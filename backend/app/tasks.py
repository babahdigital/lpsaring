# backend/app/tasks.py
import logging
import json
import calendar
import secrets
import subprocess
import sys
import re
from urllib.parse import quote_plus
from pathlib import Path
from datetime import datetime, timedelta, timezone as dt_timezone
from sqlalchemy import text, select
from sqlalchemy.orm import selectinload

from app.infrastructure.gateways.whatsapp_client import send_whatsapp_with_pdf, send_whatsapp_message
from app.services.hotspot_sync_service import sync_hotspot_usage_and_profiles, cleanup_inactive_users
from app.services import settings_service
from app.services.access_parity_service import collect_access_parity_report
from app.services.walled_garden_service import sync_walled_garden
from app.extensions import db
from app.infrastructure.db.models import (
    AdminActionLog,
    AdminActionType,
    ApprovalStatus,
    NotificationRecipient,
    NotificationType,
    Package,
    PublicDatabaseUpdateSubmission,
    QuotaMutationLedger,
    RefreshToken,
    Transaction,
    TransactionStatus,
    User,
    UserDevice,
    UserRole,
)
from app.infrastructure.gateways.mikrotik_client import (
    activate_or_update_hotspot_user,
    delete_hotspot_user,
    get_hotspot_host_usage_map,
    get_mikrotik_connection,
    remove_address_list_entry,
    upsert_address_list_entry,
    upsert_ip_binding,
)
from app.services.notification_service import get_notification_message
from app.services.quota_mutation_ledger_service import append_quota_mutation_event, lock_user_quota_row, snapshot_user_quota_state
from app.services.user_management.helpers import _handle_mikrotik_operation
from app.services.user_management.user_deletion import run_user_auth_cleanup
from app.commands.sync_unauthorized_hosts_command import sync_unauthorized_hosts_command
from app.utils.block_reasons import build_manual_debt_eom_reason
from app.utils.formatters import format_to_local_phone, get_app_local_datetime, get_phone_number_variations
from app.utils.metrics_utils import increment_metric
from app.utils.quota_debt import estimate_debt_rp_from_cheapest_package, format_rupiah

# Import create_app dari app/__init__.py
from app import create_app

# Kita akan menggunakan celery_app dari extensions.py sebagai decorator
# Pastikan ini sesuai dengan cara Anda mengimpor celery_app di docker-compose.yml
# `celery -A app.extensions.celery_app worker`
from app.extensions import celery_app

logger = logging.getLogger(__name__)

_MIKROTIK_DURATION_PART = re.compile(r"(\d+)([wdhms])", re.IGNORECASE)

_NON_RETRYABLE_UNAUTHORIZED_SYNC_ERROR_MARKERS = (
    "gagal konek mikrotik",
    "gagal ambil hotspot host",
    "kegagalan operasi router",
    "routerosapiconnectionerror",
    "timed out",
    "timeout",
)


def _should_skip_public_update_whatsapp_for_phone(phone_number: str) -> str | None:
    """Return skip-reason string jika nomor tidak layak menerima WA update, None jika harus dikirim.

    Skip permanen (whatsapp_notified_at boleh di-set → stop retry):
    - "no_phone"        : nomor kosong
    - "already_updated" : user sudah update data (nama tidak lagi diawali 'Imported ')

    Skip sementara (jangan set whatsapp_notified_at → coba lagi nanti):
    - "inactive_or_unapproved" : user Imported tapi belum aktif/disetujui
    """
    normalized_phone = str(phone_number or "").strip()
    if not normalized_phone:
        return "no_phone"

    try:
        variations = get_phone_number_variations(normalized_phone)
        user = db.session.query(User).filter(User.phone_number.in_(variations)).order_by(User.created_at.desc()).first()

        # Nomor tidak ada di DB → bukan user kita, jangan kirim WA
        if user is None:
            return "already_updated"

        # Hanya kirim ke user yang namanya diawali "Imported " (hasil import, belum update data)
        user_name = str(getattr(user, "full_name", "") or "").strip()
        if not user_name.startswith("Imported "):
            return "already_updated"  # user sudah update nama lewat form, skip permanen

        is_approved = getattr(user, "approval_status", None) == ApprovalStatus.APPROVED
        is_active = bool(getattr(user, "is_active", False))
        if not (is_approved and is_active):
            return "inactive_or_unapproved"  # skip sementara, jangan tandai sebagai terkirim

        return None  # kirim WA
    except Exception:
        # Best effort guard; never block message processing on lookup errors.
        return None


def _is_non_retryable_unauthorized_sync_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return any(marker in message for marker in _NON_RETRYABLE_UNAUTHORIZED_SYNC_ERROR_MARKERS)


