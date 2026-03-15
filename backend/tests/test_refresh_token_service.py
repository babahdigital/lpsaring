from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from types import SimpleNamespace

from flask import Flask

from app.infrastructure.db.models import RefreshToken
from app.services import refresh_token_service


class _FakeQuery:
    def __init__(self, session, call_index: int):
        self._session = session
        self._call_index = call_index

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        if self._call_index == 1:
            return self._session.active_token
        if self._call_index == 2:
            return self._session.recently_replaced_token
        return None


class _FakeSession:
    def __init__(self, *, active_token=None, recently_replaced_token=None, replacement_tokens=None):
        self.active_token = active_token
        self.recently_replaced_token = recently_replaced_token
        self.replacement_tokens = replacement_tokens or {}
        self.query_calls = 0
        self.added: list[RefreshToken] = []
        self.flush_calls = 0
        self.commit_calls = 0

    def query(self, _model):
        self.query_calls += 1
        return _FakeQuery(self, self.query_calls)

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flush_calls += 1
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    def commit(self):
        self.commit_calls += 1

    def get(self, _model, key):
        return self.replacement_tokens.get(key)


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["REFRESH_TOKEN_EXPIRES_DAYS"] = 30
    app.config["REFRESH_TOKEN_REUSE_GRACE_SECONDS"] = 5
    return app


def test_rotate_refresh_token_rotates_active_token(monkeypatch):
    user_id = uuid.uuid4()
    existing = RefreshToken()
    existing.id = uuid.uuid4()
    existing.user_id = user_id
    existing.token_hash = "hash:stale-refresh"
    existing.expires_at = datetime.now(dt_timezone.utc) + timedelta(days=1)
    existing.revoked_at = None

    session = _FakeSession(active_token=existing)
    monkeypatch.setattr(refresh_token_service, "db", SimpleNamespace(session=session))
    monkeypatch.setattr(refresh_token_service, "_hash_token", lambda raw: f"hash:{raw}")
    monkeypatch.setattr(refresh_token_service, "_get_client_ip_safely", lambda: "172.16.2.59")
    monkeypatch.setattr(refresh_token_service.secrets, "token_urlsafe", lambda _n: "rotated-refresh")

    app = _make_app()
    with app.app_context():
        result = refresh_token_service.rotate_refresh_token("stale-refresh", user_agent="UA/1.0")

    assert result is not None
    assert result.user_id == str(user_id)
    assert result.new_refresh_token == "rotated-refresh"
    assert existing.revoked_at is not None
    assert existing.replaced_by_id is not None
    assert session.commit_calls == 1
    assert len(session.added) == 1

    replacement = session.added[0]
    assert replacement.user_id == user_id
    assert replacement.token_hash == "hash:rotated-refresh"
    assert replacement.ip_address == "172.16.2.59"
    assert replacement.user_agent == "UA/1.0"


def test_rotate_refresh_token_allows_recent_reuse_without_minting_new_refresh(monkeypatch):
    user_id = uuid.uuid4()
    replacement = RefreshToken()
    replacement.id = uuid.uuid4()
    replacement.user_id = user_id
    replacement.expires_at = datetime.now(dt_timezone.utc) + timedelta(days=1)
    replacement.revoked_at = None
    replacement.ip_address = "172.16.2.59"
    replacement.user_agent = "UA/1.0"

    existing = RefreshToken()
    existing.id = uuid.uuid4()
    existing.user_id = user_id
    existing.token_hash = "hash:stale-refresh"
    existing.revoked_at = datetime.now(dt_timezone.utc) - timedelta(seconds=2)
    existing.replaced_by_id = replacement.id

    session = _FakeSession(
        active_token=None,
        recently_replaced_token=existing,
        replacement_tokens={replacement.id: replacement},
    )
    monkeypatch.setattr(refresh_token_service, "db", SimpleNamespace(session=session))
    monkeypatch.setattr(refresh_token_service, "_hash_token", lambda raw: f"hash:{raw}")
    monkeypatch.setattr(refresh_token_service, "_get_client_ip_safely", lambda: "172.16.2.59")

    minted = {"called": False}

    def _unexpected_token(_n: int) -> str:
        minted["called"] = True
        raise AssertionError("new refresh token should not be minted during grace-window reuse")

    monkeypatch.setattr(refresh_token_service.secrets, "token_urlsafe", _unexpected_token)

    app = _make_app()
    with app.app_context():
        result = refresh_token_service.rotate_refresh_token("stale-refresh", user_agent="UA/1.0")

    assert result is not None
    assert result.user_id == str(user_id)
    assert result.new_refresh_token is None
    assert minted["called"] is False
    assert session.commit_calls == 0
    assert len(session.added) == 0


def test_rotate_refresh_token_rejects_reuse_outside_grace_window(monkeypatch):
    user_id = uuid.uuid4()
    replacement = RefreshToken()
    replacement.id = uuid.uuid4()
    replacement.user_id = user_id
    replacement.expires_at = datetime.now(dt_timezone.utc) + timedelta(days=1)
    replacement.revoked_at = None

    existing = RefreshToken()
    existing.id = uuid.uuid4()
    existing.user_id = user_id
    existing.token_hash = "hash:stale-refresh"
    existing.revoked_at = datetime.now(dt_timezone.utc) - timedelta(seconds=10)
    existing.replaced_by_id = replacement.id

    session = _FakeSession(
        active_token=None,
        recently_replaced_token=existing,
        replacement_tokens={replacement.id: replacement},
    )
    monkeypatch.setattr(refresh_token_service, "db", SimpleNamespace(session=session))
    monkeypatch.setattr(refresh_token_service, "_hash_token", lambda raw: f"hash:{raw}")
    monkeypatch.setattr(refresh_token_service, "_get_client_ip_safely", lambda: "172.16.2.59")

    app = _make_app()
    with app.app_context():
        result = refresh_token_service.rotate_refresh_token("stale-refresh", user_agent="UA/1.0")

    assert result is None