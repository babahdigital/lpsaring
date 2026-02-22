from __future__ import annotations

from flask import Blueprint, jsonify, request, current_app
from http import HTTPStatus
from datetime import datetime, timezone
import uuid

from app.extensions import db
from app.infrastructure.db.models import User
from app.services import settings_service
from app.services.telegram_link_service import verify_user_link_token


telegram_bp = Blueprint("telegram_api", __name__, url_prefix="/api/telegram")


def _get_webhook_secret() -> str:
    return str(settings_service.get_setting("TELEGRAM_WEBHOOK_SECRET", "") or "").strip()


def _is_webhook_secret_valid() -> bool:
    expected = _get_webhook_secret()
    if not expected:
        return False
    provided = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
    return provided == expected


@telegram_bp.route("/webhook", methods=["POST"])
def telegram_webhook():
    if not _is_webhook_secret_valid():
        return jsonify({"message": "Unauthorized webhook."}), HTTPStatus.FORBIDDEN

    update = request.get_json(silent=True) or {}
    message = update.get("message") or update.get("edited_message") or {}
    text = str(message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id_raw = chat.get("id")
    from_user = message.get("from") or {}
    telegram_username = from_user.get("username")

    if not text or chat_id_raw is None:
        return jsonify({"ok": True}), HTTPStatus.OK

    # Expect: /start <token>
    if not text.startswith("/start"):
        return jsonify({"ok": True}), HTTPStatus.OK

    parts = text.split(maxsplit=1)
    token = parts[1].strip() if len(parts) > 1 else ""
    if not token:
        return jsonify({"ok": True}), HTTPStatus.OK

    max_age = int(current_app.config.get("TELEGRAM_LINK_TOKEN_MAX_AGE_SECONDS", 600))
    user_id_str = verify_user_link_token(token, max_age_seconds=max_age)
    if not user_id_str:
        return jsonify({"ok": True}), HTTPStatus.OK

    try:
        user_id = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        return jsonify({"ok": True}), HTTPStatus.OK

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"ok": True}), HTTPStatus.OK

    user.telegram_chat_id = str(chat_id_raw)
    if isinstance(telegram_username, str) and telegram_username.strip():
        user.telegram_username = telegram_username.strip()
    user.telegram_linked_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({"ok": True}), HTTPStatus.OK
