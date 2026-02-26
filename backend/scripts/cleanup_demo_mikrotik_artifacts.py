import argparse
from dataclasses import dataclass

from sqlalchemy import bindparam, text

from app import create_app
from app.extensions import db
from app.infrastructure.gateways.mikrotik_client import delete_hotspot_user, get_mikrotik_connection
from app.utils.formatters import format_to_local_phone, get_phone_number_variations


@dataclass(frozen=True)
class DemoRow:
    source_phone: str
    username_08: str | None
    user_id: str | None


_SELECT_FIRST_USER_BY_PHONE_SQL = text(
    """
    SELECT id::text AS user_id, phone_number
    FROM users
    WHERE phone_number IN :phones
    ORDER BY created_at ASC
    LIMIT 1
    """
).bindparams(bindparam("phones", expanding=True))


def _get_users_columns() -> set[str]:
    rows = db.session.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'users'
            """
        )
    ).scalars()
    return {str(col) for col in rows}


def _iter_demo_rows(raw_demo_values: list[str]) -> list[DemoRow]:
    rows: list[DemoRow] = []
    seen_user_ids: set[str] = set()

    for source_phone in raw_demo_values:
        try:
            variations = list(set(get_phone_number_variations(source_phone)))
        except Exception:
            variations = []
        if not variations:
            rows.append(DemoRow(source_phone=source_phone, username_08=None, user_id=None))
            continue

        row = db.session.execute(_SELECT_FIRST_USER_BY_PHONE_SQL, {"phones": variations}).mappings().first()
        if not row:
            rows.append(DemoRow(source_phone=source_phone, username_08=None, user_id=None))
            continue

        user_id = str(row.get("user_id") or "").strip()
        if not user_id:
            rows.append(DemoRow(source_phone=source_phone, username_08=None, user_id=None))
            continue

        if user_id in seen_user_ids:
            continue
        seen_user_ids.add(user_id)

        username_08 = format_to_local_phone(str(row.get("phone_number") or ""))
        rows.append(DemoRow(source_phone=source_phone, username_08=username_08, user_id=user_id))

    return rows


def _reset_db_mikrotik_flags(user_id: str, users_columns: set[str]) -> bool:
    assignments: list[str] = []
    if "mikrotik_user_exists" in users_columns:
        assignments.append("mikrotik_user_exists = FALSE")
    if "mikrotik_profile_name" in users_columns:
        assignments.append("mikrotik_profile_name = NULL")
    if "mikrotik_server_name" in users_columns:
        assignments.append("mikrotik_server_name = NULL")

    if not assignments:
        return False

    update_sql = text(f"UPDATE users SET {', '.join(assignments)} WHERE id::text = :user_id")
    db.session.execute(update_sql, {"user_id": str(user_id)})
    return True


def _cleanup_by_comment_contains(api, resource_path: str, keyword: str) -> tuple[int, int]:
    removed = 0
    scanned = 0
    try:
        rows = api.get_resource(resource_path).get()
    except Exception:
        return 0, 0

    for row in rows:
        scanned += 1
        comment = str(row.get("comment") or "")
        if keyword not in comment:
            continue
        row_id = row.get("id") or row.get(".id")
        if not row_id:
            continue
        try:
            api.get_resource(resource_path).remove(id=row_id)
            removed += 1
        except Exception:
            continue
    return removed, scanned


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cleanup demo users artifacts on MikroTik and reset DB mikrotik linkage flags."
    )
    parser.add_argument("--apply", action="store_true", help="Apply cleanup actions. Default is dry-run.")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        demo_enabled = bool(app.config.get("DEMO_MODE_ENABLED", False))
        allowed_raw = app.config.get("DEMO_ALLOWED_PHONES") or []
        if not isinstance(allowed_raw, list):
            allowed_raw = []
        demo_values = [str(v).strip() for v in allowed_raw if str(v).strip()]

        print("== Cleanup demo Mikrotik artifacts ==")
        print(f"Mode         : {'APPLY' if args.apply else 'DRY-RUN'}")
        print(f"Demo enabled : {demo_enabled}")
        print(f"Whitelist    : {len(demo_values)}")

        if not demo_values:
            print("SKIP: DEMO_ALLOWED_PHONES kosong.")
            return 0

        rows = _iter_demo_rows(demo_values)
        found = [r for r in rows if r.user_id is not None]
        missing = [r for r in rows if r.user_id is None]

        for row in missing:
            print(f"- missing-db phone={row.source_phone}")

        if not args.apply:
            for row in found:
                print(f"- would-clean phone={row.source_phone} user_id={row.user_id} username={row.username_08}")
            return 0

        if not found:
            print("SKIP: tidak ada user demo yang ditemukan di DB.")
            return 0

        with get_mikrotik_connection() as api:
            if not api:
                print("ERROR: gagal konek MikroTik.")
                return 2

            total_deleted_users = 0
            total_removed_comment_rows = 0
            users_columns = _get_users_columns()
            total_db_resets = 0

            for row in found:
                username_08 = str(row.username_08 or "").strip()
                if username_08:
                    ok_del, msg_del = delete_hotspot_user(api, username_08)
                    print(f"- delete-hotspot-user username={username_08} ok={ok_del} msg={msg_del}")
                    if ok_del:
                        total_deleted_users += 1

                    for resource_path in (
                        "/ip/hotspot/ip-binding",
                        "/ip/dhcp-server/lease",
                        "/ip/arp",
                        "/ip/firewall/address-list",
                    ):
                        removed, scanned = _cleanup_by_comment_contains(api, resource_path, username_08)
                        total_removed_comment_rows += removed
                        if removed > 0:
                            print(
                                f"  - cleanup-comment resource={resource_path} removed={removed} scanned={scanned} keyword={username_08}"
                            )

                if row.user_id and _reset_db_mikrotik_flags(row.user_id, users_columns):
                    total_db_resets += 1

            db.session.commit()
            print("\n-- Summary --")
            print(f"Users found in DB         : {len(found)}")
            print(f"Hotspot users deleted     : {total_deleted_users}")
            print(f"Comment-based rows removed: {total_removed_comment_rows}")
            print(f"DB mikrotik flags reset   : {total_db_resets}")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())