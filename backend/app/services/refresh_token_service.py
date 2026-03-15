from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional

from flask import current_app

from app.extensions import db
from app.infrastructure.db.models import RefreshToken
from app.utils.request_utils import get_client_ip


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@dataclass
class RefreshResult:
    user_id: str
    new_refresh_token: Optional[str]


def _normalize_user_agent(user_agent: Optional[str]) -> Optional[str]:
    if not user_agent:
        return None
    normalized = user_agent[:255].strip()
    return normalized or None


def _get_refresh_expiry_days() -> int:
    days = int(current_app.config.get("REFRESH_TOKEN_EXPIRES_DAYS", 30) or 30)
    if days <= 0:
        return 30
    return days


def _get_refresh_reuse_grace_seconds() -> int:
    raw_value = current_app.config.get("REFRESH_TOKEN_REUSE_GRACE_SECONDS", 5)
    try:
        grace_seconds = int(raw_value)
    except (TypeError, ValueError):
        return 5
    return max(0, grace_seconds)


def _get_client_ip_safely() -> Optional[str]:
    try:
        return get_client_ip()
    except Exception:
        return None


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt_timezone.utc)
    return value.astimezone(dt_timezone.utc)


def _reuse_recently_rotated_refresh_token(
    *, token_hash: str, now: datetime, user_agent: Optional[str], client_ip: Optional[str]
) -> Optional[RefreshResult]:
    grace_seconds = _get_refresh_reuse_grace_seconds()
    if grace_seconds <= 0:
        return None

    existing = (
        db.session.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.isnot(None),
            RefreshToken.replaced_by_id.isnot(None),
        )
        .first()
    )

    if not existing or not existing.revoked_at or not existing.replaced_by_id:
        return None

    revoked_at = _ensure_utc(existing.revoked_at)
    if now - revoked_at > timedelta(seconds=grace_seconds):
        return None

    replacement = db.session.get(RefreshToken, existing.replaced_by_id)
    if not replacement or replacement.revoked_at is not None:
        return None

    if _ensure_utc(replacement.expires_at) <= now:
        return None

    normalized_user_agent = _normalize_user_agent(user_agent)
    replacement_user_agent = _normalize_user_agent(replacement.user_agent)
    if normalized_user_agent and replacement_user_agent and replacement_user_agent != normalized_user_agent:
        return None

    if client_ip and replacement.ip_address and replacement.ip_address != client_ip:
        return None

    current_app.logger.info(
        "Accepted recent refresh-token reuse within grace window: user_id=%s replacement_id=%s",
        existing.user_id,
        replacement.id,
    )
    return RefreshResult(user_id=str(replacement.user_id), new_refresh_token=None)


def issue_refresh_token_for_user(user_id, user_agent: Optional[str] = None) -> str:
    """Issue a new refresh token (raw) and persist its hash."""
    raw = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw)

    now = datetime.now(dt_timezone.utc)
    days = _get_refresh_expiry_days()
    expires_at = now + timedelta(days=days)

    ip_address = _get_client_ip_safely()

    rt = RefreshToken()
    rt.user_id = user_id
    rt.token_hash = token_hash
    rt.issued_at = now
    rt.expires_at = expires_at
    rt.ip_address = ip_address
    rt.user_agent = _normalize_user_agent(user_agent)

    db.session.add(rt)
    db.session.flush()
    db.session.commit()
    return raw


def rotate_refresh_token(raw_token: str, user_agent: Optional[str] = None) -> Optional[RefreshResult]:
    """Rotate refresh token (single-use). Returns new refresh token + user_id if valid."""
    if not raw_token or not isinstance(raw_token, str):
        return None

    now = datetime.now(dt_timezone.utc)
    token_hash = _hash_token(raw_token)
    normalized_user_agent = _normalize_user_agent(user_agent)
    client_ip = _get_client_ip_safely()

    existing = (
        db.session.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .first()
    )

    if not existing:
        return _reuse_recently_rotated_refresh_token(
            token_hash=token_hash,
            now=now,
            user_agent=normalized_user_agent,
            client_ip=client_ip,
        )

    # Revoke old token and mint a new one.
    new_raw = secrets.token_urlsafe(48)
    new_hash = _hash_token(new_raw)

    days = _get_refresh_expiry_days()
    expires_at = now + timedelta(days=days)

    replacement = RefreshToken()
    replacement.user_id = existing.user_id
    replacement.token_hash = new_hash
    replacement.issued_at = now
    replacement.expires_at = expires_at
    replacement.ip_address = client_ip
    replacement.user_agent = normalized_user_agent

    db.session.add(replacement)
    db.session.flush()

    existing.revoked_at = now
    existing.replaced_by_id = replacement.id

    db.session.commit()

    return RefreshResult(user_id=str(existing.user_id), new_refresh_token=new_raw)


def revoke_refresh_token(raw_token: str) -> bool:
    if not raw_token or not isinstance(raw_token, str):
        return False

    now = datetime.now(dt_timezone.utc)
    token_hash = _hash_token(raw_token)

    existing = (
        db.session.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
        )
        .first()
    )

    if not existing:
        return False

    existing.revoked_at = now
    db.session.commit()
    return True