@celery_app.task(
    name="clear_total_if_no_update_submission_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
)
def clear_total_if_no_update_submission_task(self):
    """Dangerous operation: clear all users from DB and MikroTik when update sync mode is enabled and stale."""

    app = create_app()
    with app.app_context():
        if not bool(app.config.get("UPDATE_ENABLE_SYNC", False)):
            logger.info("Update sync auto-clear skipped: UPDATE_ENABLE_SYNC is disabled.")
            return {"success": True, "skipped": True, "reason": "update_sync_disabled"}

        if not bool(app.config.get("UPDATE_ALLOW_DESTRUCTIVE_AUTO_CLEAR", False)):
            logger.warning(
                "Update sync auto-clear skipped: UPDATE_ALLOW_DESTRUCTIVE_AUTO_CLEAR is disabled. "
                "This guard prevents accidental full user wipe."
            )
            return {"success": True, "skipped": True, "reason": "destructive_guard_disabled"}

        try:
            stale_days = int(app.config.get("UPDATE_CLEAR_TOTAL_AFTER_DAYS", 3))
        except Exception:
            stale_days = 3
        if stale_days < 1:
            stale_days = 1

        now_utc = datetime.now(dt_timezone.utc)
        cutoff = now_utc - timedelta(days=stale_days)

        latest_submission = (
            db.session.query(PublicDatabaseUpdateSubmission)
            .order_by(PublicDatabaseUpdateSubmission.created_at.desc())
            .first()
        )

        if latest_submission and latest_submission.created_at and latest_submission.created_at >= cutoff:
            logger.info(
                "Update sync auto-clear skipped: latest submission is still within %s days.",
                stale_days,
            )
            return {"success": True, "skipped": True, "reason": "fresh_submission"}

        users = db.session.query(User).all()
        mikrotik_failed = []

        if app.config.get("ENABLE_MIKROTIK_OPERATIONS", True):
            try:
                with get_mikrotik_connection() as api_connection:
                    if api_connection is not None:
                        for user in users:
                            username = format_to_local_phone(user.phone_number) or str(user.phone_number or "").strip()
                            if not username:
                                continue
                            ok, msg = delete_hotspot_user(api_connection, username)
                            if not ok and "tidak ditemukan" not in str(msg).lower():
                                mikrotik_failed.append({"username": username, "error": str(msg)})
            except Exception as mikrotik_error:
                logger.error("Update sync auto-clear: gagal koneksi/hapus MikroTik: %s", mikrotik_error, exc_info=True)
                mikrotik_failed.append({"error": str(mikrotik_error)})

        if mikrotik_failed:
            logger.warning("Update sync auto-clear dibatalkan karena kegagalan cleanup MikroTik.")
            return {
                "success": False,
                "skipped": True,
                "reason": "mikrotik_cleanup_failed",
                "errors": mikrotik_failed,
            }

        # Clear total user-related data from DB.
        # Use get_bind() first because scoped sessions may have bind=None even on PostgreSQL.
        session_bind = None
        try:
            session_bind = db.session.get_bind()
        except Exception:
            session_bind = getattr(db.session, "bind", None)

        dialect_name = str(getattr(getattr(session_bind, "dialect", None), "name", "") or "").lower()
        if dialect_name.startswith("postgresql"):
            db.session.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
        else:
            # Fallback for non-postgres test/dev cases. Use set-based statements to avoid
            # row-by-row ORM delete ordering/autoflush issues on self-referenced FKs.
            db.session.execute(
                text(
                    "UPDATE users "
                    "SET approved_by_id = NULL, rejected_by_id = NULL, blocked_by_id = NULL "
                    "WHERE approved_by_id IS NOT NULL OR rejected_by_id IS NOT NULL OR blocked_by_id IS NOT NULL"
                )
            )
            db.session.query(User).delete(synchronize_session=False)
        db.session.commit()

        logger.warning(
            "Update sync auto-clear executed: no submissions for %s days, total users cleared=%s",
            stale_days,
            len(users),
        )
        return {"success": True, "cleared_users": len(users), "stale_days": stale_days}


