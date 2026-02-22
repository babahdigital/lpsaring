# backend/scripts/ensure_mikrotik_profile.py
import argparse
from typing import Any

from app import create_app
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection


def _profile_exists(api: Any, name: str) -> bool:
    profiles = api.get_resource("/ip/hotspot/user/profile").get()
    for p in profiles:
        if str(p.get("name", "")).lower() == name.lower():
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Ensure MikroTik hotspot profile exists.")
    parser.add_argument("--name", required=True, help="Nama profil hotspot")
    parser.add_argument("--rate-limit", default=None, help="Rate limit (opsional)")
    parser.add_argument("--shared-users", default=None, help="Shared users (opsional)")
    parser.add_argument("--comment", default=None, help="Comment (opsional)")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        with get_mikrotik_connection() as api:
            if not api:
                print("MikroTik tidak tersedia. Tidak bisa memastikan profil.")
                return

            if _profile_exists(api, args.name):
                print(f"Profil '{args.name}' sudah ada.")
                return

            payload = {"name": args.name}
            if args.rate_limit:
                payload["rate-limit"] = args.rate_limit
            if args.shared_users:
                payload["shared-users"] = str(args.shared_users)
            if args.comment:
                payload["comment"] = args.comment

            api.get_resource("/ip/hotspot/user/profile").add(**payload)
            print(f"Profil '{args.name}' berhasil dibuat.")


if __name__ == "__main__":
    main()
