from typing import Any, Optional

from flask import current_app


def build_webhook_idempotency_key(payload: dict[str, Any]) -> Optional[str]:
    order_id = payload.get("order_id")
    status_code = payload.get("status_code")
    transaction_status = payload.get("transaction_status")
    transaction_id = payload.get("transaction_id")
    if not order_id or not status_code or not transaction_status:
        return None
    token = transaction_id or "no_trx_id"
    return f"midtrans:webhook:{order_id}:{transaction_status}:{status_code}:{token}"


def is_duplicate_webhook(payload: dict[str, Any]) -> bool:
    redis_client = getattr(current_app, "redis_client_otp", None)
    if redis_client is None:
        return False
    key = build_webhook_idempotency_key(payload)
    if not key:
        return False
    try:
        ttl_seconds = int(current_app.config.get("MIDTRANS_WEBHOOK_IDEMPOTENCY_TTL_SECONDS", 86400))
    except Exception:
        ttl_seconds = 86400
    try:
        inserted = redis_client.set(key, "1", ex=ttl_seconds, nx=True)
        return inserted is None
    except Exception:
        return False


def _build_order_effect_done_key(*, order_id: str, effect_name: str) -> str:
    return f"midtrans:effect:done:{effect_name}:{order_id}"


def _build_order_effect_lock_key(*, order_id: str, effect_name: str) -> str:
    return f"midtrans:effect:lock:{effect_name}:{order_id}"


def begin_order_effect(*, order_id: str, effect_name: str = "hotspot_apply") -> tuple[bool, str | None]:
    redis_client = getattr(current_app, "redis_client_otp", None)
    if redis_client is None:
        return True, None

    done_key = _build_order_effect_done_key(order_id=order_id, effect_name=effect_name)
    lock_key = _build_order_effect_lock_key(order_id=order_id, effect_name=effect_name)

    try:
        if redis_client.get(done_key) is not None:
            return False, None
    except Exception:
        return True, None

    try:
        lock_ttl = int(current_app.config.get("MIDTRANS_ORDER_EFFECT_LOCK_TTL_SECONDS", 300))
    except Exception:
        lock_ttl = 300
    lock_ttl = max(30, min(lock_ttl, 3600))

    try:
        inserted = redis_client.set(lock_key, "1", ex=lock_ttl, nx=True)
        if inserted is None:
            return False, None
        return True, lock_key
    except Exception:
        return True, None


def finish_order_effect(
    *,
    order_id: str,
    lock_key: str | None,
    success: bool,
    effect_name: str = "hotspot_apply",
) -> None:
    redis_client = getattr(current_app, "redis_client_otp", None)
    if redis_client is None:
        return

    done_key = _build_order_effect_done_key(order_id=order_id, effect_name=effect_name)

    if success:
        try:
            done_ttl = int(current_app.config.get("MIDTRANS_ORDER_EFFECT_DONE_TTL_SECONDS", 7 * 24 * 3600))
        except Exception:
            done_ttl = 7 * 24 * 3600
        done_ttl = max(600, min(done_ttl, 30 * 24 * 3600))
        try:
            redis_client.set(done_key, "1", ex=done_ttl)
        except Exception:
            pass

    if lock_key:
        try:
            redis_client.delete(lock_key)
        except Exception:
            pass
