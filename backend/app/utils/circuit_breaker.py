import json
import time

try:
    from flask import current_app
except Exception:  # pragma: no cover - fallback for contexts without Flask
    current_app = None

_in_memory_state = {}


def _now() -> int:
    return int(time.time())


def _get_config(key: str, default: int) -> int:
    if current_app:
        try:
            value = current_app.config.get(key, default)
            return int(value)
        except Exception:
            return default
    return default


def _get_storage():
    if current_app:
        redis_client = getattr(current_app, "redis_client_otp", None)
        if redis_client is not None:
            return redis_client
    return None


def _get_key(name: str, suffix: str) -> str:
    return f"cb:{name}:{suffix}"


def _get_state(name: str) -> dict:
    storage = _get_storage()
    if storage is None:
        return _in_memory_state.get(name, {"fail": 0, "open_until": 0, "half_open": 0, "half_open_success": 0})

    try:
        raw = storage.get(_get_key(name, "state"))
        if raw:
            return json.loads(raw)
    except Exception:
        return {"fail": 0, "open_until": 0, "half_open": 0, "half_open_success": 0}

    return {"fail": 0, "open_until": 0, "half_open": 0, "half_open_success": 0}


def _set_state(name: str, state: dict) -> None:
    storage = _get_storage()
    if storage is None:
        _in_memory_state[name] = state
        return

    try:
        storage.set(_get_key(name, "state"), json.dumps(state), ex=3600)
    except Exception:
        _in_memory_state[name] = state


def should_allow_call(name: str) -> bool:
    state = _get_state(name)
    now = _now()
    open_until = int(state.get("open_until", 0) or 0)
    if open_until and now < open_until:
        return False

    if open_until and now >= open_until:
        state["half_open"] = 1
        state["half_open_success"] = 0
        state["open_until"] = 0
        _set_state(name, state)

    return True


def record_success(name: str) -> None:
    state = _get_state(name)
    if int(state.get("half_open", 0)) == 1:
        state["half_open_success"] = int(state.get("half_open_success", 0)) + 1
        required = _get_config("CIRCUIT_BREAKER_HALF_OPEN_SUCCESS", 2)
        if state["half_open_success"] >= required:
            state = {"fail": 0, "open_until": 0, "half_open": 0, "half_open_success": 0}
            _set_state(name, state)
            return

    state["fail"] = 0
    state["open_until"] = 0
    state["half_open"] = 0
    state["half_open_success"] = 0
    _set_state(name, state)


def record_failure(name: str) -> None:
    state = _get_state(name)
    threshold = _get_config("CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5)
    reset_seconds = _get_config("CIRCUIT_BREAKER_RESET_SECONDS", 60)

    if int(state.get("half_open", 0)) == 1:
        state["open_until"] = _now() + reset_seconds
        state["fail"] = 0
        state["half_open"] = 0
        state["half_open_success"] = 0
        _set_state(name, state)
        return

    state["fail"] = int(state.get("fail", 0)) + 1
    if state["fail"] >= threshold:
        state["open_until"] = _now() + reset_seconds
        state["fail"] = 0
        state["half_open"] = 0
        state["half_open_success"] = 0

    _set_state(name, state)
