from __future__ import annotations

from typing import Any

import requests
from flask import current_app

from app.services import settings_service
from app.utils.circuit_breaker import record_failure, record_success, should_allow_call


def _get_api_base_url() -> str:
    value = settings_service.get_setting("TELEGRAM_API_BASE_URL", "https://api.telegram.org")
    base = str(value or "https://api.telegram.org").strip()
    return base.rstrip("/")


def _get_bot_token() -> str:
    token = settings_service.get_setting("TELEGRAM_BOT_TOKEN")
    return str(token or "").strip()


def send_telegram_message(chat_id: str, text: str) -> bool:
    chat_id_value = str(chat_id or "").strip()
    message_text = str(text or "").strip()

    if not chat_id_value:
        current_app.logger.error("Telegram chat_id kosong, skip kirim.")
        return False
    if not message_text:
        current_app.logger.warning("Telegram message kosong, skip kirim.")
        return False

    bot_token = _get_bot_token()
    if not bot_token:
        current_app.logger.error("TELEGRAM_BOT_TOKEN belum dikonfigurasi.")
        return False

    if not should_allow_call("telegram"):
        current_app.logger.warning("Telegram circuit breaker open. Skipping send.")
        return False

    api_base = _get_api_base_url()
    url = f"{api_base}/bot{bot_token}/sendMessage"

    payload: dict[str, Any] = {
        "chat_id": chat_id_value,
        "text": message_text,
        "disable_web_page_preview": True,
    }

    try:
        timeout_seconds = int(settings_service.get_setting("TELEGRAM_HTTP_TIMEOUT_SECONDS", "15") or 15)
    except Exception:
        timeout_seconds = 15

    current_app.logger.info("Attempting to send Telegram message to chat_id=%s (base=%s)", chat_id_value, api_base)

    try:
        response = requests.post(url, json=payload, timeout=timeout_seconds)
        if not (200 <= response.status_code < 300):
            current_app.logger.warning(
                "Telegram API returned non-2xx: status=%s body=%s",
                response.status_code,
                (response.text or "")[:300],
            )

        try:
            response_json = response.json()
        except ValueError:
            response_json = None

        if isinstance(response_json, dict) and response_json.get("ok") is True:
            record_success("telegram")
            return True

        record_failure("telegram")
        description = None
        if isinstance(response_json, dict):
            description = response_json.get("description")
        if isinstance(description, str) and description:
            current_app.logger.error("Telegram send failed: %s", description)
        return False

    except requests.exceptions.Timeout:
        current_app.logger.error("Timeout error sending Telegram message to chat_id=%s.", chat_id_value)
        record_failure("telegram")
        return False
    except requests.exceptions.RequestException as e:
        current_app.logger.error("Error sending Telegram message: %s", e, exc_info=False)
        record_failure("telegram")
        return False
    except Exception as e:
        current_app.logger.error("Unexpected error sending Telegram message: %s", e, exc_info=True)
        record_failure("telegram")
        return False