@celery_app.task(
    name="send_public_update_submission_whatsapp_batch_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
)
def send_public_update_submission_whatsapp_batch_task(self):
    """Kirim WA bertahap untuk data public update (maks 3 nomor unik per siklus secara default)."""

    app = create_app()
    with app.app_context():
        if not bool(app.config.get("UPDATE_ENABLE_SYNC", False)):
            logger.info("Update sync WA batch skipped: UPDATE_ENABLE_SYNC is disabled.")
            return {"success": True, "skipped": True, "reason": "update_sync_disabled"}

        if settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "True") != "True":
            logger.info("Update sync WA batch skipped: WhatsApp notifications disabled.")
            return {"success": True, "skipped": True, "reason": "whatsapp_disabled"}

        try:
            batch_size = int(app.config.get("UPDATE_WHATSAPP_BATCH_SIZE", 3))
        except Exception:
            batch_size = 3
        batch_size = max(1, min(batch_size, 20))

        try:
            deadline_days = int(app.config.get("UPDATE_CLEAR_TOTAL_AFTER_DAYS", 3))
        except Exception:
            deadline_days = 3
        deadline_days = max(1, deadline_days)

        message_template = (
            app.config.get("UPDATE_WHATSAPP_IMPORT_MESSAGE_TEMPLATE")
            or (
                "Halo *{full_name}*,\n\n"
                "Kami mendeteksi data Anda di jaringan LPSaring perlu dilengkapi.\n\n"
                "Silakan perbarui data melalui link berikut *dalam {deadline_days} hari*:\n"
                "{update_link}\n\n"
                "\u26a0\ufe0f *Peringatan:* Jika tidak diperbarui, akun Anda akan *dihapus otomatis* dari sistem.\n\n"
                "Terima kasih,\nTim LPSaring"
            )
        )
        base_public_url = str(app.config.get("APP_PUBLIC_BASE_URL") or "").strip().rstrip("/")

        fetch_limit = max(batch_size * 10, 30)
        all_rows = db.session.query(PublicDatabaseUpdateSubmission).all()
        pending_rows = [
            row
            for row in all_rows
            if getattr(row, "whatsapp_notified_at", None) is None and str(getattr(row, "phone_number", "") or "").strip()
        ]
        pending_rows.sort(key=lambda item: getattr(item, "created_at", datetime.min.replace(tzinfo=dt_timezone.utc)))
        pending_rows = pending_rows[:fetch_limit]

        def _normalize_phone_key(phone_number: str) -> str:
            digits = "".join(ch for ch in str(phone_number or "") if ch.isdigit())
            if not digits:
                return ""
            if digits.startswith("0"):
                return f"62{digits[1:]}"
            if digits.startswith("8"):
                return f"62{digits}"
            return digits

        phone_groups = {}
        for row in pending_rows:
            key = _normalize_phone_key(getattr(row, "phone_number", ""))
            if not key:
                continue
            phone_groups.setdefault(key, []).append(row)
            if len(phone_groups) >= batch_size:
                break

        if not phone_groups:
            logger.info("Update sync WA batch: no pending submissions with valid phone numbers.")
            return {"success": True, "skipped": True, "reason": "no_pending_phone"}

        sent_numbers = 0
        failed_numbers = 0
        now_utc = datetime.now(dt_timezone.utc)

        for _phone_key, grouped_rows in phone_groups.items():
            representative = grouped_rows[0]
            context = {
                "full_name": getattr(representative, "full_name", "Pengguna"),
                "role": getattr(representative, "role", ""),
                "blok": getattr(representative, "blok", ""),
                "kamar": getattr(representative, "kamar", ""),
                "tamping_type": getattr(representative, "tamping_type", "") or "",
                "deadline_days": deadline_days,
            }

            phone_for_link = str(getattr(representative, "phone_number", "") or "").strip()
            encoded_phone = quote_plus(phone_for_link)
            encoded_name = quote_plus(str(context.get("full_name") or ""))
            if base_public_url:
                update_link = f"{base_public_url}/update?phone={encoded_phone}&name={encoded_name}"
            else:
                update_link = f"/update?phone={encoded_phone}&name={encoded_name}"
            context["update_link"] = update_link

            try:
                message = str(message_template).format(**context)
            except Exception:
                message = (
                    f"Halo {context['full_name']}, silakan perbarui data melalui link ini "
                    f"*dalam {deadline_days} hari*: {update_link}\n\n"
                    f"\u26a0\ufe0f Jika tidak diperbarui, akun Anda akan dihapus otomatis dari sistem."
                )

            skip_reason = _should_skip_public_update_whatsapp_for_phone(getattr(representative, "phone_number", ""))
            if skip_reason is not None:
                # Skip permanen (already_updated / no_phone): tandai sebagai selesai agar tidak diproses ulang
                # Skip sementara (inactive_or_unapproved): JANGAN set whatsapp_notified_at, coba lagi nanti
                is_permanent_skip = skip_reason != "inactive_or_unapproved"
                if is_permanent_skip:
                    for row in grouped_rows:
                        row.whatsapp_notified_at = now_utc
                        row.whatsapp_notify_last_error = skip_reason
                else:
                    for row in grouped_rows:
                        row.whatsapp_notify_last_error = skip_reason
                logger.info(
                    "Update sync WA batch: skip phone reason=%s permanent=%s (phone=%s)",
                    skip_reason,
                    is_permanent_skip,
                    getattr(representative, "phone_number", ""),
                )
                continue

            sent_ok = bool(send_whatsapp_message(getattr(representative, "phone_number", ""), message))
            for row in grouped_rows:
                row.whatsapp_notify_attempts = int(getattr(row, "whatsapp_notify_attempts", 0) or 0) + 1
                if sent_ok:
                    row.whatsapp_notified_at = now_utc
                    row.whatsapp_notify_last_error = None
                else:
                    row.whatsapp_notify_last_error = "send_failed"

            if sent_ok:
                sent_numbers += 1
            else:
                failed_numbers += 1

        db.session.commit()

        logger.info(
            "Update sync WA batch processed: sent_numbers=%s failed_numbers=%s batch_size=%s",
            sent_numbers,
            failed_numbers,
            batch_size,
        )
        return {
            "success": True,
            "sent_numbers": sent_numbers,
            "failed_numbers": failed_numbers,
            "batch_size": batch_size,
        }


