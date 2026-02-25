from __future__ import annotations

from http import HTTPStatus
from typing import Any

from flask import current_app, has_request_context, jsonify, request


def get_request_id() -> str | None:
    if not has_request_context():
        return None
    try:
        request_id = request.environ.get("FLASK_REQUEST_ID")
        if isinstance(request_id, str):
            request_id = request_id.strip()
            return request_id or None
    except Exception:
        return None
    return None


def build_error_payload(
    message: str,
    *,
    status_code: int,
    code: str | None = None,
    details: Any = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": False,
        "error": message,
        "message": message,
        "status_code": int(status_code),
    }

    normalized_code = str(code).strip() if isinstance(code, str) and code.strip() else f"HTTP_{int(status_code)}"
    payload["code"] = normalized_code

    if details is not None:
        payload["details"] = details

    request_id = get_request_id()
    if request_id:
        payload["request_id"] = request_id

    if isinstance(extra, dict):
        for key, value in extra.items():
            if value is not None:
                payload[key] = value

    return payload


def error_response(
    message: str,
    *,
    status_code: int | HTTPStatus,
    code: str | None = None,
    details: Any = None,
    extra: dict[str, Any] | None = None,
):
    http_status = int(status_code)
    payload = build_error_payload(
        message,
        status_code=http_status,
        code=code,
        details=details,
        extra=extra,
    )
    return jsonify(payload), http_status


def error_response_from_http_exception(error):
    status_code = int(getattr(error, "code", HTTPStatus.INTERNAL_SERVER_ERROR) or HTTPStatus.INTERNAL_SERVER_ERROR)
    message = getattr(error, "description", None) or getattr(error, "name", None) or "Internal server error."
    payload = build_error_payload(message, status_code=status_code)
    return jsonify(payload), status_code


def error_response_internal(message: str = "Internal server error."):
    if current_app:
        current_app.logger.debug("error_response_internal called with message=%s", message)
    return error_response(message, status_code=HTTPStatus.INTERNAL_SERVER_ERROR)
