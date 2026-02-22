import itsdangerous
from flask import current_app


def _get_serializer() -> itsdangerous.URLSafeTimedSerializer:
    secret_key = current_app.config.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY tidak disetel")
    return itsdangerous.URLSafeTimedSerializer(secret_key, salt="telegram-user-link")


def generate_user_link_token(*, user_id: str) -> str:
    s = _get_serializer()
    return s.dumps({"uid": user_id})


def verify_user_link_token(token: str, *, max_age_seconds: int) -> str | None:
    if not isinstance(token, str) or not token.strip():
        return None
    s = _get_serializer()
    try:
        payload = s.loads(token, max_age=max_age_seconds)
    except (itsdangerous.SignatureExpired, itsdangerous.BadTimeSignature, itsdangerous.BadSignature):
        return None

    uid = payload.get("uid") if isinstance(payload, dict) else None
    if not isinstance(uid, str) or not uid:
        return None
    return uid
