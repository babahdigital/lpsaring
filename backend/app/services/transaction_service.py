# backend/app/services/transaction_service.py
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from sqlalchemy.exc import SQLAlchemyError
from decimal import Decimal

from app.extensions import db
from app.infrastructure.db.models import User, Package, Transaction, TransactionStatus

logger = logging.getLogger(__name__)

def apply_package_to_user(transaction: Transaction) -> bool:
    """
    Logika inti yang disempurnakan untuk menerapkan paket ke pengguna.
    Secara eksplisit menangani status unlimited dan memastikan validasi data.
    """
    if not transaction or transaction.status != TransactionStatus.SUCCESS:
        logger.warning(f"Mencoba menerapkan paket dari transaksi yang tidak valid atau belum sukses: ID Transaksi {transaction.id if transaction else 'N/A'}")
        return False

    user = transaction.user
    package = transaction.package

    if not user or not package:
        logger.error(f"Transaksi {transaction.id} tidak memiliki user atau paket yang valid untuk diterapkan.")
        return False

    if package.data_quota_gb is None or package.duration_days is None:
        logger.error(f"Paket {package.id} ('{package.name}') memiliki data_quota_gb atau duration_days yang null. Proses dibatalkan.")
        return False

    logger.info(f"Menerapkan paket '{package.name}' ke pengguna '{user.full_name}' (ID: {user.id}) dari transaksi {transaction.id}.")
    
    # Perbandingan yang robust menggunakan tipe data Decimal
    is_unlimited_package = (Decimal(str(package.data_quota_gb)) == Decimal('0'))

    user.is_unlimited_user = is_unlimited_package

    if is_unlimited_package:
        user.total_quota_purchased_mb = 0
        logger.info(f"User ID {user.id} diproses sebagai PENGGUNA UNLIMITED.")
    else:
        # Untuk keamanan, set is_unlimited_user ke False lagi jika alur masuk ke else
        user.is_unlimited_user = False
        added_quota_mb = int(float(package.data_quota_gb) * 1024)
        user.total_quota_purchased_mb = (user.total_quota_purchased_mb or 0) + added_quota_mb
        logger.info(f"User ID {user.id} diproses sebagai PENGGUNA BERKUOTA dengan tambahan {added_quota_mb} MB.")

    # Perpanjangan Masa Aktif
    duration_to_add = timedelta(days=package.duration_days)
    now_utc = datetime.now(dt_timezone.utc)
    
    if user.quota_expiry_date and user.quota_expiry_date > now_utc:
        user.quota_expiry_date += duration_to_add
    else:
        user.quota_expiry_date = now_utc + duration_to_add

    logger.info(
        f"HASIL AKHIR (sebelum commit): User ID: {user.id} | "
        f"Status Unlimited: {user.is_unlimited_user} | "
        f"Plafon Kuota: {user.total_quota_purchased_mb} MB | "
        f"Masa Aktif: {user.quota_expiry_date.strftime('%Y-%m-%d %H:%M:%S %Z') if user.quota_expiry_date else 'N/A'}"
    )

    try:
        db.session.add(user)
        return True
    except SQLAlchemyError as e:
        logger.error(f"Gagal saat menambahkan perubahan pengguna {user.id} ke sesi DB: {e}", exc_info=True)
        return False