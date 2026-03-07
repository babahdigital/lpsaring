from __future__ import annotations

import app.commands.sync_unauthorized_hosts_command as cmd


def test_plan_critical_status_overlap_removals_enforces_priority():
    ip_to_lists = {
        "172.16.2.10": {"active", "fup"},
        "172.16.2.11": {"active", "blocked"},
        "172.16.2.12": {"active", "fup", "blocked"},
        "172.16.2.13": {"fup"},
    }

    plans = cmd._plan_critical_status_overlap_removals(
        ip_to_lists=ip_to_lists,
        list_active="active",
        list_fup="fup",
        list_blocked="blocked",
    )

    assert len(plans) == 4
    assert ("172.16.2.10", "active", "fup") in plans
    assert ("172.16.2.11", "active", "blocked") in plans
    assert ("172.16.2.12", "active", "blocked") in plans
    assert ("172.16.2.12", "fup", "blocked") in plans


def test_plan_critical_status_overlap_removals_ignores_single_or_unknown_lists():
    ip_to_lists = {
        "172.16.2.20": {"active"},
        "172.16.2.21": {"fup"},
        "172.16.2.22": {"blocked"},
        "172.16.2.23": {"unknown-a", "unknown-b"},
    }

    plans = cmd._plan_critical_status_overlap_removals(
        ip_to_lists=ip_to_lists,
        list_active="active",
        list_fup="fup",
        list_blocked="blocked",
    )

    assert plans == []
