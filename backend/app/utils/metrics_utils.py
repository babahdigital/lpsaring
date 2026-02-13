import time
from typing import Dict

try:
    from flask import current_app
except Exception:  # pragma: no cover
    current_app = None

_in_memory_metrics = {}


def _now() -> int:
    return int(time.time())


def _get_storage():
    if current_app:
        redis_client = getattr(current_app, "redis_client_otp", None)
        if redis_client is not None:
            return redis_client
    return None


def _get_ttl() -> int:
    if current_app:
        try:
            return int(current_app.config.get("METRICS_TTL_SECONDS", 86400))
        except Exception:
            return 86400
    return 86400


def increment_metric(key: str, amount: int = 1) -> None:
    storage = _get_storage()
    ttl = _get_ttl()
    if storage is None:
        entry = _in_memory_metrics.get(key)
        if not entry or entry["expires_at"] < _now():
            _in_memory_metrics[key] = {"value": amount, "expires_at": _now() + ttl}
        else:
            entry["value"] += amount
        return

    try:
        storage.incrby(f"metrics:{key}", amount)
        storage.expire(f"metrics:{key}", ttl)
    except Exception:
        entry = _in_memory_metrics.get(key)
        if not entry or entry["expires_at"] < _now():
            _in_memory_metrics[key] = {"value": amount, "expires_at": _now() + ttl}
        else:
            entry["value"] += amount


def get_metrics(keys: list[str]) -> Dict[str, int]:
    storage = _get_storage()
    if storage is None:
        result = {}
        for key in keys:
            entry = _in_memory_metrics.get(key)
            if entry and entry["expires_at"] >= _now():
                result[key] = int(entry["value"])
            else:
                result[key] = 0
        return result

    result = {}
    try:
        for key in keys:
            raw = storage.get(f"metrics:{key}")
            result[key] = int(raw) if raw else 0
        return result
    except Exception:
        for key in keys:
            entry = _in_memory_metrics.get(key)
            if entry and entry["expires_at"] >= _now():
                result[key] = int(entry["value"])
            else:
                result[key] = 0
        return result
