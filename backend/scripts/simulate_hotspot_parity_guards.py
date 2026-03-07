from __future__ import annotations

import json
import os
import sys


_HERE = os.path.abspath(os.path.dirname(__file__))
_BACKEND_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.commands.audit_hotspot_parity_command import (  # noqa: E402
    _calculate_status_overlap_metrics,
    _is_expected_missing_dhcp_for_blocked_row,
)
from app.commands.sync_unauthorized_hosts_command import (  # noqa: E402
    _plan_critical_status_overlap_removals,
)


def main() -> int:
    failed_checks: list[str] = []

    blocked_expected = _is_expected_missing_dhcp_for_blocked_row(
        list_name="blocked",
        blocked_list_name="blocked",
        has_binding=True,
    )
    non_blocked_expected = _is_expected_missing_dhcp_for_blocked_row(
        list_name="active",
        blocked_list_name="blocked",
        has_binding=True,
    )
    blocked_without_binding_expected = _is_expected_missing_dhcp_for_blocked_row(
        list_name="blocked",
        blocked_list_name="blocked",
        has_binding=False,
    )

    if blocked_expected is not True:
        failed_checks.append("blocked_with_binding_should_be_expected")
    if non_blocked_expected is not False:
        failed_checks.append("non_blocked_should_not_be_expected")
    if blocked_without_binding_expected is not False:
        failed_checks.append("blocked_without_binding_should_not_be_expected")

    overlap_metrics = _calculate_status_overlap_metrics(
        status_lists_by_ip={
            "172.16.2.10": {"active", "fup"},
            "172.16.2.11": {"fup", "blocked"},
            "172.16.2.12": {"active", "blocked", "fup"},
        },
        unauthorized_ips={"172.16.2.11", "172.16.2.99"},
        list_names={"active": "active", "fup": "fup", "blocked": "blocked"},
        sample_size=10,
    )

    if overlap_metrics["fup_overlap_active_ips"] != ["172.16.2.10", "172.16.2.12"]:
        failed_checks.append("fup_overlap_active_unexpected")
    if overlap_metrics["fup_overlap_blocked_ips"] != ["172.16.2.11", "172.16.2.12"]:
        failed_checks.append("fup_overlap_blocked_unexpected")

    overlap_plan = _plan_critical_status_overlap_removals(
        ip_to_lists={
            "172.16.2.10": {"active", "fup"},
            "172.16.2.11": {"active", "blocked"},
            "172.16.2.12": {"active", "fup", "blocked"},
        },
        list_active="active",
        list_fup="fup",
        list_blocked="blocked",
    )

    expected_actions = {
        ("172.16.2.10", "active", "fup"),
        ("172.16.2.11", "active", "blocked"),
        ("172.16.2.12", "active", "blocked"),
        ("172.16.2.12", "fup", "blocked"),
    }
    if set(overlap_plan) != expected_actions:
        failed_checks.append("critical_overlap_plan_unexpected")

    output = {
        "ok": len(failed_checks) == 0,
        "failed_checks": failed_checks,
        "samples": {
            "blocked_expected": blocked_expected,
            "overlap_plan": overlap_plan,
            "overlap_metrics": {
                "fup_overlap_active_ips": overlap_metrics["fup_overlap_active_ips"],
                "fup_overlap_blocked_ips": overlap_metrics["fup_overlap_blocked_ips"],
            },
        },
    }
    print(json.dumps(output, indent=2, ensure_ascii=True))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
