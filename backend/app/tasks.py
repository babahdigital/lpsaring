# backend/app/tasks.py
import logging
import json
import calendar
import secrets
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone as dt_timezone
from sqlalchemy.orm import selectinload

from app.infrastructure.gateways.whatsapp_client import send_whatsapp_with_pdf, send_whatsapp_message
from app.services.hotspot_sync_service import sync_hotspot_usage_and_profiles, cleanup_inactive_users
from app.services import settings_service
from app.services.access_parity_service import collect_access_parity_report
from app.services.walled_garden_service import sync_walled_garden
from app.extensions import db
from app.infrastructure.db.models import (
    ApprovalStatus,
    NotificationRecipient,
    NotificationType,
    Package,
    Transaction,
    TransactionStatus,
    User,
    UserRole,
)
from app.infrastructure.gateways.mikrotik_client import (
    activate_or_update_hotspot_user,
    get_hotspot_host_usage_map,
    get_mikrotik_connection,
    remove_address_list_entry,
    upsert_address_list_entry,
    upsert_ip_binding,
)
from app.services.notification_service import get_notification_message
from app.services.quota_mutation_ledger_service import append_quota_mutation_event, lock_user_quota_row, snapshot_user_quota_state
from app.services.user_management.helpers import _handle_mikrotik_operation
from app.commands.sync_unauthorized_hosts_command import sync_unauthorized_hosts_command
from app.utils.block_reasons import build_manual_debt_eom_reason
from app.utils.formatters import format_to_local_phone, get_app_local_datetime
from app.utils.metrics_utils import increment_metric
from app.utils.quota_debt import estimate_debt_rp_from_cheapest_package, format_rupiah

# Import create_app dari app/__init__.py
from app import create_app