@celery_app.task(
    name="auto_delete_unresponsive_imported_users_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
)
def auto_delete_unresponsive_imported_users_task(self):
    """Hapus user Imported yang tidak mengisi form update setelah X hari."""

    app = create_app()
    with app.app_context():
        if not bool(app.config.get("UPDATE_ENABLE_SYNC", False)):
            logger.info("Auto-delete unresponsive skipped: UPDATE_ENABLE_SYNC is disabled.")
            return {"success": True, "skipped": True, "reason": "update_sync_disabled"}

        if not bool(app.config.get("UPDATE_AUTO_DELETE_UNRESPONSIVE", False)):
            logger.info("Auto-delete unresponsive skipped: UPDATE_AUTO_DELETE_UNRESPONSIVE is disabled.")
            return {"success": True, "skipped": True, "reason": "auto_delete_disabled"}

        try:
            deadline_days = int(app.config.get("UPDATE_CLEAR_TOTAL_AFTER_DAYS", 3))
        except Exception:
            deadline_days = 3
        deadline_days = max(1, deadline_days)

        try:
            max_per_run = int(app.config.get("UPDATE_AUTO_DELETE_MAX_PER_RUN", 5))
        except Exception:
            max_per_run = 5
        max_per_run = max(1, max_per_run)

        now_utc = datetime.now(dt_timezone.utc)
        cutoff = now_utc - timedelta(days=deadline_days)

        all_overdue = (
            db.session.query(PublicDatabaseUpdateSubmission)
            .filter(
                PublicDatabaseUpdateSubmission.whatsapp_notified_at.isnot(None),
                PublicDatabaseUpdateSubmission.whatsapp_notified_at < cutoff,
                PublicDatabaseUpdateSubmission.approval_status == "PENDING",
            )
            .order_by(PublicDatabaseUpdateSubmission.whatsapp_notified_at.asc())
            .all()
        )

        def _normalize_phone_key(phone_number: str) -> str:
            digits = "".join(ch for ch in str(phone_number or "") if ch.isdigit())
            if not digits:
                return ""
            if digits.startswith("0"):
                return f"62{digits[1:]}"
            if digits.startswith("8"):
                return f"62{digits}"
            return digits

        phone_groups: dict = {}
        for row in all_overdue:
            key = _normalize_phone_key(getattr(row, "phone_number", ""))
            if not key:
                continue
            phone_groups.setdefault(key, []).append(row)
            if len(phone_groups) >= max_per_run:
                break

        if not phone_groups:
            logger.info("Auto-delete unresponsive: no overdue PENDING submissions.")
            return {"success": True, "skipped": True, "reason": "no_overdue_pending"}

        deleted_count = 0
        skipped_count = 0

        with get_mikrotik_connection() as api:
            for _phone_key, submissions in phone_groups.items():
                representative = submissions[0]
                raw_phone = str(getattr(representative, "phone_number", "") or "").strip()
                if not raw_phone:
                    skipped_count += 1
                    continue

                variations = get_phone_number_variations(raw_phone)
                user = (
                    db.session.query(User)
                    .filter(User.phone_number.in_(variations))
                    .order_by(User.created_at.desc())
                    .first()
                )
                if user is None:
                    logger.info(
                        "Auto-delete unresponsive: user not found for phone=%s, marking submissions.", raw_phone
                    )
                    for sub in submissions:
                        sub.approval_status = "DELETED_AUTO"
                        sub.rejection_reason = (
                            f"Auto-deleted: tidak merespons {deadline_days} hari (user not found)"
                        )
                    skipped_count += 1
                    continue

                if user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
                    logger.info("Auto-delete unresponsive: SKIP admin user %s.", user.phone_number)
                    skipped_count += 1
                    continue

                user_name = str(getattr(user, "full_name", "") or "").strip()
                if not user_name.startswith("Imported "):
                    logger.info(
                        "Auto-delete unresponsive: SKIP non-imported user %s.", user.phone_number
                    )
                    skipped_count += 1
                    continue

                if user.quota_expiry_date is not None and user.quota_expiry_date > now_utc:
                    logger.info(
                        "Auto-delete unresponsive: SKIP user %s — kuota aktif hingga %s.",
                        user.phone_number,
                        user.quota_expiry_date,
                    )
                    skipped_count += 1
                    continue

                username_08 = format_to_local_phone(user.phone_number)

                if api and username_08:
                    ok, msg = delete_hotspot_user(api_connection=api, username=username_08)
                    if not ok and "tidak ditemukan" not in str(msg).lower():
                        logger.warning(
                            "Auto-delete unresponsive: failed to delete MikroTik user %s: %s",
                            username_08, msg,
                        )

                # Gunakan run_user_auth_cleanup untuk cleanup menyeluruh:
                # - hapus UserDevice dari DB
                # - _cleanup_router_artifacts: hotspot host, ip-binding, DHCP, ARP,
                #   semua managed address-list (active, blocked, fup, habis, expired,
                #   inactive, unauthorized) — by IP dan by uid-comment scan.
                cleanup_summary = run_user_auth_cleanup(user)
                devices_cleaned = cleanup_summary.get("device_count_before", 0)
                mikrotik_connected = cleanup_summary.get("router", {}).get("mikrotik_connected", False)

                for sub in submissions:
                    sub.approval_status = "DELETED_AUTO"
                    sub.rejection_reason = f"Auto-deleted: tidak merespons {deadline_days} hari"

                # NOTE: Hindari keyword-args pada declarative model agar Pylance tidak memunculkan
                # `reportCallIssue` (model SQLAlchemy tidak selalu terinferensi memiliki __init__(**kwargs)).
                log_entry = AdminActionLog()
                log_entry.admin_id = None
                log_entry.target_user_id = None
                log_entry.action_type = AdminActionType.MANUAL_USER_DELETE
                log_entry.details = json.dumps({
                    "auto_delete": True,
                    "phone_number": raw_phone,
                    "full_name": user_name,
                    "deadline_days": deadline_days,
                    "devices_cleaned": devices_cleaned,
                    "mikrotik_connected": mikrotik_connected,
                }, default=str)
                db.session.add(log_entry)

                db.session.delete(user)
                deleted_count += 1
                logger.warning(
                    "Auto-delete unresponsive: DELETED %s (phone=%s, deadline=%d hari)",
                    user_name, raw_phone, deadline_days,
                )

        db.session.commit()

        logger.info(
            "Auto-delete unresponsive imported users: deleted=%d skipped=%d deadline_days=%d",
            deleted_count, skipped_count, deadline_days,
        )
        return {
            "success": True,
            "deleted": deleted_count,
            "skipped": skipped_count,
            "deadline_days": deadline_days,
        }


