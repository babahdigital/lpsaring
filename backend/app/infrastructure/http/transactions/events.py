import json
import uuid

from app.infrastructure.db.models import Transaction, TransactionEvent, TransactionEventSource, TransactionStatus


def safe_json_dumps(value: object) -> str | None:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return None


def log_transaction_event(
    *,
    session,
    transaction: Transaction,
    source: TransactionEventSource,
    event_type: str,
    status: TransactionStatus | None = None,
    payload: object | None = None,
) -> None:
    ev = TransactionEvent()
    ev.id = uuid.uuid4()
    ev.transaction_id = transaction.id
    ev.source = source
    ev.event_type = event_type
    ev.status = status
    ev.payload = safe_json_dumps(payload) if payload is not None else None
    session.add(ev)
