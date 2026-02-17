"""Backfill SUCCESS transaction payment fields.

Tujuan:
- Mengisi field pembayaran yang kosong pada transaksi SUCCESS (payment_method, payment_time, expiry_time,
  va_number, payment_code, biller_code, qr_code_url, midtrans_transaction_id) dari:
  1) transactions.midtrans_notification_payload (json string), atau
  2) (opsional) Midtrans Core API status check per order_id.

Default aman: dry-run (tidak mengubah DB) kecuali --apply.

Contoh:
  python scripts/backfill_success_payment_fields.py --days 90
  python scripts/backfill_success_payment_fields.py --days 365 --apply
  python scripts/backfill_success_payment_fields.py --days 365 --apply --fetch-midtrans

Catatan:
- Script ini sebaiknya dijalankan di container backend produksi (docker compose exec).
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.infrastructure.db.models import Transaction, TransactionEvent, TransactionEventSource, TransactionStatus


def _safe_json_loads(value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _safe_parse_midtrans_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip()
    # Midtrans sering mengirim: "YYYY-MM-DD HH:MM:SS"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue

    # Fallback: datetime.fromisoformat
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _extract_va_number(payload: dict[str, Any]) -> str | None:
    va_numbers = payload.get("va_numbers")
    if isinstance(va_numbers, list) and va_numbers:
        first = va_numbers[0]
        if isinstance(first, dict):
            num = first.get("va_number")
            if isinstance(num, str) and num.strip():
                return num.strip()

    permata = payload.get("permata_va_number")
    if isinstance(permata, str) and permata.strip():
        return permata.strip()

    return None


def _extract_qr_code_url(payload: dict[str, Any]) -> str | None:
    actions = payload.get("actions")
    if isinstance(actions, list):
        for action in actions:
            if not isinstance(action, dict):
                continue
            url = action.get("url")
            if isinstance(url, str) and url.strip():
                # Midtrans QRIS biasanya punya action name: generate-qr-code
                return url.strip()

    # sebagian payload punya qr_string/qr_code_url berbeda-beda; simpan yang jelas URL saja.
    qr_url = payload.get("qr_code_url")
    if isinstance(qr_url, str) and qr_url.strip():
        return qr_url.strip()

    return None


def _log_event(session, tx: Transaction, changes: dict[str, Any], source: TransactionEventSource, event_type: str) -> None:
    ev = TransactionEvent()
    ev.transaction_id = tx.id
    ev.source = source
    ev.event_type = event_type
    ev.status = tx.status
    ev.payload = json.dumps(changes, ensure_ascii=False)
    session.add(ev)


def _get_midtrans_core_api_client():
    # Import di dalam fungsi agar script tetap bisa dipakai di env yang belum punya midtrans.
    import midtransclient
    from flask import current_app

    is_production = current_app.config.get("MIDTRANS_IS_PRODUCTION", False)
    server_key = current_app.config.get("MIDTRANS_SERVER_KEY")
    if not server_key:
        raise RuntimeError("MIDTRANS_SERVER_KEY belum disetel")

    client = midtransclient.CoreApi(is_production=is_production, server_key=server_key)
    timeout_seconds = int(current_app.config.get("MIDTRANS_HTTP_TIMEOUT_SECONDS", 15))
    if hasattr(client, "timeout"):
        client.timeout = timeout_seconds  # type: ignore[attr-defined]
    if hasattr(client, "http_client") and hasattr(client.http_client, "timeout"):
        client.http_client.timeout = timeout_seconds  # type: ignore[attr-defined]
    return client


def backfill(*, days: int, apply: bool, fetch_midtrans: bool, sleep_seconds: float) -> int:
    session = db.session

    since_dt = datetime.now(timezone.utc) - timedelta(days=max(1, days))

    # Target minimal: SUCCESS yang payment_method kosong ATAU payment_time kosong.
    query = (
        select(Transaction)
        .where(Transaction.status == TransactionStatus.SUCCESS)
        .where(Transaction.created_at >= since_dt)
        .order_by(Transaction.created_at.desc())
    )

    txs = session.scalars(query).all()

    inspected = 0
    updated = 0
    skipped = 0
    fetched = 0

    for tx in txs:
        inspected += 1

        needs = (
            tx.payment_method is None
            or tx.payment_method == ""
            or tx.payment_time is None
            or tx.midtrans_transaction_id is None
            or tx.midtrans_transaction_id == ""
        )

        if not needs:
            skipped += 1
            continue

        payload = _safe_json_loads(tx.midtrans_notification_payload or "")

        # optional fetch from Midtrans if payload absent
        if payload is None and fetch_midtrans:
            try:
                from flask import current_app

                if not current_app:
                    raise RuntimeError("Flask app context not available")

                core_api = _get_midtrans_core_api_client()
                payload = core_api.transactions.status(tx.midtrans_order_id)
                fetched += 1
                try:
                    tx.midtrans_notification_payload = json.dumps(payload, ensure_ascii=False)
                except Exception:
                    pass

                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
            except Exception:
                payload = None

        if payload is None:
            skipped += 1
            continue

        changes: dict[str, Any] = {}

        if (tx.payment_method is None or tx.payment_method == "") and isinstance(payload.get("payment_type"), str):
            changes["payment_method"] = payload.get("payment_type")

        if (tx.midtrans_transaction_id is None or tx.midtrans_transaction_id == "") and isinstance(payload.get("transaction_id"), str):
            changes["midtrans_transaction_id"] = payload.get("transaction_id")

        if tx.expiry_time is None:
            if parsed := _safe_parse_midtrans_datetime(payload.get("expiry_time")):
                changes["expiry_time"] = parsed

        if tx.payment_time is None:
            parsed = (
                _safe_parse_midtrans_datetime(payload.get("settlement_time"))
                or _safe_parse_midtrans_datetime(payload.get("transaction_time"))
            )
            if parsed is not None:
                changes["payment_time"] = parsed

        if tx.va_number is None:
            if va := _extract_va_number(payload):
                changes["va_number"] = va

        if tx.payment_code is None and isinstance(payload.get("payment_code"), str):
            changes["payment_code"] = payload.get("payment_code")

        if tx.biller_code is None and isinstance(payload.get("biller_code"), str):
            changes["biller_code"] = payload.get("biller_code")

        if tx.qr_code_url is None:
            if qr := _extract_qr_code_url(payload):
                changes["qr_code_url"] = qr

        if not changes:
            skipped += 1
            continue

        # Apply changes in-memory
        for k, v in changes.items():
            setattr(tx, k, v)

        _log_event(
            session,
            tx,
            {
                "action": "backfill_success_payment_fields",
                "changed": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in changes.items()},
                "source": "payload" if (tx.midtrans_notification_payload) else "unknown",
                "fetched_midtrans": fetch_midtrans,
            },
            TransactionEventSource.APP,
            "BACKFILL_SUCCESS_FIELDS",
        )

        updated += 1

        if apply:
            # commit per N items? keep it simple: batch every 100
            if updated % 100 == 0:
                session.commit()

    if apply:
        session.commit()
    else:
        session.rollback()

    print("Backfill summary")
    print(f"- inspected: {inspected}")
    print(f"- updated  : {updated}{' (applied)' if apply else ' (dry-run)'}")
    print(f"- fetched  : {fetched} (midtrans status calls)")
    print(f"- skipped  : {skipped}")

    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill SUCCESS transaction payment fields")
    parser.add_argument("--days", type=int, default=365, help="Lookback days window (default 365)")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default dry-run)")
    parser.add_argument(
        "--fetch-midtrans",
        action="store_true",
        help="If payload missing, fetch status from Midtrans Core API per order_id (rate-limited by --sleep)",
    )
    parser.add_argument("--sleep", type=float, default=0.25, help="Sleep seconds between Midtrans calls (default 0.25)")

    args = parser.parse_args()

    # Script requires Flask app context because app.extensions db is bound there.
    from app import create_app

    app = create_app()

    with app.app_context():
        backfill(days=args.days, apply=args.apply, fetch_midtrans=args.fetch_midtrans, sleep_seconds=args.sleep)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
