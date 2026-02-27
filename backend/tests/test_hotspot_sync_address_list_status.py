from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
import uuid

from flask import Flask

import app.services.hotspot_sync_service as svc
from app.utils.block_reasons import build_auto_debt_limit_reason


class _Role:
    def __init__(self, value: str):
        self.value = value


def _patch_settings(monkeypatch, *, fup_threshold_mb: int = 3072):
    mapping = {
        "MIKROTIK_ADDRESS_LIST_ACTIVE": "active_list",
        "MIKROTIK_ADDRESS_LIST_FUP": "fup_list",
        "MIKROTIK_ADDRESS_LIST_INACTIVE": "inactive_list",
        "MIKROTIK_ADDRESS_LIST_EXPIRED": "expired_list",
        "MIKROTIK_ADDRESS_LIST_HABIS": "habis_list",
        "MIKROTIK_ADDRESS_LIST_BLOCKED": "blocked_list",
    }

    def fake_get_setting(key: str, default=None):
        return mapping.get(key, default)

    def fake_get_setting_as_int(key: str, default: int = 0) -> int:
        if key == "QUOTA_FUP_THRESHOLD_MB":
            return fup_threshold_mb
        return default

    monkeypatch.setattr(svc.settings_service, "get_setting", fake_get_setting)
    monkeypatch.setattr(svc.settings_service, "get_setting_as_int", fake_get_setting_as_int)


def test_sync_address_list_blocked_has_priority_and_cleans_other_lists(monkeypatch):
    _patch_settings(monkeypatch)

    capture = {}

    def fake_sync_address_list_for_user(
        *, api_connection, username, target_list, other_lists=None, comment=None, timeout=None
    ):
        capture["username"] = username
        capture["target_list"] = target_list
        capture["other_lists"] = list(other_lists or [])
        capture["comment"] = comment or ""
        return True, "Sukses"

    monkeypatch.setattr(svc, "sync_address_list_for_user", fake_sync_address_list_for_user)

    user = SimpleNamespace(
        is_unlimited_user=False,
        is_blocked=True,
        role=_Role("USER"),
        phone_number="081234567890",
    )

    ok = svc._sync_address_list_status(
        api=object(),
        user=cast(Any, user),
        username_08="081234567890",
        remaining_mb=999.0,
        remaining_percent=100.0,
        is_expired=False,
    )

    assert ok is True
    assert capture["target_list"] == "blocked_list"

    # Ensure we pass all lists including blocked so sync can remove non-target lists.
    assert "blocked_list" in capture["other_lists"]
    assert "active_list" in capture["other_lists"]
    assert "fup_list" in capture["other_lists"]
    assert "inactive_list" in capture["other_lists"]
    assert "expired_list" in capture["other_lists"]
    assert "habis_list" in capture["other_lists"]

    assert "status=blocked" in capture["comment"]


def test_sync_address_list_non_blocked_removes_blocked_if_present(monkeypatch):
    _patch_settings(monkeypatch, fup_threshold_mb=3072)

    capture = {}

    def fake_sync_address_list_for_user(
        *, api_connection, username, target_list, other_lists=None, comment=None, timeout=None
    ):
        capture["target_list"] = target_list
        capture["other_lists"] = list(other_lists or [])
        capture["comment"] = comment or ""
        return True, "Sukses"

    monkeypatch.setattr(svc, "sync_address_list_for_user", fake_sync_address_list_for_user)

    user = SimpleNamespace(
        is_unlimited_user=False,
        is_blocked=False,
        role=_Role("USER"),
        phone_number="081234567890",
        total_quota_purchased_mb=10240,
    )

    ok = svc._sync_address_list_status(
        api=object(),
        user=cast(Any, user),
        username_08="081234567890",
        remaining_mb=100.0,
        remaining_percent=10.0,
        is_expired=False,
    )

    assert ok is True
    assert capture["target_list"] == "fup_list"

    # Critical: blocked list is part of other_lists so it gets removed when user isn't blocked.
    assert "blocked_list" in capture["other_lists"]
    assert "status=fup" in capture["comment"]