@celery_app.task(
    name="populate_update_submissions_from_imported_users_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
)
def populate_update_submissions_from_imported_users_task(self):
    """Scan user Imported di tabel users → buat PublicDatabaseUpdateSubmission jika belum ada.

    Task ini memastikan setiap user yang diimport (nama diawali 'Imported ')
    memiliki minimal satu baris di public_database_update_submissions sehingga
    task send_public_update_submission_whatsapp_batch_task bisa mengirim WA notifikasi.
    Satu submission per nomor HP — jika sudah ada, skip.
    """
    app = create_app()
    with app.app_context():
        if not bool(app.config.get("UPDATE_ENABLE_SYNC", False)):
            logger.info("populate_imported_submissions skipped: UPDATE_ENABLE_SYNC disabled.")
            return {"success": True, "skipped": True, "reason": "update_sync_disabled"}

        imported_users = (
            db.session.query(User)
            .filter(User.full_name.like("Imported %"))
            .order_by(User.created_at.asc())
            .all()
        )

        created = 0
        already_exists = 0

        for user in imported_users:
            phone = str(getattr(user, "phone_number", "") or "").strip()
            if not phone:
                continue

            # Periksa variasi nomor agar tidak duplikat meskipun format beda
            variations = get_phone_number_variations(phone)
            existing = (
                db.session.query(PublicDatabaseUpdateSubmission)
                .filter(PublicDatabaseUpdateSubmission.phone_number.in_(variations))
                .first()
            )
            if existing:
                already_exists += 1
                continue

            # Buat submission stub — data aktual diisi oleh user via form
            submission = PublicDatabaseUpdateSubmission()
            submission.full_name = str(getattr(user, "full_name", "") or "").strip()
            submission.role = "USER"
            submission.phone_number = phone
            submission.source_ip = "system:populate_task"
            db.session.add(submission)
            created += 1

        db.session.commit()

        logger.info(
            "populate_imported_submissions: created=%d already_exists=%d total_imported_users=%d",
            created, already_exists, len(imported_users),
        )
        return {
            "success": True,
            "created": created,
            "already_exists": already_exists,
            "total_imported_users": len(imported_users),
        }

def _parse_mikrotik_duration_seconds(value: str) -> int:
    text = str(value or "").strip().lower()
    if not text:
        return 0

    multipliers = {
        "w": 7 * 24 * 60 * 60,
        "d": 24 * 60 * 60,
        "h": 60 * 60,
        "m": 60,
        "s": 1,
    }

    total = 0
    for amount_text, unit in _MIKROTIK_DURATION_PART.findall(text):
        try:
            total += int(amount_text) * multipliers[unit.lower()]
        except Exception:
            continue

    return max(0, total)


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
        if settings_service.get_setting("MIKROTIK_AUDIT_AUTO_CLEANUP_ORPHANED_LISTS", "False") == "True":
            cmd.extend(["--cleanup-orphaned-lists", "--apply"])

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
        sync_interval = settings_service.get_setting_as_int("QUOTA_SYNC_INTERVAL_SECONDS", 300)
        redis_client = getattr(app, "redis_client_otp", None)

        # Throttle check: skip jika belum melewati interval sejak run terakhir
        if redis_client is not None:
            now_ts = int(datetime.now(dt_timezone.utc).timestamp())
            last_ts_str = redis_client.get("quota_sync:last_run_ts")
            if last_ts_str:
                last_ts = int(last_ts_str)
                if now_ts - last_ts < max(sync_interval, 30):
                    logger.info("Celery Task: Skip sinkronisasi (menunggu interval dinamis).")
                    return

        # Mutex lock: cegah eksekusi concurrent dari beberapa worker (root cause deadlock DB)
        # SET NX (atomic) — hanya satu worker yang bisa acquire pada satu waktu
        lock_key = "quota_sync:run_lock"
        lock_ttl = 3600  # Safety TTL: task bisa jalan hingga 52+ menit (observed); 120s terlalu pendek → menyebabkan multiple worker berjalan bersamaan → quota double-deducted
        lock_acquired = False
        try:
            if redis_client is not None:
                lock_acquired = bool(redis_client.set(lock_key, "1", nx=True, ex=lock_ttl))
                if not lock_acquired:
                    logger.info("Celery Task: Skip sinkronisasi (worker lain sedang berjalan).")
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
        finally:
            if redis_client is not None and lock_acquired:
                redis_client.delete(lock_key)


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

        redis_client = getattr(app, "redis_client_otp", None)
        lock_key = "sync_unauthorized_hosts:lock"
        lock_acquired = False
        lock_ttl_seconds = max(60, settings_service.get_setting_as_int("UNAUTHORIZED_SYNC_LOCK_TTL_SECONDS", 180))

        if redis_client is not None:
            try:
                lock_acquired = bool(
                    redis_client.set(
                        lock_key,
                        int(datetime.now(dt_timezone.utc).timestamp()),
                        nx=True,
                        ex=lock_ttl_seconds,
                    )
                )
            except Exception:
                lock_acquired = False

            if not lock_acquired:
                logger.info("Celery Task: Skip sync unauthorized hosts (lock aktif, run sebelumnya belum selesai).")
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
            if _is_non_retryable_unauthorized_sync_error(e):
                _record_task_failure(app, "sync_unauthorized_hosts_task", {}, str(e))
                logger.warning(
                    "Celery Task: Sinkronisasi unauthorized hosts tidak diretry karena error non-retryable."
                )
                return {
                    "success": False,
                    "reason": "non_retryable_mikrotik_sync_error",
                    "error": str(e),
                }
            if self.request.retries >= 2:
                _record_task_failure(app, "sync_unauthorized_hosts_task", {}, str(e))
            raise
        finally:
            if redis_client is not None and lock_acquired:
                try:
                    redis_client.delete(lock_key)
                except Exception:
                    pass


