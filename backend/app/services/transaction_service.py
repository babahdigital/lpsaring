# backend/app/services/transaction_service.py
import logging
import secrets
import string
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.infrastructure.db.models import Package, Transaction, TransactionStatus, User
from app.services import settings_service
from app.infrastructure.gateways.mikrotik_client import (
    activate_or_update_hotspot_user,
)
from app.utils.formatters import format_to_local_phone

logger = logging.getLogger(__name__)


def generate_random_password(length: int = 6) -> str:
    """Menghasilkan password numerik acak dengan panjang yang ditentukan."""
    return "".join(secrets.choice(string.digits) for _ in range(length))


def apply_package_and_sync_to_mikrotik(
    transaction: Transaction, mikrotik_api: Any
) -> tuple[bool, str]:
    """
    Logika inti yang disempurnakan.
    1. Menerapkan manfaat paket ke objek User.
    2. Melakukan sinkronisasi langsung ke Mikrotik.
    3. Mengembalikan status keberhasilan untuk di-commit atau di-rollback oleh pemanggil.
    """
    if not transaction or transaction.status != TransactionStatus.SUCCESS:
        msg = f"Mencoba menerapkan paket dari transaksi yang tidak valid atau belum sukses: ID {transaction.id if transaction else 'N/A'}"
        logger.warning(msg)
        return False, msg

    user = transaction.user
    package = transaction.package

    if not user or not package or not package.profile:
        msg = f"Transaksi {transaction.id} tidak memiliki user, paket, atau profil paket yang valid."
        logger.error(msg)
        return False, msg

    logger.info(
        f"Menerapkan paket '{package.name}' ke pengguna '{user.full_name}' dari transaksi {transaction.id}."
    )

    is_unlimited_package = Decimal(str(package.data_quota_gb)) == Decimal("0")
    user.is_unlimited_user = is_unlimited_package

    if is_unlimited_package:
        user.total_quota_purchased_mb = 0
        logger.info(f"User ID {user.id} diproses sebagai PENGGUNA UNLIMITED.")
    else:
        user.is_unlimited_user = False
        added_quota_mb = int(float(package.data_quota_gb) * 1024)
        user.total_quota_purchased_mb = (
            user.total_quota_purchased_mb or 0
        ) + added_quota_mb
        logger.info(
            f"User ID {user.id} diproses sebagai PENGGUNA BERKUOTA dengan tambahan {added_quota_mb} MB."
        )

    duration_to_add = timedelta(days=package.duration_days)
    now_utc = datetime.now(dt_timezone.utc)

    if user.quota_expiry_date and user.quota_expiry_date > now_utc:
        user.quota_expiry_date += duration_to_add
    else:
        user.quota_expiry_date = now_utc + duration_to_add

    if not user.mikrotik_password or not (
        len(user.mikrotik_password) == 6 and user.mikrotik_password.isdigit()
    ):
        user.mikrotik_password = generate_random_password()
    transaction.hotspot_password = user.mikrotik_password

    if not mikrotik_api:
        msg = "Koneksi Mikrotik tidak tersedia, sinkronisasi dilewati."
        logger.warning(msg)
        return True, msg

    hotspot_username = format_to_local_phone(user.phone_number)
    if not hotspot_username:
        msg = f"Format nomor telepon user {user.id} tidak valid untuk Mikrotik."
        logger.error(msg)
        return False, msg

    mikrotik_profile_to_set = package.profile.profile_name
    if user.is_unlimited_user:
        unlimited_profile_name = settings_service.get_setting('MIKROTIK_UNLIMITED_PROFILE', 'unlimited')
        logger.info(
            f"User ID {user.id} adalah UNLIMITED. Mengganti profil dari '{mikrotik_profile_to_set}' menjadi '{unlimited_profile_name}'."
        )
        mikrotik_profile_to_set = unlimited_profile_name

    limit_bytes_total = (
        0
        if user.is_unlimited_user
        else int((user.total_quota_purchased_mb or 0) * 1024 * 1024)
    )
    session_timeout_seconds = max(
        0, int((user.quota_expiry_date - now_utc).total_seconds())
    )

    # --- PENYEMPURNAAN: Menyiapkan parameter server secara dinamis ---
    params_for_mt = {
        'api_connection': mikrotik_api,
        'user_mikrotik_username': hotspot_username,
        'mikrotik_profile_name': mikrotik_profile_to_set,
        'hotspot_password': user.mikrotik_password,
        'comment': f"Order:{transaction.midtrans_order_id}",
        'limit_bytes_total': limit_bytes_total,
        'session_timeout_seconds': session_timeout_seconds,
        'force_update_profile': True,
    }

    # Tambahkan parameter 'server' hanya jika ada nilainya di data user
    if hasattr(user, 'mikrotik_server_name') and user.mikrotik_server_name:
        params_for_mt['server'] = user.mikrotik_server_name
        logger.info(
            f"Sinkronisasi ke Mikrotik untuk user '{hotspot_username}' pada SERVER: '{user.mikrotik_server_name}', PROFIL: '{mikrotik_profile_to_set}'."
        )
    else:
        logger.info(
            f"Sinkronisasi ke Mikrotik untuk user '{hotspot_username}' pada SEMUA SERVER (default), PROFIL: '{mikrotik_profile_to_set}'."
        )
    # -----------------------------------------------------------------

    # Memanggil fungsi dengan parameter yang sudah lengkap
    success_mt, msg_mt = activate_or_update_hotspot_user(**params_for_mt)

    if not success_mt:
        logger.error(
            f"SINKRONISASI MIKROTIK GAGAL untuk user '{hotspot_username}'. Pesan: {msg_mt}."
        )
        return False, f"Gagal sinkronisasi ke Mikrotik: {msg_mt}"

    try:
        db.session.add(user)
        db.session.add(transaction)
        logger.info(
            f"Sinkronisasi Mikrotik BERHASIL untuk user '{hotspot_username}'. Perubahan siap di-commit."
        )
        return True, "Paket berhasil diterapkan dan disinkronkan ke Mikrotik."
    except SQLAlchemyError as e:
        logger.error(
            f"Gagal saat menambahkan perubahan user {user.id} ke sesi DB: {e}",
            exc_info=True,
        )
        return False, "Gagal memproses data di sesi database."