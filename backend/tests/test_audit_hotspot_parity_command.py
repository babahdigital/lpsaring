from __future__ import annotations

from types import SimpleNamespace

import app.commands.audit_hotspot_parity_command as cmd


def test_calculate_status_overlap_metrics_tracks_fup_overlap_dimensions():
    status_lists_by_ip = {
        "172.16.2.10": {"active", "fup"},
        "172.16.2.11": {"fup", "blocked"},
        "172.16.2.12": {"active", "blocked"},
        "172.16.2.13": {"fup"},
    }
    unauthorized_ips = {"172.16.2.11", "172.16.2.13", "172.16.2.99"}

    metrics = cmd._calculate_status_overlap_metrics(
        status_lists_by_ip=status_lists_by_ip,
        unauthorized_ips=unauthorized_ips,
        list_names={"active": "active", "fup": "fup", "blocked": "blocked"},
        sample_size=10,
    )

    assert metrics["status_multi_overlap_ips"] == ["172.16.2.10", "172.16.2.11", "172.16.2.12"]
    assert metrics["fup_overlap_active_ips"] == ["172.16.2.10"]
    assert metrics["fup_overlap_blocked_ips"] == ["172.16.2.11"]
    assert metrics["fup_overlap_unauthorized_ips"] == ["172.16.2.11", "172.16.2.13"]


def test_calculate_status_overlap_metrics_filters_invalid_ip_candidates():
    status_lists_by_ip = {
        "": {"active", "fup"},
        "0.0.0.0": {"active", "fup"},
        "172.16.2.20": {"active", "fup"},
    }
    unauthorized_ips = {"", "0.0.0.0", "172.16.2.20"}

    metrics = cmd._calculate_status_overlap_metrics(
        status_lists_by_ip=status_lists_by_ip,
        unauthorized_ips=unauthorized_ips,
        list_names={"active": "active", "fup": "fup", "blocked": "blocked"},
        sample_size=10,
    )

    assert metrics["status_multi_overlap_ips"] == ["172.16.2.20"]
    assert metrics["fup_overlap_active_ips"] == ["172.16.2.20"]
    assert metrics["fup_overlap_unauthorized_ips"] == ["172.16.2.20"]


def test_is_expected_missing_dhcp_for_blocked_row_true_when_blocked_with_binding():
    user = SimpleNamespace(id="uid-1")
    cmd.resolve_allowed_binding_type_for_user = lambda _user: "blocked"
    assert (
        cmd._is_expected_missing_dhcp_for_blocked_row(
            list_name="blocked",
            blocked_list_name="blocked",
            has_binding=True,
            resolved_uid="uid-1",
            users_by_uid={"uid-1": user},
        )
        is True
    )


def test_is_expected_missing_dhcp_for_blocked_row_false_for_non_blocked_or_no_binding():
    user = SimpleNamespace(id="uid-1")
    cmd.resolve_allowed_binding_type_for_user = lambda _user: "blocked"
    assert (
        cmd._is_expected_missing_dhcp_for_blocked_row(
            list_name="active",
            blocked_list_name="blocked",
            has_binding=True,
            resolved_uid="uid-1",
            users_by_uid={"uid-1": user},
        )
        is False
    )
    assert (
        cmd._is_expected_missing_dhcp_for_blocked_row(
            list_name="blocked",
            blocked_list_name="blocked",
            has_binding=False,
            resolved_uid="uid-1",
            users_by_uid={"uid-1": user},
        )
        is False
    )


def test_has_binding_for_blocked_row_accepts_regular_binding_for_auto_debt_block(monkeypatch):
    monkeypatch.setattr(cmd, "resolve_allowed_binding_type_for_user", lambda _user: "regular")

    binding_indexes = {
        "token_blocked": set(),
        "mac_blocked": set(),
        "ip_blocked": set(),
        "token_nonblocked": set(),
        "mac_nonblocked": {"66:4B:0F:4C:35:37"},
        "ip_nonblocked": set(),
    }

    assert (
        cmd._has_binding_for_row(
            address="172.16.2.98",
            list_name="blocked",
            uid_token="uid-1",
            user_token="082213615601",
            resolved_uid="uid-1",
            mac_hint="",
            binding_indexes=binding_indexes,
            authorized_macs_by_uid={"uid-1": {"66:4B:0F:4C:35:37"}},
            users_by_uid={"uid-1": SimpleNamespace(id="uid-1")},
            blocked_list_name="blocked",
        )
        is True
    )
