from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from flask import Flask
from sqlalchemy.exc import InvalidRequestError

import app.services.hotspot_sync_service as svc


@contextmanager
def _api_context(api):
    yield api


class _FakeQuery:
    def where(self, *_args, **_kwargs):
        return self

    def options(self, *_args, **_kwargs):
        return self


class _FakeLoader:
    def selectinload(self, *_args, **_kwargs):
        return self


class _FakeNestedTransaction:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        self.session.begin_calls += 1
        return self

    def __exit__(self, exc_type, _exc, _tb):
        self.session.transaction_active = False
        if exc_type is not None:
            self.session.poisoned = False
        return False


class _FakeSession:
    def __init__(self, users):
        self.users = list(users)
        self.begin_calls = 0
        self.remove_calls = 0
        self.poisoned = False
        self.transaction_active = False

    def scalars(self, _query):
        return SimpleNamespace(
            all=lambda: list(self.users),
            first=lambda: self.users[0] if self.users else None,
        )

    def begin(self):
        if self.transaction_active:
            raise InvalidRequestError("A transaction is already begun on this Session.")
        self.transaction_active = True
        return _FakeNestedTransaction(self)

    def remove(self):
        self.remove_calls += 1
        self.transaction_active = False


class _FakeUser:
    def __init__(self, phone_number: str, used_mb: float):
        self._id = uuid4()
        self.raise_on_id = False
        self.phone_number = phone_number
        self.total_quota_used_mb = used_mb
        self.total_quota_purchased_mb = 1000.0
        self.is_unlimited_user = False
        self.role = svc.UserRole.USER
        self.quota_expiry_date = None
        self.mikrotik_profile_name = "default"
        self.is_blocked = False
        self.devices = []

    @property
    def id(self):
        if self.raise_on_id:
            raise RuntimeError("user id unavailable after rollback")
        return self._id


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "unit-test-secret"
    app.config["QUOTA_SYNC_GLOBAL_LOCK_SECONDS"] = 180
    return app


