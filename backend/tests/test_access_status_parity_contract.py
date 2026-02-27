from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from app.services import access_policy_service as policy


_CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "access_status_parity_cases.json"


def _to_frontend_status(backend_status: str) -> str:
    if backend_status in {"active", "unlimited"}:
        return "ok"
    return backend_status


def test_access_status_parity_contract(monkeypatch):
    monkeypatch.setattr(policy.settings_service, "get_setting_as_int", lambda key, default=0: 3072)

    payload = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert payload, "Contract cases must not be empty"

    for case in payload:
        user_data = dict(case.get("user") or {})
        expiry_raw = user_data.get("quota_expiry_date")
        if isinstance(expiry_raw, str) and expiry_raw.strip():
            user_data["quota_expiry_date"] = datetime.fromisoformat(expiry_raw)
        user = SimpleNamespace(**user_data)

        backend_status = policy.get_user_access_status(user)

        assert backend_status == case["expected_backend"], f"backend mismatch for case={case.get('name')}"
        assert _to_frontend_status(backend_status) == case["expected_frontend"], (
            f"frontend-mapped mismatch for case={case.get('name')}"
        )
