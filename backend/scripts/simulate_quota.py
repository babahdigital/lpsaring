# backend/scripts/simulate_quota.py
import argparse
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional

from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.infrastructure.db.models import User
from app.utils.formatters import normalize_to_local, get_phone_number_variations, format_to_local_phone
from app.services import settings_service
from app.services.hotspot_sync_service import _calculate_remaining, _resolve_target_profile, _sync_address_list_status
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, set_hotspot_user_profile


def _compute_used(total_mb: int, status: str, fup_threshold: int, used_override: Optional[int]) -> int:
    if used_override is not None:
        return max(0, used_override)

    if status == "active":
        return max(0, int(total_mb * 0.1))
    if status == "fup":
        # Remaining <= fup_threshold
        return max(0, int(total_mb - (total_mb * fup_threshold / 100)) + 1)
    if status == "habis":
        return max(0, total_mb)
    if status == "expired":
        return max(0, int(total_mb * 0.5))
    if status == "unlimited":
        return 0
    return max(0, int(total_mb * 0.1))


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate quota status for a user.")
    parser.add_argument("--phone", required=True, help="Nomor telepon user (08... / +62...)")
    parser.add_argument(
        "--status", required=True, choices=["active", "fup", "habis", "expired", "unlimited"], help="Target status"
    )
    parser.add_argument("--total-mb", type=int, default=1000, help="Total kuota (MB)")
    parser.add_argument("--used-mb", type=int, default=None, help="Override kuota terpakai (MB)")
    parser.add_argument("--expiry-days", type=int, default=30, help="Jumlah hari sampai expired (untuk non-expired)")
    parser.add_argument("--apply-mikrotik", action="store_true", help="Terapkan profile + address-list ke MikroTik")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        normalized = normalize_to_local(args.phone)
        phone_variations = get_phone_number_variations(normalized)
        user = db.session.scalar(select(User).where(User.phone_number.in_(phone_variations)))
        if not user:
            print(f"User tidak ditemukan untuk nomor: {args.phone}")
            return

        now = datetime.now(dt_timezone.utc)
        fup_threshold = settings_service.get_setting_as_int("QUOTA_FUP_PERCENT", 20)

        if args.status == "unlimited":
            user.is_unlimited_user = True
            user.total_quota_purchased_mb = 0
            user.total_quota_used_mb = 0
            user.quota_expiry_date = None
        else:
            user.is_unlimited_user = False
            user.total_quota_purchased_mb = max(0, args.total_mb)
            user.total_quota_used_mb = _compute_used(
                user.total_quota_purchased_mb, args.status, fup_threshold, args.used_mb
            )
            if args.status == "expired":
                user.quota_expiry_date = now - timedelta(days=1)
            else:
                user.quota_expiry_date = now + timedelta(days=max(0, args.expiry_days))

        db.session.commit()

        remaining_mb, remaining_percent = _calculate_remaining(user)
        print(
            f"OK: user={user.full_name} phone={user.phone_number} status={args.status} "
            f"total={user.total_quota_purchased_mb}MB used={user.total_quota_used_mb}MB "
            f"remaining={remaining_mb}MB ({remaining_percent}%) expiry={user.quota_expiry_date}"
        )

        if not args.apply_mikrotik:
            return

        username_08 = format_to_local_phone(user.phone_number)
        if not username_08:
            print("Username Mikrotik tidak valid. Skip apply profile/address-list.")
            return

        now_utc = datetime.now(dt_timezone.utc)
        expiry = user.quota_expiry_date
        is_expired = bool(expiry and expiry < now_utc)
        target_profile = _resolve_target_profile(user, remaining_mb, remaining_percent, is_expired)

        with get_mikrotik_connection() as api:
            if not api:
                print("MikroTik tidak tersedia. Skip apply profile/address-list.")
                return

            if target_profile:
                success, message = set_hotspot_user_profile(
                    api_connection=api,
                    username_or_id=username_08,
                    new_profile_name=target_profile,
                )
                if success:
                    user.mikrotik_profile_name = target_profile
                else:
                    print(f"Gagal set profile MikroTik: {message}")

            _sync_address_list_status(api, user, username_08, remaining_mb, remaining_percent, is_expired)
            db.session.commit()
            print(f"Applied MikroTik profile + address-list for {username_08}")


if __name__ == "__main__":
    main()
