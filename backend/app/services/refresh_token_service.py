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
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


@dataclass
class RefreshResult:
    user_id: str
    new_refresh_token: str


def issue_refresh_token_for_user(user_id, user_agent: Optional[str] = None) -> str:
    """Issue a new refresh token (raw) and persist its hash."""
    raw = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw)

    now = datetime.now(dt_timezone.utc)
    days = int(current_app.config.get('REFRESH_TOKEN_EXPIRES_DAYS', 30) or 30)
    if days <= 0:
        days = 30
    expires_at = now + timedelta(days=days)

    ip_address = None
    try:
        ip_address = get_client_ip()
    except Exception:
        ip_address = None

    rt = RefreshToken()
    rt.user_id = user_id
    rt.token_hash = token_hash
    rt.issued_at = now
    rt.expires_at = expires_at
    rt.ip_address = ip_address
    rt.user_agent = (user_agent[:255] if user_agent else None)

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

    existing = db.session.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked_at.is_(None),
        RefreshToken.expires_at > now,
    ).first()

    if not existing:
        return None

    # Revoke old token and mint a new one.
    new_raw = secrets.token_urlsafe(48)
    new_hash = _hash_token(new_raw)

    days = int(current_app.config.get('REFRESH_TOKEN_EXPIRES_DAYS', 30) or 30)
    if days <= 0:
        days = 30
    expires_at = now + timedelta(days=days)

    ip_address = None
    try:
        ip_address = get_client_ip()
    except Exception:
        ip_address = None

    replacement = RefreshToken()
    replacement.user_id = existing.user_id
    replacement.token_hash = new_hash
    replacement.issued_at = now
    replacement.expires_at = expires_at
    replacement.ip_address = ip_address
    replacement.user_agent = (user_agent[:255] if user_agent else None)

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

    existing = db.session.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked_at.is_(None),
    ).first()

    if not existing:
        return False

    existing.revoked_at = now
    db.session.commit()
    return True