# Kita akan menggunakan celery_app dari extensions.py sebagai decorator
# Pastikan ini sesuai dengan cara Anda mengimpor celery_app di docker-compose.yml
# `celery -A app.extensions.celery_app worker`
from app.extensions import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="enforce_end_of_month_debt_block_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def enforce_end_of_month_debt_block_task(self):
    """At end-of-month, warn users with unpaid quota debt via WhatsApp, then block them.

    - WhatsApp warning must be attempted first.
    - Admin notifications are sent to subscribed recipients (NotificationType.QUOTA_DEBT_LIMIT_EXCEEDED).
    """
    app = create_app()
    with app.app_context():
        now_local = get_app_local_datetime()
        last_day = calendar.monthrange(now_local.year, now_local.month)[1]

        # Default: run enforcement only on the last day, at/after 23:00 local time.
        try:
            min_hour = int(app.config.get("DEBT_EOM_BLOCK_MIN_HOUR", 23))
        except Exception:
            min_hour = 23

        if now_local.day != last_day or now_local.hour < min_hour:
            return

        if settings_service.get_setting("ENABLE_MIKROTIK_OPERATIONS", "True") != "True":
            logger.info("EOM debt block: Mikrotik ops disabled; will still update DB + WhatsApp.")

        ref_packages = (
            db.session.query(Package)
            .filter(Package.is_active.is_(True))
            .filter(Package.data_quota_gb.isnot(None))
            .filter(Package.data_quota_gb > 0)
            .filter(Package.price.isnot(None))
            .filter(Package.price > 0)
            .order_by(Package.data_quota_gb.asc(), Package.price.asc())
            .all()
        )

        def _pick_ref_pkg_for_debt_mb(value_mb: float) -> Package | None:
            try:
                mb = float(value_mb or 0)
            except Exception:
                mb = 0.0
            if mb <= 0 or not ref_packages:
                return None
            debt_gb = mb / 1024.0
            for pkg in ref_packages:
                try:
                    if float(pkg.data_quota_gb or 0) >= debt_gb:
                        return pkg
                except Exception:
                    continue
            return ref_packages[-1]

        users = (
            db.session.query(User)
            .filter(User.is_active.is_(True))
            .filter(User.approval_status == ApprovalStatus.APPROVED)
            .filter(User.role == UserRole.USER)
            .filter(User.is_unlimited_user.is_(False))
            .options(selectinload(User.devices))
            .all()
        )

        enable_wa = settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "True") == "True"
        blocked_profile = settings_service.get_setting("MIKROTIK_BLOCKED_PROFILE", "inactive") or "inactive"
        list_blocked = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked") or "blocked"
        other_status_lists = [
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_ACTIVE", "active") or "active",
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_FUP", "fup") or "fup",
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive") or "inactive",
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired") or "expired",
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_HABIS", "habis") or "habis",
        ]
        blocked_binding_type = settings_service.get_ip_binding_type_setting("IP_BINDING_TYPE_BLOCKED", "blocked")

        recipients_query = (
            db.select(User)
            .join(NotificationRecipient, User.id == NotificationRecipient.admin_user_id)
            .where(
                NotificationRecipient.notification_type == NotificationType.QUOTA_DEBT_LIMIT_EXCEEDED,
                User.is_active.is_(True),
            )
        )
        subscribed_admins = db.session.scalars(recipients_query).all()

        summary = {
            "eligible": 0,
            "warn_failed": 0,
            "blocked_success": 0,
            "block_failed": 0,
            "admin_notify_failed": 0,
        }

        for user in users:
            manual_debt_mb = int(getattr(user, "manual_debt_mb", 0) or 0)
            if manual_debt_mb <= 0:
                continue

            try:
                debt_mb = float(getattr(user, "quota_debt_total_mb", 0) or 0)
            except Exception:
                debt_mb = 0.0

            if debt_mb <= 0:
                continue

            if bool(getattr(user, "is_blocked", False)):
                continue

            summary["eligible"] += 1

            ref_pkg = _pick_ref_pkg_for_debt_mb(debt_mb)
            base_pkg_name = str(getattr(ref_pkg, "name", "") or "") or "-"
            estimate = estimate_debt_rp_from_cheapest_package(
                debt_mb=debt_mb,
                cheapest_package_price_rp=int(getattr(ref_pkg, "price", 0) or 0) if ref_pkg else 0,
                cheapest_package_quota_gb=float(getattr(ref_pkg, "data_quota_gb", 0) or 0) if ref_pkg else 0,
                cheapest_package_name=base_pkg_name,
            )
            estimate_rp = estimate.estimated_rp_rounded
            estimate_rp_text = format_rupiah(int(estimate_rp)) if isinstance(estimate_rp, int) else "-"

            debt_mb_text = str(int(round(debt_mb)))

            warned_ok = True
            if enable_wa:
                try:
                    user_msg = get_notification_message(
                        "user_quota_debt_end_of_month_warning",
                        {
                            "full_name": user.full_name,
                            "phone_number": user.phone_number,
                            "debt_mb": debt_mb_text,
                            "estimated_rp": estimate_rp_text,
                            "base_package_name": base_pkg_name,
                        },
                    )
                    warned_ok = bool(send_whatsapp_message(user.phone_number, user_msg))
                except Exception:
                    logger.exception("EOM debt block: gagal kirim WA warning ke user %s", getattr(user, "id", "?"))
                    warned_ok = False

            # Requirement: send WA first, then block.
            if enable_wa and not warned_ok:
                summary["warn_failed"] += 1
                continue

            try:
                lock_user_quota_row(user)
                before_state = snapshot_user_quota_state(user)

                if not user.mikrotik_password:
                    user.mikrotik_password = "".join(secrets.choice("0123456789") for _ in range(6))

                username_08 = format_to_local_phone(user.phone_number) or user.phone_number or ""
                comment = f"blocked|quota-debt-eom|user={username_08}"

                _handle_mikrotik_operation(
                    activate_or_update_hotspot_user,
                    user_mikrotik_username=username_08,
                    hotspot_password=user.mikrotik_password,
                    mikrotik_profile_name=blocked_profile,
                    limit_bytes_total=1,
                    session_timeout="1s",
                    comment=comment,
                    server=user.mikrotik_server_name,
                    force_update_profile=True,
                )

                user.is_blocked = True
                user.blocked_reason = build_manual_debt_eom_reason(
                    debt_mb_text=debt_mb_text,
                    manual_debt_mb=manual_debt_mb,
                    estimated_rp=int(estimate_rp) if isinstance(estimate_rp, int) else None,
                    base_pkg_name=base_pkg_name,
                )
                user.blocked_at = datetime.now(dt_timezone.utc)
                user.blocked_by_id = None

                # Rule: manual debt EOM wajib hard-block di ip-binding + address-list blocked.
                with get_mikrotik_connection() as api:
                    if api:
                        ok_host, host_map, _host_msg = get_hotspot_host_usage_map(api)
                        host_map = host_map if ok_host else {}

                        for device in user.devices or []:
                            mac = str(getattr(device, "mac_address", "") or "").upper().strip()
                            if not mac:
                                continue
                            upsert_ip_binding(
                                api_connection=api,
                                mac_address=mac,
                                binding_type=blocked_binding_type,
                                comment=f"blocked|manual-debt-eom|user={username_08}|uid={user.id}",
                            )

                            ip_addr = str(getattr(device, "ip_address", "") or "").strip()
                            if not ip_addr:
                                ip_addr = str(host_map.get(mac, {}).get("address") or "").strip()
                            if not ip_addr:
                                continue

                            upsert_address_list_entry(
                                api_connection=api,
                                address=ip_addr,
                                list_name=list_blocked,
                                comment=f"lpsaring|status=blocked|reason=manual-debt-eom|user={username_08}|uid={user.id}",
                            )
                            for list_name in other_status_lists:
                                if list_name and list_name != list_blocked:
                                    remove_address_list_entry(
                                        api_connection=api,
                                        address=ip_addr,
                                        list_name=list_name,
                                    )

                db.session.add(user)
                append_quota_mutation_event(
                    user=user,
                    source="policy.block_transition:manual_debt_eom",
                    before_state=before_state,
                    after_state=snapshot_user_quota_state(user),
                    event_details={
                        "action": "block",
                        "reason": str(getattr(user, "blocked_reason", "") or "") or None,
                        "manual_debt_mb": int(manual_debt_mb),
                        "debt_mb": float(debt_mb),
                    },
                )
                db.session.commit()
                summary["blocked_success"] += 1

                if enable_wa and subscribed_admins:
                    admin_msg = get_notification_message(
                        "admin_quota_debt_end_of_month_blocked",
                        {
                            "full_name": user.full_name,
                            "phone_number": user.phone_number,
                            "debt_mb": debt_mb_text,
                            "estimated_rp": estimate_rp_text,
                            "base_package_name": base_pkg_name,
                        },
                    )
                    for admin in subscribed_admins:
                        try:
                            sent = bool(send_whatsapp_message(admin.phone_number, admin_msg))
                            if not sent:
                                summary["admin_notify_failed"] += 1
                        except Exception:
                            summary["admin_notify_failed"] += 1
                            logger.exception(
                                "EOM debt block: gagal kirim WA admin %s utk user %s",
                                getattr(admin, "id", "?"),
                                getattr(user, "id", "?"),
                            )
            except Exception:
                db.session.rollback()
                summary["block_failed"] += 1
                logger.exception("EOM debt block: gagal proses block untuk user %s", getattr(user, "id", "?"))

        if summary["eligible"] > 0:
            increment_metric("eom.debt_block.eligible", summary["eligible"])
        if summary["warn_failed"] > 0:
            increment_metric("eom.debt_block.warn_failed", summary["warn_failed"])
        if summary["blocked_success"] > 0:
            increment_metric("eom.debt_block.success", summary["blocked_success"])
        if summary["block_failed"] > 0:
            increment_metric("eom.debt_block.failed", summary["block_failed"])
        if summary["admin_notify_failed"] > 0:
            increment_metric("eom.debt_block.admin_notify_failed", summary["admin_notify_failed"])

        logger.info(
            "EOM debt block summary: eligible=%s warn_failed=%s blocked_success=%s block_failed=%s admin_notify_failed=%s",
            summary["eligible"],
            summary["warn_failed"],
            summary["blocked_success"],
            summary["block_failed"],
            summary["admin_notify_failed"],
        )


