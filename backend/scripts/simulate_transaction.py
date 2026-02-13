# backend/scripts/simulate_transaction.py
import argparse
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.infrastructure.db.models import Package, Transaction, TransactionStatus, User
from app.services.transaction_service import generate_random_password
from app.utils.formatters import get_phone_number_variations, normalize_to_local


def _select_user(phone_number: str) -> User | None:
    normalized = normalize_to_local(phone_number)
    phone_variations = get_phone_number_variations(normalized)
    return db.session.scalar(select(User).where(User.phone_number.in_(phone_variations)))


def _select_package(package_id: str | None, package_name: str | None) -> Package | None:
    if package_id:
        return db.session.scalar(select(Package).where(Package.id == uuid.UUID(package_id)))
    if package_name:
        return db.session.scalar(select(Package).where(Package.name == package_name))
    return db.session.scalar(select(Package).where(Package.is_active).order_by(Package.created_at.asc()))


def _apply_package_to_user(user: User, package: Package, now_utc: datetime) -> None:
    is_unlimited_package = Decimal(str(package.data_quota_gb)) == Decimal("0")
    if is_unlimited_package:
        user.is_unlimited_user = True
        user.total_quota_purchased_mb = 0
    else:
        user.is_unlimited_user = False
        added_quota_mb = int(float(package.data_quota_gb) * 1024)
        user.total_quota_purchased_mb = (user.total_quota_purchased_mb or 0) + added_quota_mb

    duration_to_add = timedelta(days=package.duration_days)
    if user.quota_expiry_date and user.quota_expiry_date > now_utc:
        user.quota_expiry_date += duration_to_add
    else:
        user.quota_expiry_date = now_utc + duration_to_add

    if not user.mikrotik_password or not (
        len(user.mikrotik_password) == 6 and user.mikrotik_password.isdigit()
    ):
        user.mikrotik_password = generate_random_password()


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate a successful package transaction.")
    parser.add_argument("--phone", required=True, help="Nomor telepon user (08... / +62...)")
    parser.add_argument("--package-id", default=None, help="ID paket (UUID) opsional")
    parser.add_argument("--package-name", default=None, help="Nama paket (opsional, harus cocok persis)")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        user = _select_user(args.phone)
        if not user:
            print(f"User tidak ditemukan untuk nomor: {args.phone}")
            return

        package = _select_package(args.package_id, args.package_name)
        if not package:
            print("Paket tidak ditemukan atau tidak aktif.")
            return

        now_utc = datetime.now(dt_timezone.utc)
        order_id = f"SIM-{uuid.uuid4().hex[:12].upper()}"

        transaction = Transaction()
        transaction.id = uuid.uuid4()
        transaction.user_id = user.id
        transaction.package_id = package.id
        transaction.midtrans_order_id = order_id
        transaction.amount = int(package.price or 0)
        transaction.status = TransactionStatus.SUCCESS
        transaction.payment_method = "simulation"
        transaction.payment_time = now_utc

        _apply_package_to_user(user, package, now_utc)
        transaction.hotspot_password = user.mikrotik_password

        db.session.add(user)
        db.session.add(transaction)
        db.session.commit()

        print(
            "OK: transaksi simulasi sukses "
            f"order_id={order_id} user={user.full_name} package={package.name} amount={transaction.amount}"
        )


if __name__ == "__main__":
    main()
