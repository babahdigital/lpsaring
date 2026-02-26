from __future__ import annotations

from pathlib import Path


def _extract_path_block(spec_text: str, path: str) -> str:
    marker = f"  {path}:"
    start = spec_text.find(marker)
    if start < 0:
        return ""
    trailing = spec_text[start + len(marker) :]
    lines = trailing.splitlines()
    chunk: list[str] = []
    for line in lines:
        if line.startswith("  /"):
            break
        chunk.append(line)
    return "\n".join(chunk)


def _extract_required_inline_for_schema(spec_text: str, schema_name: str) -> set[str]:
    marker = f"    {schema_name}:"
    start = spec_text.find(marker)
    if start < 0:
        return set()
    trailing = spec_text[start + len(marker) :]
    lines = trailing.splitlines()
    for line in lines:
        if line.startswith("    ") and not line.startswith("      "):
            break
        stripped = line.strip()
        if stripped.startswith("required: [") and stripped.endswith("]"):
            inner = stripped[len("required: [") : -1]
            return {item.strip() for item in inner.split(",") if item.strip()}
    return set()


def test_openapi_priority_paths_reference_expected_payload_schemas():
    repo_root = Path(__file__).resolve().parents[2]
    spec_path = repo_root / "contracts" / "openapi" / "openapi.v1.yaml"
    spec_text = spec_path.read_text(encoding="utf-8")

    expected_refs = {
        "/auth/verify-otp": "#/components/schemas/AuthVerifyOtpResponse",
        "/users/me/devices/bind-current": "#/components/schemas/DeviceBindResponse",
        "/transactions/by-order-id/{order_id}": "#/components/schemas/TransactionDetailResponse",
        "/transactions/public/by-order-id/{order_id}": "#/components/schemas/TransactionDetailResponsePublic",
    }

    missing: list[str] = []
    for path, schema_ref in expected_refs.items():
        block = _extract_path_block(spec_text, path)
        if block == "" or schema_ref not in block:
            missing.append(f"{path} -> {schema_ref}")

    assert not missing, f"OpenAPI response schema refs mismatch: {missing}"


def test_openapi_required_fields_for_critical_schemas_and_error_envelope():
    repo_root = Path(__file__).resolve().parents[2]
    spec_path = repo_root / "contracts" / "openapi" / "openapi.v1.yaml"
    spec_text = spec_path.read_text(encoding="utf-8")

    expected_required = {
        "ErrorResponse": {"code", "message"},
        "AuthVerifyOtpResponse": {"access_token", "token_type"},
        "DeviceBindResponse": {"success", "message"},
        "TransactionDetailResponse": {"id", "midtrans_order_id", "status"},
    }

    mismatches: list[str] = []
    for schema_name, required_set in expected_required.items():
        declared = _extract_required_inline_for_schema(spec_text, schema_name)
        if not required_set.issubset(declared):
            mismatches.append(f"{schema_name}: expected {sorted(required_set)} got {sorted(declared)}")

    assert not mismatches, f"Critical schema required fields mismatch: {mismatches}"


def test_runtime_unauthorized_response_uses_error_envelope_shape():
    from app import create_app

    app = create_app("testing")
    app.testing = True

    with app.test_client() as client:
        response = client.get("/api/auth/me")

    assert response.status_code == 401
    payload = response.get_json(silent=True)
    assert isinstance(payload, dict)
    assert payload.get("success") is False
    assert isinstance(payload.get("code"), str) and payload.get("code")
    assert isinstance(payload.get("message"), str) and payload.get("message")
    assert payload.get("status_code") == 401
