from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

from flask import current_app
from jose import jwt


def create_access_token(data: dict) -> str:
    to_encode = dict(data or {})
    expire_minutes = int(current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", 30) or 30)
    if expire_minutes <= 0:
        expire_minutes = 30

    expire_at_utc = datetime.now(dt_timezone.utc) + timedelta(minutes=expire_minutes)
    to_encode.update(
        {
            "exp": expire_at_utc,
            "iat": datetime.now(dt_timezone.utc),
        }
    )
    return jwt.encode(
        to_encode,
        current_app.config["JWT_SECRET_KEY"],
        algorithm=current_app.config["JWT_ALGORITHM"],
    )