def test_sync_address_list_auto_debt_blocked_user_uses_blocked_list(monkeypatch):
    _patch_settings(monkeypatch, fup_threshold_mb=3072)

    capture = {}

    def fake_sync_address_list_for_user(
        *, api_connection, username, target_list, other_lists=None, comment=None, timeout=None
    ):
        capture["target_list"] = target_list
        capture["other_lists"] = list(other_lists or [])
        capture["comment"] = comment or ""
        return True, "Sukses"

    monkeypatch.setattr(svc, "sync_address_list_for_user", fake_sync_address_list_for_user)

    user = SimpleNamespace(
        is_unlimited_user=False,
        is_blocked=True,
        blocked_reason=build_auto_debt_limit_reason(debt_mb=640, limit_mb=500, source="test"),
        role=_Role("USER"),
        phone_number="081234567890",
        total_quota_purchased_mb=10240,
    )

    ok = svc._sync_address_list_status(
        api=object(),
        user=cast(Any, user),
        username_08="081234567890",
        remaining_mb=0.0,
        remaining_percent=0.0,
        is_expired=False,
    )

    assert ok is True
    assert capture["target_list"] == "blocked_list"
    assert "status=blocked" in capture["comment"]


def test_self_heal_policy_binding_repairs_mismatch(monkeypatch):
    app = Flask(__name__)
    app.config["ENABLE_POLICY_BINDING_SELF_HEAL"] = True

    calls = {"count": 0, "binding_type": None}

    def _fake_upsert_ip_binding(*, api_connection, mac_address, address=None, server=None, binding_type="regular", comment=None):
        calls["count"] += 1
        calls["binding_type"] = binding_type
        return True, "ok"

    monkeypatch.setattr(svc, "upsert_ip_binding", _fake_upsert_ip_binding)
    monkeypatch.setattr(svc, "resolve_allowed_binding_type_for_user", lambda _u: "regular")

    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=_Role("USER"),
        phone_number="081234567890",
        mikrotik_server_name="srv-user",
        devices=[
            SimpleNamespace(
                is_authorized=True,
                mac_address="DA:B2:F3:B8:94:D2",
                ip_address="172.16.3.179",
            )
        ],
    )
    ip_binding_map = {
        "DA:B2:F3:B8:94:D2": {
            "type": "bypassed",
            "address": "172.16.3.179",
        }
    }

    with app.app_context():
        healed = svc._self_heal_policy_binding_for_user(
            api=object(),
            user=cast(Any, user),
            ip_binding_map=ip_binding_map,
            host_usage_map={},
        )

    assert healed == 1
    assert calls["count"] == 1
    assert calls["binding_type"] == "regular"
    assert ip_binding_map["DA:B2:F3:B8:94:D2"]["type"] == "regular"


def test_self_heal_policy_binding_respects_disable_toggle(monkeypatch):
    app = Flask(__name__)
    app.config["ENABLE_POLICY_BINDING_SELF_HEAL"] = False

    calls = {"count": 0}

    def _fake_upsert_ip_binding(*, api_connection, mac_address, address=None, server=None, binding_type="regular", comment=None):
        calls["count"] += 1
        return True, "ok"

    monkeypatch.setattr(svc, "upsert_ip_binding", _fake_upsert_ip_binding)
    monkeypatch.setattr(svc, "resolve_allowed_binding_type_for_user", lambda _u: "regular")

    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=_Role("USER"),
        phone_number="081234567890",
        mikrotik_server_name="srv-user",
        devices=[SimpleNamespace(is_authorized=True, mac_address="DA:B2:F3:B8:94:D2", ip_address="172.16.3.179")],
    )
    ip_binding_map = {"DA:B2:F3:B8:94:D2": {"type": "bypassed"}}

    with app.app_context():
        healed = svc._self_heal_policy_binding_for_user(
            api=object(),
            user=cast(Any, user),
            ip_binding_map=ip_binding_map,
            host_usage_map={},
        )

    assert healed == 0
    assert calls["count"] == 0
