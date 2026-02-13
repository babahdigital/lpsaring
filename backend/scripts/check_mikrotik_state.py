import argparse
import uuid
from typing import Optional

from app import create_app
from app.extensions import db
from app.infrastructure.db.models import User
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection
from app.utils.formatters import format_to_local_phone, get_phone_number_variations


def _match_comment(comment: Optional[str], user_id: uuid.UUID, username_08: str) -> bool:
    if not comment:
        return False
    text = str(comment)
    return f"user_id={user_id}" in text or f"phone={username_08}" in text or f"user={user_id}" in text


def main() -> int:
    parser = argparse.ArgumentParser(description="Cek status MikroTik untuk user.")
    parser.add_argument("--phone", required=True, help="Nomor telepon user (format lokal/62/+62)")
    parser.add_argument("--client-ip", default="", help="IP client untuk filter address-list/ip-binding")
    parser.add_argument("--client-mac", default="", help="MAC client untuk filter ip-binding")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        variations = get_phone_number_variations(args.phone)
        user = db.session.query(User).filter(User.phone_number.in_(variations)).first()
        if not user:
            print("User tidak ditemukan.")
            return 1

        user_id = user.id
        username_08 = format_to_local_phone(user.phone_number)
        if not username_08:
            print("Format nomor telepon user tidak valid.")
            return 1
        client_ip = args.client_ip.strip()
        client_mac = args.client_mac.strip().upper()

        with get_mikrotik_connection() as api:
            if not api:
                print("MikroTik tidak tersedia.")
                return 2

            print(f"User: {user.full_name} | ID: {user_id} | Phone: {user.phone_number} | Username08: {username_08}")

            hotspot_users = api.get_resource("/ip/hotspot/user").get(name=username_08)
            if hotspot_users:
                print(f"Hotspot user ditemukan: profile={hotspot_users[0].get('profile')} server={hotspot_users[0].get('server')}")
            else:
                print("Hotspot user tidak ditemukan.")

            bindings = api.get_resource("/ip/hotspot/ip-binding").get()
            matched_bindings = []
            for entry in bindings:
                mac = str(entry.get("mac-address") or "").upper()
                address = str(entry.get("address") or "")
                comment = entry.get("comment")
                if client_mac and mac == client_mac:
                    matched_bindings.append(entry)
                    continue
                if client_ip and address == client_ip:
                    matched_bindings.append(entry)
                    continue
                if _match_comment(comment, user_id, username_08):
                    matched_bindings.append(entry)

            print(f"IP binding match count: {len(matched_bindings)}")
            for entry in matched_bindings:
                print(f"  - mac={entry.get('mac-address')} ip={entry.get('address')} type={entry.get('type')} comment={entry.get('comment')}")

            addr_list = api.get_resource("/ip/firewall/address-list").get()
            matched_addr = []
            for entry in addr_list:
                address = str(entry.get("address") or "")
                comment = entry.get("comment")
                if client_ip and address == client_ip:
                    matched_addr.append(entry)
                    continue
                if _match_comment(comment, user_id, username_08):
                    matched_addr.append(entry)

            print(f"Address-list match count: {len(matched_addr)}")
            for entry in matched_addr:
                print(f"  - list={entry.get('list')} address={entry.get('address')} comment={entry.get('comment')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
