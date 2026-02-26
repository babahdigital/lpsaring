from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any, Dict, Optional

import midtransclient
from flask import current_app


def get_midtrans_core_api_client():
    is_production = current_app.config.get("MIDTRANS_IS_PRODUCTION", False)
    server_key = current_app.config.get("MIDTRANS_SERVER_KEY")
    if not server_key:
        raise ValueError("MIDTRANS_SERVER_KEY configuration is missing.")
    client = midtransclient.CoreApi(is_production=is_production, server_key=server_key)
    timeout_seconds = int(current_app.config.get("MIDTRANS_HTTP_TIMEOUT_SECONDS", 15))
    if hasattr(client, "timeout"):
        client.timeout = timeout_seconds  # type: ignore[attr-defined]
    if hasattr(client, "http_client") and hasattr(client.http_client, "timeout"):
        client.http_client.timeout = timeout_seconds  # type: ignore[attr-defined]
    return client


def get_midtrans_snap_client():
    is_production = current_app.config.get("MIDTRANS_IS_PRODUCTION", False)
    server_key = current_app.config.get("MIDTRANS_SERVER_KEY")
    client_key = current_app.config.get("MIDTRANS_CLIENT_KEY")
    if not server_key or not client_key:
        raise ValueError("MIDTRANS_SERVER_KEY atau MIDTRANS_CLIENT_KEY configuration is missing.")
    client = midtransclient.Snap(is_production=is_production, server_key=server_key, client_key=client_key)
    timeout_seconds = int(current_app.config.get("MIDTRANS_HTTP_TIMEOUT_SECONDS", 15))
    if hasattr(client, "timeout"):
        client.timeout = timeout_seconds  # type: ignore[attr-defined]
    if hasattr(client, "http_client") and hasattr(client.http_client, "timeout"):
        client.http_client.timeout = timeout_seconds  # type: ignore[attr-defined]
    return client


def safe_parse_midtrans_datetime(dt_string: Optional[str]):
    if not dt_string:
        return None
    try:
        naive_dt = datetime.strptime(dt_string, "%Y-%m-%d %H:%M:%S")
        offset_hours = int(current_app.config.get("MIDTRANS_DATETIME_INPUT_OFFSET_HOURS", 7))
        return naive_dt.replace(tzinfo=dt_timezone(timedelta(hours=offset_hours))).astimezone(dt_timezone.utc)
    except (ValueError, TypeError):
        return None


def extract_va_number(response_data: Dict[str, Any]):
    va_numbers = response_data.get("va_numbers")
    if isinstance(va_numbers, list) and len(va_numbers) > 0:
        for va_info in va_numbers:
            if isinstance(va_info, dict) and va_info.get("va_number"):
                return str(va_info.get("va_number")).strip()
    specific_fields = [
        "permata_va_number",
        "bca_va_number",
        "bni_va_number",
        "bri_va_number",
        "cimb_va_number",
        "va_number",
    ]
    for field in specific_fields:
        if field_value := response_data.get(field):
            return str(field_value).strip()
    return None


def extract_qr_code_url(response_data: Dict[str, Any]):
    actions = response_data.get("actions")
    if isinstance(actions, list):
        for action in actions:
            action_name = str(action.get("name", "")).lower()
            qr_url = action.get("url")
            if qr_url and "generate-qr-code-v2" in action_name:
                return qr_url
        for action in actions:
            action_name = action.get("name", "").lower()
            qr_url = action.get("url")
            if qr_url and "generate-qr-code" in action_name:
                return qr_url
    return response_data.get("qr_code_url")


def is_qr_payment_type(payment_type: str | None) -> bool:
    pt = str(payment_type or "").strip().lower()
    return pt in {"qris", "gopay", "shopeepay"}


def extract_action_url(response_data: Dict[str, Any], *, action_name_contains: str) -> str | None:
    needle = str(action_name_contains or "").strip().lower()
    if needle == "":
        return None
    actions = response_data.get("actions")
    if not isinstance(actions, list):
        return None
    for action in actions:
        if not isinstance(action, dict):
            continue
        name = str(action.get("name", "")).strip().lower()
        url = action.get("url")
        if url and needle in name:
            return str(url).strip()
    return None