def test_sync_hotspot_usage_and_profiles_isolates_user_failures(monkeypatch):
    app = _make_app()
    first_user = _FakeUser("+628111111111", 10.0)
    second_user = _FakeUser("+628222222222", 20.0)
    fake_session = _FakeSession([first_user, second_user])
    fake_redis = object()
    released_user_ids = []
    user_by_id = {
        first_user._id: first_user,
        second_user._id: second_user,
    }

    monkeypatch.setattr(svc, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(svc, "settings_service", SimpleNamespace(
        get_setting=lambda _key, default=None: default,
        get_setting_as_int=lambda _key, default=0: default,
    ))
    monkeypatch.setattr(
        svc,
        "_load_hotspot_usage_sync_db_state",
        lambda: svc.HotspotUsageSyncDbState(user_ids=[first_user._id, second_user._id]),
    )
    monkeypatch.setattr(svc, "_load_hotspot_sync_user", lambda user_id: user_by_id[user_id])
    monkeypatch.setattr(svc, "_get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(svc, "_acquire_global_sync_lock", lambda *_args, **_kwargs: (True, "token"))
    monkeypatch.setattr(svc, "_release_global_sync_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_acquire_sync_lock", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(svc, "_release_sync_lock", lambda _redis, user_id: released_user_ids.append(user_id))
    monkeypatch.setattr(svc, "_is_demo_user", lambda _user: False)
    monkeypatch.setattr(svc, "get_mikrotik_connection", lambda: _api_context(object()))
    monkeypatch.setattr(svc, "get_hotspot_host_usage_map", lambda _api: (True, {}, "ok"))
    monkeypatch.setattr(svc, "get_hotspot_ip_binding_user_map", lambda _api: (True, {}, "ok"))
    monkeypatch.setattr(svc, "_snapshot_ip_binding_rows_by_mac", lambda _api: (True, {}))
    monkeypatch.setattr(svc, "_snapshot_dhcp_ips_by_mac", lambda _api: (True, {}))
    monkeypatch.setattr(
        svc,
        "_calculate_usage_update",
        lambda user, *_args, **_kwargs: svc.HotspotUsageUpdateResult(
            delta_mb=1.25,
            new_total_usage_mb=float(user.total_quota_used_mb or 0.0) + 1.25,
            device_deltas=[],
            rebaseline_events=[],
        ),
    )

    def _update_daily_usage_log(user, _delta_mb, _today):
        if user is first_user:
            fake_session.poisoned = True
            user.raise_on_id = True
            raise RuntimeError("simulated stale user_devices flush")
        return True

    monkeypatch.setattr(svc, "_update_daily_usage_log", _update_daily_usage_log)
    monkeypatch.setattr(svc, "lock_user_quota_row", lambda _user: None)
    monkeypatch.setattr(
        svc,
        "snapshot_user_quota_state",
        lambda user: {"total_quota_used_mb": float(user.total_quota_used_mb or 0.0)},
    )
    monkeypatch.setattr(svc, "append_quota_mutation_event", lambda **_kwargs: None)
    monkeypatch.setattr(svc, "_calculate_remaining", lambda _user: (500.0, 50.0))
    monkeypatch.setattr(svc, "_apply_auto_debt_limit_block_state", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(svc, "_resolve_target_profile", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_self_heal_policy_binding_for_user", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(svc, "_self_heal_policy_dhcp_for_user", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(svc, "_emit_policy_binding_mismatch_metrics", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_collect_candidate_ips_for_user", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(svc, "_sync_address_list_status_for_ip", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(svc, "_prune_stale_status_entries_for_user", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_sync_address_list_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_send_quota_notifications", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_send_expiry_notifications", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "get_app_local_datetime", lambda *_args, **_kwargs: datetime(2026, 3, 14, tzinfo=timezone.utc))

    with app.app_context():
        result = svc.sync_hotspot_usage_and_profiles()

    assert result["processed"] == 1
    assert result["updated_usage"] == 1
    assert result["failed"] == 1
    assert fake_session.begin_calls == 2
    assert fake_session.remove_calls == 3
    assert second_user.total_quota_used_mb == 21.25
    assert released_user_ids == [first_user._id, second_user._id]


def test_sync_hotspot_usage_and_profiles_releases_preloop_settings_session(monkeypatch):
    app = _make_app()
    first_user = _FakeUser("+628111111111", 10.0)
    second_user = _FakeUser("+628222222222", 20.0)
    fake_session = _FakeSession([first_user, second_user])
    fake_redis = object()
    released_user_ids = []
    user_by_id = {
        first_user._id: first_user,
        second_user._id: second_user,
    }

    def _get_setting(key, default=None):
        fake_session.transaction_active = True
        return default

    def _get_setting_as_int(_key, default=0):
        fake_session.transaction_active = True
        return default

    monkeypatch.setattr(svc, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(
        svc,
        "settings_service",
        SimpleNamespace(
            get_setting=_get_setting,
            get_setting_as_int=_get_setting_as_int,
        ),
    )
    monkeypatch.setattr(
        svc,
        "_load_hotspot_usage_sync_db_state",
        lambda: svc.HotspotUsageSyncDbState(user_ids=[first_user._id, second_user._id]),
    )
    monkeypatch.setattr(svc, "_load_hotspot_sync_user", lambda user_id: user_by_id[user_id])
    monkeypatch.setattr(svc, "_get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(svc, "_acquire_global_sync_lock", lambda *_args, **_kwargs: (True, "token"))
    monkeypatch.setattr(svc, "_release_global_sync_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_acquire_sync_lock", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(svc, "_release_sync_lock", lambda _redis, user_id: released_user_ids.append(user_id))
    monkeypatch.setattr(svc, "_is_demo_user", lambda _user: False)
    monkeypatch.setattr(svc, "get_mikrotik_connection", lambda: _api_context(object()))
    monkeypatch.setattr(svc, "get_hotspot_host_usage_map", lambda _api: (True, {}, "ok"))
    monkeypatch.setattr(svc, "get_hotspot_ip_binding_user_map", lambda _api: (True, {}, "ok"))
    monkeypatch.setattr(svc, "_snapshot_ip_binding_rows_by_mac", lambda _api: (True, {}))
    monkeypatch.setattr(svc, "_snapshot_dhcp_ips_by_mac", lambda _api: (True, {}))
    monkeypatch.setattr(svc, "_calculate_usage_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_calculate_remaining", lambda _user: (500.0, 50.0))
    monkeypatch.setattr(svc, "_apply_auto_debt_limit_block_state", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(svc, "_resolve_target_profile", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_self_heal_policy_binding_for_user", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(svc, "_self_heal_policy_dhcp_for_user", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(svc, "_emit_policy_binding_mismatch_metrics", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_collect_candidate_ips_for_user", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(svc, "_sync_address_list_status_for_ip", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(svc, "_prune_stale_status_entries_for_user", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_sync_address_list_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_send_quota_notifications", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_send_expiry_notifications", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "get_app_local_datetime", lambda *_args, **_kwargs: datetime(2026, 3, 14, tzinfo=timezone.utc))

    with app.app_context():
        result = svc.sync_hotspot_usage_and_profiles()

    assert result["processed"] == 2
    assert result["failed"] == 0
    assert fake_session.begin_calls == 2
    assert fake_session.remove_calls == 3
    assert released_user_ids == [first_user._id, second_user._id]


def test_load_hotspot_usage_sync_db_state_releases_session(monkeypatch):
    first_user_id = uuid4()
    second_user_id = uuid4()
    fake_session = _FakeSession([first_user_id, second_user_id])

    monkeypatch.setattr(svc, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(svc, "select", lambda *_args, **_kwargs: _FakeQuery())

    state = svc._load_hotspot_usage_sync_db_state()

    assert state.user_ids == [first_user_id, second_user_id]
    assert fake_session.remove_calls == 1


def test_sync_hotspot_usage_and_profiles_continues_without_host_snapshot(monkeypatch):
    app = _make_app()
    first_user = _FakeUser("+628111111111", 10.0)
    second_user = _FakeUser("+628222222222", 20.0)
    fake_session = _FakeSession([first_user, second_user])
    fake_redis = object()
    released_user_ids = []
    user_by_id = {
        first_user._id: first_user,
        second_user._id: second_user,
    }
    observed_host_maps = []

    monkeypatch.setattr(svc, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(
        svc,
        "settings_service",
        SimpleNamespace(
            get_setting=lambda _key, default=None: default,
            get_setting_as_int=lambda _key, default=0: default,
        ),
    )
    monkeypatch.setattr(
        svc,
        "_load_hotspot_usage_sync_db_state",
        lambda: svc.HotspotUsageSyncDbState(user_ids=[first_user._id, second_user._id]),
    )
    monkeypatch.setattr(svc, "_load_hotspot_sync_user", lambda user_id: user_by_id[user_id])
    monkeypatch.setattr(svc, "_get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(svc, "_acquire_global_sync_lock", lambda *_args, **_kwargs: (True, "token"))
    monkeypatch.setattr(svc, "_release_global_sync_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_acquire_sync_lock", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(svc, "_release_sync_lock", lambda _redis, user_id: released_user_ids.append(user_id))
    monkeypatch.setattr(svc, "_is_demo_user", lambda _user: False)
    monkeypatch.setattr(svc, "get_mikrotik_connection", lambda: _api_context(object()))
    monkeypatch.setattr(
        svc,
        "get_hotspot_host_usage_map",
        lambda _api: (False, {}, "[Errno 110] Connection timed out"),
    )
    monkeypatch.setattr(svc, "get_hotspot_ip_binding_user_map", lambda _api: (True, {}, "ok"))
    monkeypatch.setattr(svc, "_snapshot_ip_binding_rows_by_mac", lambda _api: (True, {}))
    monkeypatch.setattr(svc, "_snapshot_dhcp_ips_by_mac", lambda _api: (True, {}))

    def _calculate_usage_update(user, host_usage_map, _redis_client):
        observed_host_maps.append(dict(host_usage_map))
        return None

    monkeypatch.setattr(svc, "_calculate_usage_update", _calculate_usage_update)
    monkeypatch.setattr(svc, "_calculate_remaining", lambda _user: (500.0, 50.0))
    monkeypatch.setattr(svc, "_apply_auto_debt_limit_block_state", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(svc, "_resolve_target_profile", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_self_heal_policy_binding_for_user", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(svc, "_self_heal_policy_dhcp_for_user", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(svc, "_emit_policy_binding_mismatch_metrics", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_collect_candidate_ips_for_user", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(svc, "_sync_address_list_status_for_ip", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(svc, "_prune_stale_status_entries_for_user", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_sync_address_list_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_send_quota_notifications", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_send_expiry_notifications", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "get_app_local_datetime", lambda *_args, **_kwargs: datetime(2026, 3, 14, tzinfo=timezone.utc))

    with app.app_context():
        result = svc.sync_hotspot_usage_and_profiles()

    assert result["processed"] == 2
    assert result["failed"] == 0
    assert fake_session.begin_calls == 2
    assert fake_session.remove_calls == 3
    assert released_user_ids == [first_user._id, second_user._id]
    assert observed_host_maps == [{}, {}]


def test_sync_hotspot_usage_and_profiles_reuses_owned_status_snapshot_for_prune(monkeypatch):
    app = _make_app()
    first_user = _FakeUser("+628111111111", 10.0)
    second_user = _FakeUser("+628222222222", 20.0)
    fake_session = _FakeSession([first_user, second_user])
    fake_redis = object()
    released_user_ids = []
    user_by_id = {
        first_user._id: first_user,
        second_user._id: second_user,
    }
    api = object()
    managed_snapshot = {
        "by_user_id": {
            str(first_user._id): {("active", "172.16.2.10")},
            str(second_user._id): {("active", "172.16.2.11")},
        },
        "by_username": {},
    }
    snapshot_calls = []
    prune_calls = []

    monkeypatch.setattr(svc, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(
        svc,
        "settings_service",
        SimpleNamespace(
            get_setting=lambda _key, default=None: default,
            get_setting_as_int=lambda _key, default=0: default,
        ),
    )
    monkeypatch.setattr(
        svc,
        "_load_hotspot_usage_sync_db_state",
        lambda: svc.HotspotUsageSyncDbState(user_ids=[first_user._id, second_user._id]),
    )
    monkeypatch.setattr(svc, "_load_hotspot_sync_user", lambda user_id: user_by_id[user_id])
    monkeypatch.setattr(svc, "_get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(svc, "_acquire_global_sync_lock", lambda *_args, **_kwargs: (True, "token"))
    monkeypatch.setattr(svc, "_release_global_sync_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_acquire_sync_lock", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(svc, "_release_sync_lock", lambda _redis, user_id: released_user_ids.append(user_id))
    monkeypatch.setattr(svc, "_is_demo_user", lambda _user: False)
    monkeypatch.setattr(svc, "get_mikrotik_connection", lambda: _api_context(api))
    monkeypatch.setattr(svc, "get_hotspot_host_usage_map", lambda _api: (True, {}, "ok"))
    monkeypatch.setattr(svc, "get_hotspot_ip_binding_user_map", lambda _api: (True, {}, "ok"))
    monkeypatch.setattr(svc, "_snapshot_ip_binding_rows_by_mac", lambda _api: (True, {}))
    monkeypatch.setattr(svc, "_snapshot_dhcp_ips_by_mac", lambda _api: (True, {}))

    def _fake_snapshot(_api, *, managed_status_lists=None):
        snapshot_calls.append((
            _api,
            tuple(managed_status_lists or []),
        ))
        return True, managed_snapshot

    def _fake_prune(_api, user, keep_ips=None, *, owned_status_entries_snapshot=None, managed_status_lists=None):
        prune_calls.append(
            (
                user.id,
                list(keep_ips or []),
                owned_status_entries_snapshot,
                tuple(managed_status_lists or []),
            )
        )
        return 0

    monkeypatch.setattr(svc, "_snapshot_owned_status_entries_for_prune", _fake_snapshot)
    monkeypatch.setattr(svc, "_calculate_usage_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_calculate_remaining", lambda _user: (500.0, 50.0))
    monkeypatch.setattr(svc, "_apply_auto_debt_limit_block_state", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(svc, "_resolve_target_profile", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_self_heal_policy_binding_for_user", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(svc, "_self_heal_policy_dhcp_for_user", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(svc, "_emit_policy_binding_mismatch_metrics", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_collect_candidate_ips_for_user", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(svc, "_sync_address_list_status_for_ip", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(svc, "_prune_stale_status_entries_for_user", _fake_prune)
    monkeypatch.setattr(svc, "_sync_address_list_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_send_quota_notifications", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "_send_expiry_notifications", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc, "get_app_local_datetime", lambda *_args, **_kwargs: datetime(2026, 3, 14, tzinfo=timezone.utc))

    with app.app_context():
        result = svc.sync_hotspot_usage_and_profiles()

    assert result["processed"] == 2
    assert result["failed"] == 0
    assert len(snapshot_calls) == 1
    assert snapshot_calls[0][0] is api
    assert len(snapshot_calls[0][1]) == 6
    assert released_user_ids == [first_user._id, second_user._id]
    assert [call[0] for call in prune_calls] == [first_user._id, second_user._id]
    assert all(call[2] is managed_snapshot for call in prune_calls)
    assert all(len(call[3]) == 6 for call in prune_calls)