def _record_task_failure(app, task_name: str, payload: dict, error_message: str) -> None:
    redis_client = getattr(app, "redis_client_otp", None)
    if redis_client is None:
        return
    try:
        dlq_key = app.config.get("TASK_DLQ_REDIS_KEY", "celery:dlq")
        item = {
            "task": task_name,
            "payload": payload,
            "error": error_message,
            "created_at": datetime.now(dt_timezone.utc).isoformat(),
        }
        redis_client.rpush(dlq_key, json.dumps(item))
    except Exception:
        return


@celery_app.task(
    name="audit_mikrotik_reconciliation_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def audit_mikrotik_reconciliation_task(self):
    app = create_app()
    with app.app_context():
        if settings_service.get_setting("ENABLE_MIKROTIK_OPERATIONS", "True") != "True":
            logger.info("Celery Task: Skip audit MikroTik (MikroTik operations disabled).")
            return

        if settings_service.get_setting("ENABLE_MIKROTIK_AUDIT_RECONCILIATION", "True") != "True":
            logger.info("Celery Task: Skip audit MikroTik (reconciliation disabled by setting).")
            return

        backend_root = Path(__file__).resolve().parents[1]
        script_path = backend_root / "scripts" / "audit_mikrotik_total.py"
        if not script_path.exists():
            logger.warning("Celery Task: Script audit tidak ditemukan: %s", script_path)
            return

        cmd = [sys.executable, str(script_path), "--limit", "30"]
        if settings_service.get_setting("MIKROTIK_AUDIT_AUTO_CLEANUP_STALE_BLOCKED", "False") == "True":
            cmd.extend(["--cleanup-stale-blocked", "--apply"])

        logger.info("Celery Task: Menjalankan audit MikroTik reconciliation harian.")
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(backend_root),
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            stdout = (completed.stdout or "").strip()
            stderr = (completed.stderr or "").strip()

            if completed.returncode != 0:
                raise RuntimeError(
                    f"audit_mikrotik_total exit={completed.returncode}; stderr={stderr or '-'}"
                )

            if stdout:
                logger.info("Celery Task: Audit MikroTik selesai. Summary:\n%s", stdout[-8000:])
            else:
                logger.info("Celery Task: Audit MikroTik selesai tanpa output.")
        except Exception as e:
            logger.error("Celery Task: Audit MikroTik gagal: %s", e, exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "audit_mikrotik_reconciliation_task", {}, str(e))
            raise


@celery_app.task(
    name="policy_parity_guard_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def policy_parity_guard_task(self):
    app = create_app()
    with app.app_context():
        if settings_service.get_setting("ENABLE_MIKROTIK_OPERATIONS", "True") != "True":
            logger.info("Celery Task: Skip policy parity guard (MikroTik operations disabled).")
            return

        logger.info("Celery Task: Menjalankan policy parity guard.")
        try:
            report = collect_access_parity_report(max_items=300)
            if not report.get("ok", False):
                reason = str(report.get("reason") or "unknown")
                logger.warning("Celery Task: Policy parity guard unavailable. reason=%s", reason)
                return

            summary = report.get("summary", {}) or {}
            mismatches = int(summary.get("mismatches", 0) or 0)
            mismatch_types = summary.get("mismatch_types", {}) or {}

            if mismatches > 0:
                increment_metric("policy.parity.guard.mismatches", mismatches)
                increment_metric("policy.parity.guard.binding_type", int(mismatch_types.get("binding_type", 0) or 0))
                increment_metric("policy.parity.guard.address_list", int(mismatch_types.get("address_list", 0) or 0))
                increment_metric(
                    "policy.parity.guard.address_list_multi_status",
                    int(mismatch_types.get("address_list_multi_status", 0) or 0),
                )

            redis_client = getattr(app, "redis_client_otp", None)
            if redis_client is not None:
                try:
                    redis_client.set(
                        "policy_parity:last_report",
                        json.dumps(
                            {
                                "generated_at": datetime.now(dt_timezone.utc).isoformat(),
                                "summary": summary,
                                "items": report.get("items", [])[:100],
                            }
                        ),
                        ex=24 * 3600,
                    )
                except Exception:
                    pass

            if mismatches > 0:
                top_items = report.get("items", [])[:5]
                logger.warning(
                    "Policy parity guard detected mismatches=%s detail=%s",
                    mismatches,
                    json.dumps(top_items, ensure_ascii=False),
                )
            else:
                logger.info("Policy parity guard: no mismatch detected.")
        except Exception as e:
            logger.error("Celery Task: Policy parity guard gagal: %s", e, exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "policy_parity_guard_task", {}, str(e))
            raise


@celery_app.task(
    name="send_whatsapp_invoice_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_whatsapp_invoice_task(
    self, recipient_number: str, caption: str, pdf_url: str, filename: str, request_id: str = ""
):
    """
    Celery task untuk mengirim pesan WhatsApp dengan lampiran PDF.

    Args:
        recipient_number (str): Nomor HP tujuan.
        caption (str): Teks/caption untuk pesan WhatsApp.
        pdf_url (str): URL publik ke file PDF invoice.
        filename (str): Nama file PDF.
    """
    # Penting: Buat instance aplikasi Flask di dalam konteks task
    # Ini memastikan current_app tersedia untuk semua fungsi yang dipanggil dalam task
    # yang membutuhkan konteks aplikasi (misalnya, mengakses app.config)
    # environ.get sekarang akan berfungsi karena 'environ' telah diimpor secara langsung.
    app = create_app()

    with app.app_context():
        logger.info(
            f"Celery Task: Memulai pengiriman WhatsApp dengan PDF ke {recipient_number} untuk URL: {pdf_url}. Request ID: {request_id}"
        )
        try:
            # send_whatsapp_with_pdf sekarang akan memiliki akses ke current_app
            success = send_whatsapp_with_pdf(recipient_number, caption, pdf_url, filename)
            if not success:
                logger.error(
                    f"Celery Task: Gagal mengirim WhatsApp invoice ke {recipient_number} (Fonnte reported failure)."
                )
                # Fallback: kirim pesan teks tanpa PDF
                text_success = send_whatsapp_message(recipient_number, caption)
                if text_success:
                    logger.info(f"Celery Task: Pesan teks berhasil dikirim ke {recipient_number} setelah gagal PDF.")
                else:
                    logger.error(f"Celery Task: Pesan teks juga gagal dikirim ke {recipient_number}.")
                    raise RuntimeError("Fonnte gagal mengirim pesan PDF dan teks.")
            else:
                logger.info(f"Celery Task: Berhasil mengirim WhatsApp invoice ke {recipient_number}.")
        except Exception as e:
            logger.error(
                f"Celery Task: Exception saat mengirim WhatsApp invoice ke {recipient_number}: {e}", exc_info=True
            )
            if self.request.retries >= 3:
                _record_task_failure(
                    app,
                    "send_whatsapp_invoice_task",
                    {
                        "recipient_number": recipient_number,
                        "caption": caption,
                        "pdf_url": pdf_url,
                        "filename": filename,
                        "request_id": request_id,
                    },
                    str(e),
                )
            raise


@celery_app.task(
    name="sync_hotspot_usage_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def sync_hotspot_usage_task(self):
    app = create_app()
    with app.app_context():
        logger.info("Celery Task: Memulai sinkronisasi kuota dan profil hotspot.")
        try:
            sync_interval = settings_service.get_setting_as_int("QUOTA_SYNC_INTERVAL_SECONDS", 300)
            redis_client = getattr(app, "redis_client_otp", None)
            if redis_client is not None:
                now_ts = int(datetime.now(dt_timezone.utc).timestamp())
                last_ts_str = redis_client.get("quota_sync:last_run_ts")
                if last_ts_str:
                    last_ts = int(last_ts_str)
                    if now_ts - last_ts < max(sync_interval, 30):
                        logger.info("Celery Task: Skip sinkronisasi (menunggu interval dinamis).")
                        return

            result = sync_hotspot_usage_and_profiles()
            logger.info(f"Celery Task: Sinkronisasi selesai. Result: {result}")
            if redis_client is not None:
                redis_client.set("quota_sync:last_run_ts", int(datetime.now(dt_timezone.utc).timestamp()))
        except Exception as e:
            logger.error(f"Celery Task: Sinkronisasi gagal: {e}", exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "sync_hotspot_usage_task", {}, str(e))
            raise


@celery_app.task(
    name="sync_unauthorized_hosts_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def sync_unauthorized_hosts_task(self):
    app = create_app()
    with app.app_context():
        if settings_service.get_setting("ENABLE_MIKROTIK_OPERATIONS", "True") != "True":
            logger.info("Celery Task: Skip sync unauthorized hosts (MikroTik operations disabled).")
            return

        logger.info("Celery Task: Memulai sinkronisasi unauthorized hosts.")
        try:
            sync_unauthorized_hosts_command.main(args=["--apply"], standalone_mode=False)
            logger.info("Celery Task: Sinkronisasi unauthorized hosts selesai.")
        except SystemExit as e:
            if int(getattr(e, "code", 0) or 0) != 0:
                raise RuntimeError(f"sync-unauthorized-hosts exit code {e.code}")
        except Exception as e:
            logger.error(f"Celery Task: Sinkronisasi unauthorized hosts gagal: {e}", exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "sync_unauthorized_hosts_task", {}, str(e))
            raise


@celery_app.task(
    name="cleanup_inactive_users_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def cleanup_inactive_users_task(self):
    app = create_app()
    with app.app_context():
        logger.info("Celery Task: Memulai pembersihan pengguna tidak aktif.")
        try:
            result = cleanup_inactive_users()
            logger.info(f"Celery Task: Pembersihan selesai. Result: {result}")
        except Exception as e:
            logger.error(f"Celery Task: Pembersihan gagal: {e}", exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "cleanup_inactive_users_task", {}, str(e))
            raise


@celery_app.task(
    name="sync_walled_garden_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def sync_walled_garden_task(self):
    app = create_app()
    with app.app_context():
        logger.info("Celery Task: Memulai sinkronisasi walled-garden.")
        try:
            result = sync_walled_garden()
            logger.info(f"Celery Task: Walled-garden sync selesai. Result: {result}")
        except Exception as e:
            logger.error(f"Celery Task: Walled-garden sync gagal: {e}", exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "sync_walled_garden_task", {}, str(e))
            raise


@celery_app.task(
    name="expire_stale_transactions_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def expire_stale_transactions_task(self):
    app = create_app()
    with app.app_context():
        now_utc = datetime.now(dt_timezone.utc)
        try:
            try:
                expiry_minutes = int(app.config.get("MIDTRANS_DEFAULT_EXPIRY_MINUTES", 15))
            except Exception:
                expiry_minutes = 15
            expiry_minutes = max(5, min(expiry_minutes, 24 * 60))
            # Grace window to avoid expiring transactions too aggressively.
            grace_minutes = 5
            legacy_cutoff = now_utc - timedelta(minutes=(expiry_minutes + grace_minutes))

            # Expire transactions that were initiated or pending but exceeded expiry_time.
            q = (
                db.session.query(Transaction)
                .filter(Transaction.status.in_([TransactionStatus.UNKNOWN, TransactionStatus.PENDING]))
                .filter(Transaction.expiry_time.isnot(None))
                .filter(Transaction.expiry_time < now_utc)
            )
            to_expire = q.all()

            # Also expire legacy rows that never had expiry_time set.
            q_legacy = (
                db.session.query(Transaction)
                .filter(Transaction.status.in_([TransactionStatus.UNKNOWN, TransactionStatus.PENDING]))
                .filter(Transaction.expiry_time.is_(None))
                .filter(Transaction.created_at < legacy_cutoff)
            )
            to_expire.extend(q_legacy.all())

            if not to_expire:
                return

            for tx in to_expire:
                tx.status = TransactionStatus.EXPIRED

            db.session.commit()
            logger.info("Celery Task: Expired %s stale transactions.", len(to_expire))
        except Exception as e:
            logger.error("Celery Task: Expire stale transactions gagal: %s", e, exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "expire_stale_transactions_task", {}, str(e))
            raise
