import argparse
from dataclasses import dataclass
import uuid
from typing import Iterable

from app import create_app
from app.extensions import db
from app.infrastructure.db.models import User
from app.utils.formatters import normalize_to_e164


@dataclass(frozen=True)
class Row:
    user_id: uuid.UUID
    phone_raw: str
    phone_e164: str | None
    error: str | None


def _iter_users() -> Iterable[User]:
    return db.session.query(User).order_by(User.created_at.asc()).all()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize users.phone_number to E.164 (+<countrycode>...) with duplicate detection."
    )
    parser.add_argument("--apply", action="store_true", help="Apply changes to DB (default: dry-run only)")
    parser.add_argument(
        "--allow-duplicates", action="store_true", help="Do not fail on duplicates (still reports them)"
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit number of users processed (0 = all)")
    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        users = list(_iter_users())
        if args.limit and args.limit > 0:
            users = users[: args.limit]

        rows: list[Row] = []
        for u in users:
            raw = (getattr(u, "phone_number", None) or "").strip()
            if not raw:
                rows.append(Row(u.id, raw, None, "empty"))
                continue
            try:
                e164 = normalize_to_e164(raw)
                rows.append(Row(u.id, raw, e164, None))
            except Exception as e:  # noqa: BLE001
                rows.append(Row(u.id, raw, None, str(e)))

        invalid = [r for r in rows if r.error]
        normalized = [r for r in rows if (not r.error) and r.phone_e164]

        by_e164: dict[str, list[Row]] = {}
        for r in normalized:
            by_e164.setdefault(r.phone_e164 or "", []).append(r)

        duplicates = {k: v for k, v in by_e164.items() if k and len({x.user_id for x in v}) > 1}

        changes = [r for r in normalized if r.phone_raw != (r.phone_e164 or "")]

        print("== Phone normalization report ==")
        print(f"Total users scanned : {len(rows)}")
        print(f"Valid E.164         : {len(normalized)}")
        print(f"Invalid/empty       : {len(invalid)}")
        print(f"Would change        : {len(changes)}")
        print(f"Duplicates (E.164)  : {len(duplicates)}")
        print(f"Mode               : {'APPLY' if args.apply else 'DRY-RUN'}")

        if invalid:
            print("\n-- Invalid numbers (first 50) --")
            for r in invalid[:50]:
                print(f"- id={str(r.user_id)} phone={r.phone_raw!r} error={r.error}")

        if duplicates:
            print("\n-- Duplicates (E.164) (first 50 groups) --")
            for e164, group in list(duplicates.items())[:50]:
                ids = ", ".join(sorted({str(g.user_id) for g in group}))
                raws = ", ".join(sorted({g.phone_raw for g in group}))
                print(f"- e164={e164} ids=[{ids}] raws=[{raws}]")

        if not args.apply:
            return 0

        if duplicates and (not args.allow_duplicates):
            print("\nERROR: duplicates detected; refusing to apply. Re-run with --allow-duplicates to override.")
            return 2

        if not changes:
            print("\nNo changes to apply.")
            return 0

        updated = 0
        for r in changes:
            u = db.session.get(User, r.user_id)
            if not u:
                continue
            u.phone_number = r.phone_e164 or u.phone_number
            updated += 1

        db.session.commit()
        print(f"\nApplied updates: {updated}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
