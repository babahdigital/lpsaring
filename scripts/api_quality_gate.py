#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from collections.abc import Mapping
from typing import Any

try:
    import yaml
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"PyYAML is required: {exc}")


ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "contracts" / "openapi" / "openapi.v1.yaml"
GENERATED_TS_PATH = ROOT / "frontend" / "types" / "api" / "contracts.generated.ts"

REQUIRED_PRIORITY_PATHS = {
    "/auth/register",
    "/auth/request-otp",
    "/auth/verify-otp",
    "/auth/session/consume",
    "/auth/me",
    "/auth/me/profile",
    "/users/me/profile",
    "/users/me/devices",
    "/users/me/devices/bind-current",
    "/users/me/devices/{device_id}",
    "/users/me/devices/{device_id}/label",
    "/transactions/initiate",
    "/transactions/debt/initiate",
    "/transactions/by-order-id/{order_id}",
    "/transactions/public/by-order-id/{order_id}",
    "/transactions/{order_id}/cancel",
    "/transactions/public/{order_id}/cancel",
    "/transactions/{order_id}/qr",
    "/transactions/public/{order_id}/qr",
    "/admin/users",
    "/admin/users/{user_id}",
    "/admin/settings",
    "/admin/quota-requests",
    "/admin/quota-requests/{request_id}/process",
    "/admin/transactions",
    "/admin/transactions/{order_id}/detail",
}


def load_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return dict(loaded) if isinstance(loaded, Mapping) else {}


def normalize_backend_route(path: str) -> str:
    path = re.sub(r"<[^:>]+:([^>]+)>", r"{\1}", path)
    path = re.sub(r"<([^>]+)>", r"{\1}", path)
    return path


def check_openapi_paths(spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    paths_obj = spec.get("paths")
    paths: dict[str, Any] = paths_obj if isinstance(paths_obj, dict) else {}
    openapi_paths = set(paths.keys())

    missing_priority = sorted(REQUIRED_PRIORITY_PATHS - openapi_paths)
    if missing_priority:
        errors.append("Missing priority paths in OpenAPI:")
        errors.extend([f"  - {p}" for p in missing_priority])

    # Security response consistency for secured operations
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue
            security = op.get("security")
            if not security:
                continue
            responses_obj = op.get("responses")
            responses: dict[str, Any] = responses_obj if isinstance(responses_obj, dict) else {}
            if "401" not in responses:
                errors.append(f"Secured operation missing 401 response: {method.upper()} {path}")

    # Error envelope schema consistency
    components_obj = spec.get("components")
    components: dict[str, Any] = components_obj if isinstance(components_obj, dict) else {}
    schemas_obj = components.get("schemas")
    schemas: dict[str, Any] = schemas_obj if isinstance(schemas_obj, dict) else {}
    error_schema_obj = schemas.get("ErrorResponse")
    error_schema = error_schema_obj if isinstance(error_schema_obj, dict) else None
    if not error_schema:
        errors.append("Missing components.schemas.ErrorResponse")
    else:
        required = set(error_schema.get("required") or [])
        if not {"code", "message"}.issubset(required):
            errors.append("ErrorResponse must require fields: code, message")

    return errors


def check_generated_sync() -> list[str]:
    errors: list[str] = []
    if not GENERATED_TS_PATH.exists():
        return [f"Missing generated contracts file: {GENERATED_TS_PATH}"]

    source_sha = hashlib.sha256(OPENAPI_PATH.read_bytes()).hexdigest()
    content = GENERATED_TS_PATH.read_text(encoding="utf-8")
    match = re.search(r"OPENAPI_SOURCE_SHA256\s*=\s*'([0-9a-f]+)'", content)
    if not match:
        errors.append("Generated contracts missing OPENAPI_SOURCE_SHA256 marker")
        return errors

    generated_sha = match.group(1)
    if generated_sha != source_sha:
        errors.append(
            "Generated contracts out of date. Run: "
            "python scripts/generate_ts_contracts_from_openapi.py"
        )

    return errors


def main() -> int:
    spec = load_yaml(OPENAPI_PATH)
    errors = []
    errors.extend(check_openapi_paths(spec))
    errors.extend(check_generated_sync())

    if errors:
        print("[api-quality-gate] FAIL")
        for err in errors:
            print(err)
        return 1

    print("[api-quality-gate] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
