from __future__ import annotations

import hmac
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any, Optional

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db, limiter
from app.infrastructure.db.models import User
from app.infrastructure.http.auth_contexts.shared_helpers import get_redis_client_otp
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
    return hmac.compare_digest(provided, expected)


def _claim_update_id(update_id: Optional[int]) -> bool:
    """C7: Dedup via Redis SETNX. Return True jika klaim sukses (belum dipakai)."""
    if update_id is None:
        return True  # No update_id → cannot dedup, allow but log later
    client: Any = get_redis_client_otp()
    if client is None:
        return True  # Redis unavailable → fail-open (do not block legitimate webhook)
    try:
        key = f"tg:webhook:dedup:{int(update_id)}"
        ttl = int(current_app.config.get("TELEGRAM_WEBHOOK_DEDUP_TTL_SECONDS", 3600))
        acquired = client.set(key, "1", nx=True, ex=ttl)
        return bool(acquired)
    except Exception as exc:
        current_app.logger.warning("Telegram webhook dedup Redis error: %s", exc)
        return True  # fail-open


@telegram_bp.route("/webhook", methods=["POST"])
@limiter.limit(lambda: current_app.config.get("TELEGRAM_WEBHOOK_RATE_LIMIT", "60 per minute"))
def telegram_webhook():
    if not _is_webhook_secret_valid():
        return jsonify({"message": "Unauthorized webhook."}), HTTPStatus.FORBIDDEN

    update = request.get_json(silent=True) or {}
    update_id = update.get("update_id") if isinstance(update, dict) else None

    # C7: Idempotent update_id dedup — Telegram bisa retry webhook delivery.
    if not _claim_update_id(update_id if isinstance(update_id, int) else None):
        current_app.logger.info("Telegram webhook duplicate update_id=%s — skipped.", update_id)
        return jsonify({"ok": True, "deduped": True}), HTTPStatus.OK

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

    chat_id_str = str(chat_id_raw)

    # C3: Lock the row before reading current state untuk hindari race link-concurrent.
    try:
        user = db.session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one_or_none()
    except Exception as exc_lock:
        current_app.logger.warning("Telegram link FOR UPDATE gagal: %s — fallback non-locked", exc_lock)
        user = db.session.get(User, user_id)

    if not user:
        return jsonify({"ok": True}), HTTPStatus.OK

    # C1: Idempotent — kalau user sudah ter-link dengan chat_id yang SAMA, anggap OK.
    if user.telegram_chat_id:
        if user.telegram_chat_id == chat_id_str:
            current_app.logger.info(
                "Telegram /start re-issued untuk user=%s chat=%s (no-op).",
                user_id,
                chat_id_str,
            )
            # Optional: refresh username kalau berubah supaya tetap akurat.
            if (
                isinstance(telegram_username, str)
                and telegram_username.strip()
                and user.telegram_username != telegram_username.strip()
            ):
                user.telegram_username = telegram_username.strip()
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
            return jsonify({"ok": True, "already_linked": True}), HTTPStatus.OK

        # User sudah linked tapi ke chat_id BERBEDA → tolak re-bind diam-diam, supaya
        # admin perlu unlink eksplisit dulu (cegah hijack jika token bocor lewat akun lain).
        current_app.logger.warning(
            "Telegram /start blocked: user=%s sudah linked ke chat=%s, request chat=%s",
            user_id,
            user.telegram_chat_id,
            chat_id_str,
        )
        return jsonify({"ok": True, "blocked": "already_linked_other_chat"}), HTTPStatus.OK

    # C1: cek apakah chat_id ini sudah dipakai user LAIN (cegah cross-link sebelum
    # UniqueConstraint partial index ikut bekerja). Tidak FOR UPDATE — kita hanya
    # butuh existence check; UniqueConstraint akan jadi safety net pada commit.
    other = db.session.execute(select(User.id).where(User.telegram_chat_id == chat_id_str)).scalar_one_or_none()
    if other is not None and other != user_id:
        current_app.logger.warning(
            "Telegram /start blocked: chat=%s sudah dipakai user lain=%s (request user=%s)",
            chat_id_str,
            other,
            user_id,
        )
        return jsonify({"ok": True, "blocked": "chat_already_linked_other_user"}), HTTPStatus.OK

    user.telegram_chat_id = chat_id_str
    if isinstance(telegram_username, str) and telegram_username.strip():
        user.telegram_username = telegram_username.strip()
    user.telegram_linked_at = datetime.now(timezone.utc)

    try:
        db.session.commit()
    except IntegrityError as exc_int:
        # Race: orang lain klaim chat_id sama dalam window — partial unique index trigger.
        db.session.rollback()
        current_app.logger.warning(
            "Telegram link IntegrityError user=%s chat=%s: %s",
            user_id,
            chat_id_str,
            exc_int,
        )
        return jsonify({"ok": True, "blocked": "race_conflict"}), HTTPStatus.OK
    except Exception as exc_commit:
        db.session.rollback()
        current_app.logger.error("Telegram link commit gagal user=%s: %s", user_id, exc_commit, exc_info=True)
        return jsonify({"ok": True}), HTTPStatus.OK

    return jsonify({"ok": True}), HTTPStatus.OK
