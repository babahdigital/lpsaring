from __future__ import annotations

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
    assert (
        cmd._is_expected_missing_dhcp_for_blocked_row(
            list_name="blocked",
            blocked_list_name="blocked",
            has_binding=True,
        )
        is True
    )


def test_is_expected_missing_dhcp_for_blocked_row_false_for_non_blocked_or_no_binding():
    assert (
        cmd._is_expected_missing_dhcp_for_blocked_row(
            list_name="active",
            blocked_list_name="blocked",
            has_binding=True,
        )
        is False
    )
    assert (
        cmd._is_expected_missing_dhcp_for_blocked_row(
            list_name="blocked",
            blocked_list_name="blocked",
            has_binding=False,
        )
        is False
    )
