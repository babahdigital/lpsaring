# backend/app/tasks.py
import logging
import json
import calendar
import secrets
from datetime import datetime, timedelta, timezone as dt_timezone

from app.infrastructure.gateways.whatsapp_client import send_whatsapp_with_pdf, send_whatsapp_message
from app.services.hotspot_sync_service import sync_hotspot_usage_and_profiles, cleanup_inactive_users
from app.services import settings_service
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
from app.infrastructure.gateways.mikrotik_client import activate_or_update_hotspot_user
from app.services.notification_service import get_notification_message
from app.services.user_management.helpers import _handle_mikrotik_operation
from app.utils.formatters import format_to_local_phone, get_app_local_datetime
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

        cheapest_pkg = (
            db.session.query(Package)
            .filter(Package.is_active.is_(True))
            .filter(Package.data_quota_gb > 0)
            .order_by(Package.price.asc())
            .first()
        )

        cheapest_pkg_price = int(getattr(cheapest_pkg, "price", 0) or 0)
        cheapest_pkg_quota_gb = float(getattr(cheapest_pkg, "data_quota_gb", 0) or 0)
        cheapest_pkg_name = str(getattr(cheapest_pkg, "name", "") or "") or "-"

        users = (
            db.session.query(User)
            .filter(User.is_active.is_(True))
            .filter(User.approval_status == ApprovalStatus.APPROVED)
            .filter(User.role == UserRole.USER)
            .filter(User.is_unlimited_user.is_(False))
            .all()
        )

        enable_wa = settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "True") == "True"
        blocked_profile = settings_service.get_setting("MIKROTIK_BLOCKED_PROFILE", "inactive") or "inactive"

        recipients_query = (
            db.select(User)
            .join(NotificationRecipient, User.id == NotificationRecipient.admin_user_id)
            .where(
                NotificationRecipient.notification_type == NotificationType.QUOTA_DEBT_LIMIT_EXCEEDED,
                User.is_active.is_(True),
            )
        )
        subscribed_admins = db.session.scalars(recipients_query).all()

        for user in users:
            try:
                debt_mb = float(getattr(user, "quota_debt_total_mb", 0) or 0)
            except Exception:
                debt_mb = 0.0

            if debt_mb <= 0:
                continue

            if bool(getattr(user, "is_blocked", False)):
                continue

            estimate = estimate_debt_rp_from_cheapest_package(
                debt_mb=debt_mb,
                cheapest_package_price_rp=cheapest_pkg_price,
                cheapest_package_quota_gb=cheapest_pkg_quota_gb,
                cheapest_package_name=cheapest_pkg_name,
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
                            "base_package_name": cheapest_pkg_name,
                        },
                    )
                    warned_ok = bool(send_whatsapp_message(user.phone_number, user_msg))
                except Exception:
                    logger.exception("EOM debt block: gagal kirim WA warning ke user %s", getattr(user, "id", "?"))
                    warned_ok = False

            # Requirement: send WA first, then block.
            if enable_wa and not warned_ok:
                continue

            try:
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
                user.blocked_reason = (
                    f"quota_debt_end_of_month|debt_mb={debt_mb_text}"
                    + (f"|estimated_rp={int(estimate_rp)}" if isinstance(estimate_rp, int) else "")
                    + (f"|base_pkg={cheapest_pkg_name}" if cheapest_pkg_name else "")
                )
                user.blocked_at = datetime.now(dt_timezone.utc)
                user.blocked_by_id = None
                db.session.add(user)
                db.session.commit()

                if enable_wa and subscribed_admins:
                    admin_msg = get_notification_message(
                        "admin_quota_debt_end_of_month_blocked",
                        {
                            "full_name": user.full_name,
                            "phone_number": user.phone_number,
                            "debt_mb": debt_mb_text,
                            "estimated_rp": estimate_rp_text,
                            "base_package_name": cheapest_pkg_name,
                        },
                    )
                    for admin in subscribed_admins:
                        send_whatsapp_message(admin.phone_number, admin_msg)
            except Exception:
                db.session.rollback()
                logger.exception("EOM debt block: gagal proses block untuk user %s", getattr(user, "id", "?"))


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