@celery_app.task(
    name="cleanup_waiting_dhcp_arp_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def cleanup_waiting_dhcp_arp_task(self):
    app = create_app()
    with app.app_context():
        if settings_service.get_setting("ENABLE_MIKROTIK_OPERATIONS", "True") != "True":
            logger.info("Celery Task: Skip cleanup waiting DHCP/ARP (MikroTik operations disabled).")
            return

        if settings_service.get_setting("AUTO_CLEANUP_WAITING_DHCP_ARP_ENABLED", "False") != "True":
            logger.info("Celery Task: Skip cleanup waiting DHCP/ARP (feature disabled).")
            return

        keyword = (
            settings_service.get_setting("AUTO_CLEANUP_WAITING_DHCP_ARP_COMMENT_KEYWORD", "lpsaring|static-dhcp")
            or "lpsaring|static-dhcp"
        ).strip().lower()
        min_last_seen_seconds = max(
            0,
            settings_service.get_setting_as_int("AUTO_CLEANUP_WAITING_DHCP_ARP_MIN_LAST_SEEN_SECONDS", 6 * 60 * 60),
        )

        logger.info(
            "Celery Task: Memulai cleanup waiting DHCP/ARP (keyword=%s, min_last_seen_seconds=%s).",
            keyword,
            min_last_seen_seconds,
        )

        try:
            with get_mikrotik_connection() as api:
                if not api:
                    raise RuntimeError("Gagal konek MikroTik")

                lease_res = api.get_resource("/ip/dhcp-server/lease")
                arp_res = api.get_resource("/ip/arp")

                leases = lease_res.get() or []
                arp_rows = arp_res.get() or []
                arp_by_ip = {
                    str(row.get("address") or "").strip(): row
                    for row in arp_rows
                    if str(row.get("address") or "").strip()
                }
                arp_by_mac = {
                    str(row.get("mac-address") or "").strip().upper(): row
                    for row in arp_rows
                    if str(row.get("mac-address") or "").strip()
                }

                summary = {
                    "waiting_candidates": 0,
                    "skipped_recent": 0,
                    "lease_removed": 0,
                    "arp_removed": 0,
                    "lease_failed": 0,
                    "arp_failed": 0,
                }
                removed_arp_ids: set[str] = set()

                for lease in leases:
                    status = str(lease.get("status") or "").strip().lower()
                    comment_text = str(lease.get("comment") or "").lower()
                    if status != "waiting" or keyword not in comment_text:
                        continue

                    summary["waiting_candidates"] += 1

                    last_seen_text = str(lease.get("last-seen") or "").strip()
                    last_seen_seconds = _parse_mikrotik_duration_seconds(last_seen_text)
                    if last_seen_seconds and last_seen_seconds < min_last_seen_seconds:
                        summary["skipped_recent"] += 1
                        continue

                    ip_text = str(lease.get("address") or "").strip()
                    mac_text = str(lease.get("mac-address") or "").strip().upper()
                    lease_id = lease.get(".id") or lease.get("id")

                    if lease_id:
                        try:
                            lease_res.remove(id=lease_id)
                            summary["lease_removed"] += 1
                        except Exception:
                            summary["lease_failed"] += 1
                            logger.exception(
                                "Celery Task: Gagal remove waiting lease id=%s ip=%s mac=%s",
                                lease_id,
                                ip_text,
                                mac_text,
                            )

                    arp_row = arp_by_ip.get(ip_text) or arp_by_mac.get(mac_text)
                    arp_id = (arp_row or {}).get(".id") or (arp_row or {}).get("id")
                    if arp_id and str(arp_id) not in removed_arp_ids:
                        try:
                            arp_res.remove(id=arp_id)
                            removed_arp_ids.add(str(arp_id))
                            summary["arp_removed"] += 1
                        except Exception:
                            summary["arp_failed"] += 1
                            logger.exception(
                                "Celery Task: Gagal remove ARP id=%s ip=%s mac=%s",
                                arp_id,
                                ip_text,
                                mac_text,
                            )

                logger.info(
                    "Celery Task: Cleanup waiting DHCP/ARP selesai. %s",
                    json.dumps(summary, ensure_ascii=False),
                )
        except Exception as e:
            logger.error("Celery Task: Cleanup waiting DHCP/ARP gagal: %s", e, exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "cleanup_waiting_dhcp_arp_task", {}, str(e))
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


@celery_app.task(
    name="purge_stale_quota_keys_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
)
def purge_stale_quota_keys_task(self):
    """
    Hapus Redis key quota:last_bytes:mac:<MAC> untuk perangkat yang sudah
    tidak aktif (tidak ada di UserDevice atau last_seen_at > STALE_DAYS hari lalu).
    Jalankan harian jam 03:30 via Celery Beat.
    """
    app = create_app()
    with app.app_context():
        if settings_service.get_setting("QUOTA_STALE_KEY_PURGE_ENABLED", "True") != "True":
            logger.info("Celery Task: Skip purge stale quota keys (fitur disabled).")
            return

        stale_days = max(1, settings_service.get_setting_as_int("QUOTA_STALE_KEY_STALE_DAYS", 30))
        redis_client = getattr(app, "redis_client_otp", None)
        if redis_client is None:
            logger.warning("Celery Task: Skip purge stale quota keys (redis_client tidak tersedia).")
            return

        try:
            prefix = "quota:last_bytes:mac:"
            # Kumpulkan semua MAC dari Redis
            redis_macs: set[str] = set()
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor, match=f"{prefix}*", count=200)
                for key in keys:
                    key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                    mac = key_str[len(prefix):]
                    if mac:
                        redis_macs.add(mac.upper())
                if cursor == 0:
                    break

            if not redis_macs:
                logger.info("Celery Task: Purge stale quota keys — tidak ada key ditemukan.")
                return

            # Cari MAC yang masih aktif di DB (last_seen dalam stale_days)
            cutoff = datetime.now(dt_timezone.utc) - timedelta(days=stale_days)
            active_macs: set[str] = set()
            rows = (
                db.session.query(UserDevice.mac_address)
                .filter(UserDevice.last_seen_at >= cutoff)
                .filter(UserDevice.mac_address.isnot(None))
                .all()
            )
            for row in rows:
                if row.mac_address:
                    active_macs.add(row.mac_address.upper())

            # Hapus key untuk MAC yang tidak aktif
            stale_macs = redis_macs - active_macs
            deleted = 0
            for mac in stale_macs:
                try:
                    redis_client.delete(f"{prefix}{mac}")
                    deleted += 1
                except Exception:
                    pass

            logger.info(
                "Celery Task: Purge stale quota keys selesai. "
                "redis_total=%s active_db=%s stale_deleted=%s",
                len(redis_macs),
                len(active_macs),
                deleted,
            )
        except Exception as e:
            logger.error("Celery Task: Purge stale quota keys gagal: %s", e, exc_info=True)
            if self.request.retries >= 1:
                _record_task_failure(app, "purge_stale_quota_keys_task", {}, str(e))
            raise


