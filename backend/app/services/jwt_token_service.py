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
    now_utc = datetime.now(dt_timezone.utc)
    to_encode.update(
        {
            "exp": expire_at_utc,
            "iat": now_utc,
            # Sprint 6: iss/aud claims supaya token staging tidak bisa di-replay
            # ke prod walau JWT_SECRET_KEY bocor antar environment.
            "iss": current_app.config.get("JWT_ISSUER", "lpsaring-production"),
            "aud": current_app.config.get("JWT_AUDIENCE", "lpsaring-portal"),
        }
    )
    return jwt.encode(
        to_encode,
        current_app.config["JWT_SECRET_KEY"],
        algorithm=current_app.config["JWT_ALGORITHM"],
    )
