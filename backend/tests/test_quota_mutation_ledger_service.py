from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from sqlalchemy.exc import IntegrityError

import app.services.quota_mutation_ledger_service as svc


class _SessionStub:
    def __init__(self, *, raise_integrity_on_flush: bool = False):
        self.raise_integrity_on_flush = raise_integrity_on_flush
        self.add_calls = 0
        self.flush_calls = 0
        self.begin_nested_calls = 0

    @contextmanager
    def begin_nested(self):
        self.begin_nested_calls += 1
        yield

    def add(self, _item):
        self.add_calls += 1

    def flush(self):
        self.flush_calls += 1
        if self.raise_integrity_on_flush:
            raise IntegrityError("insert", {}, Exception("duplicate idempotency"))


def test_append_quota_mutation_event_ignores_duplicate_idempotency(monkeypatch):
    session = _SessionStub(raise_integrity_on_flush=True)
    monkeypatch.setattr(svc, "has_app_context", lambda: True)
    monkeypatch.setattr(svc.db, "session", session, raising=False)

    user = SimpleNamespace(id="u-1")

    svc.append_quota_mutation_event(
        user=user,  # type: ignore[arg-type]
        source="hotspot.sync_usage",
        before_state={"total_quota_used_mb": 100.0},
        after_state={"total_quota_used_mb": 100.5},
        idempotency_key="sync_usage:u-1:2026-03-01:100.5",
        event_details={"delta_mb": 0.5},
    )

    assert session.begin_nested_calls == 1
    assert session.add_calls == 1
    assert session.flush_calls == 1


def test_append_quota_mutation_event_adds_and_flushes_when_valid(monkeypatch):
    session = _SessionStub(raise_integrity_on_flush=False)
    monkeypatch.setattr(svc, "has_app_context", lambda: True)
    monkeypatch.setattr(svc.db, "session", session, raising=False)

    user = SimpleNamespace(id="u-2")

    svc.append_quota_mutation_event(
        user=user,  # type: ignore[arg-type]
        source="hotspot.sync_usage",
        before_state={"total_quota_used_mb": 50.0},
        after_state={"total_quota_used_mb": 51.0},
        idempotency_key="sync_usage:u-2:2026-03-01:51.0",
        event_details={"delta_mb": 1.0},
    )

    assert session.begin_nested_calls == 1
    assert session.add_calls == 1
    assert session.flush_calls == 1