@celery_app.task(
    name="dlq_health_monitor_task",
    bind=True,
    retry_kwargs={"max_retries": 0},
)
def dlq_health_monitor_task(self):
    """
    Cek panjang Dead Letter Queue (DLQ) Celery setiap 15 menit.
    Kirim notifikasi WhatsApp ke superadmin jika DLQ tidak kosong,
    dengan throttle agar tidak spam (default: 1x per 60 menit).
    """
    app = create_app()
    with app.app_context():
        throttle_minutes = settings_service.get_setting_as_int("TASK_DLQ_ALERT_THROTTLE_MINUTES", 60)
        if throttle_minutes <= 0:
            return

        redis_client = getattr(app, "redis_client_otp", None)
        if redis_client is None:
            return

        try:
            # --- Check 1: Dead Letter Queue ---
            dlq_key = app.config.get("TASK_DLQ_REDIS_KEY", "celery:dlq")
            dlq_length = redis_client.llen(dlq_key)
            if dlq_length > 0:
                throttle_key = "dlq:alert:last_sent"
                if redis_client.exists(throttle_key):
                    logger.debug("Celery Task: DLQ monitor — alert throttled (DLQ=%s).", dlq_length)
                else:
                    items_raw = redis_client.lrange(dlq_key, -3, -1)
                    preview_lines = []
                    for raw in items_raw:
                        try:
                            item = json.loads(raw)
                            preview_lines.append(f"- [{item.get('task','?')}] {item.get('error','')[:80]}")
                        except Exception:
                            pass
                    preview = "\n".join(preview_lines) if preview_lines else "(tidak bisa dibaca)"

                    admin_phone = app.config.get("SUPERADMIN_PHONE", "")
                    if admin_phone:
                        wa_number = re.sub(r"[^0-9]", "", str(admin_phone))
                        if wa_number.startswith("0"):
                            wa_number = "62" + wa_number[1:]
                        msg = (
                            f"⚠️ *ALERT: Celery DLQ tidak kosong*\n"
                            f"Total task gagal: *{dlq_length}*\n\n"
                            f"Preview 3 terakhir:\n{preview}\n\n"
                            f"Cek log container celery_worker untuk detail.\n"
                            f"Throttle: alert berikutnya dalam {throttle_minutes} menit."
                        )
                        try:
                            send_whatsapp_message(wa_number, msg)
                            logger.warning(
                                "Celery Task: DLQ alert dikirim ke admin. DLQ length=%s.", dlq_length
                            )
                        except Exception as wa_err:
                            logger.error("Celery Task: Gagal kirim DLQ alert WA: %s", wa_err)
                    redis_client.setex(throttle_key, throttle_minutes * 60, 1)

            # --- Check 2: Circuit breaker open alerts ---
            cb_count = redis_client.llen("cb:open_alerts")
            if cb_count > 0:
                raw_alerts = redis_client.lrange("cb:open_alerts", 0, -1)
                redis_client.delete("cb:open_alerts")
                circuit_names = []
                for raw in raw_alerts:
                    try:
                        item = json.loads(raw)
                        circuit_names.append(item.get("name", "unknown"))
                    except Exception:
                        pass
                if circuit_names:
                    alert_phone = (
                        app.config.get("CIRCUIT_BREAKER_ALERT_PHONE", "")
                        or app.config.get("SUPERADMIN_PHONE", "")
                    )
                    if alert_phone:
                        wa_number = re.sub(r"[^0-9]", "", str(alert_phone))
                        if wa_number.startswith("0"):
                            wa_number = "62" + wa_number[1:]
                        threshold = app.config.get("CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5)
                        msg = (
                            f"🔴 *ALERT: Circuit Breaker Terbuka*\n"
                            f"Circuit: *{', '.join(sorted(set(circuit_names)))}*\n\n"
                            f"Koneksi ke layanan tersebut bermasalah "
                            f"(≥{threshold} failure berturut-turut).\n"
                            f"Router/API tidak dapat dijangkau.\n"
                            f"Cek log container backend / celery_worker untuk detail."
                        )
                        try:
                            send_whatsapp_message(wa_number, msg)
                            logger.warning(
                                "Celery Task: Circuit breaker open alert dikirim: %s", circuit_names
                            )
                        except Exception as wa_err:
                            logger.error(
                                "Celery Task: Gagal kirim circuit breaker alert WA: %s", wa_err
                            )

        except Exception as e:
            logger.error("Celery Task: DLQ health monitor gagal: %s", e, exc_info=True)


@celery_app.task(
    name="purge_quota_mutation_ledger_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
)
def purge_quota_mutation_ledger_task(self):
    """
    Hapus entri quota_mutation_ledger yang lebih tua dari QUOTA_MUTATION_LEDGER_RETENTION_DAYS
    (default 90 hari). Mencegah tabel tumbuh tak terbatas dan menjaga performa query analytics.
    Jalan harian jam 04:00 via Celery Beat.
    """
    app = create_app()
    with app.app_context():
        try:
            try:
                retention_days = int(app.config.get("QUOTA_MUTATION_LEDGER_RETENTION_DAYS", 90))
            except Exception:
                retention_days = 90
            retention_days = max(30, retention_days)

            cutoff = datetime.now(dt_timezone.utc) - timedelta(days=retention_days)
            deleted = (
                db.session.query(QuotaMutationLedger)
                .filter(QuotaMutationLedger.created_at < cutoff)
                .delete(synchronize_session=False)
            )
            if deleted:
                db.session.commit()
                logger.info(
                    "Celery Task: Purged %s quota_mutation_ledger entri (retention=%d hari, cutoff=%s).",
                    deleted, retention_days, cutoff.date(),
                )
            else:
                logger.info(
                    "Celery Task: quota_mutation_ledger purge — tidak ada entri > %d hari.", retention_days
                )
        except Exception as e:
            db.session.rollback()
            logger.error("Celery Task: purge_quota_mutation_ledger gagal: %s", e, exc_info=True)
            if self.request.retries >= 1:
                _record_task_failure(app, "purge_quota_mutation_ledger_task", {}, str(e))
            raise


@celery_app.task(
    name="revoke_expired_refresh_tokens_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
)
def revoke_expired_refresh_tokens_task(self):
    """
    Hapus refresh token yang sudah expired atau sudah di-revoke lebih dari
    REFRESH_TOKEN_CLEANUP_KEEP_DAYS (default 7) hari lalu.
    Mencegah tabel refresh_tokens akumulasi tak terbatas.
    Jalan harian jam 04:30 via Celery Beat.
    """
    app = create_app()
    with app.app_context():
        try:
            try:
                keep_days = int(app.config.get("REFRESH_TOKEN_CLEANUP_KEEP_DAYS", 7))
            except Exception:
                keep_days = 7
            keep_days = max(1, keep_days)

            now_utc = datetime.now(dt_timezone.utc)
            revoked_cutoff = now_utc - timedelta(days=keep_days)

            # Hapus token yang sudah expired (tanpa perlu is_revoked)
            deleted_expired = (
                db.session.query(RefreshToken)
                .filter(RefreshToken.expires_at < now_utc)
                .delete(synchronize_session=False)
            )
            # Hapus token is_revoked=True yang lebih tua dari keep_days
            deleted_revoked = (
                db.session.query(RefreshToken)
                .filter(
                    RefreshToken.is_revoked == True,  # noqa: E712
                    RefreshToken.created_at < revoked_cutoff,
                )
                .delete(synchronize_session=False)
            )
            total = deleted_expired + deleted_revoked
            if total:
                db.session.commit()
                logger.info(
                    "Celery Task: Cleanup refresh tokens — expired=%s, revoked_old=%s (total=%s).",
                    deleted_expired, deleted_revoked, total,
                )
            else:
                logger.info("Celery Task: Refresh token cleanup — tidak ada token usang.")
        except Exception as e:
            db.session.rollback()
            logger.error("Celery Task: revoke_expired_refresh_tokens gagal: %s", e, exc_info=True)
            if self.request.retries >= 1:
                _record_task_failure(app, "revoke_expired_refresh_tokens_task", {}, str(e))
            raise
