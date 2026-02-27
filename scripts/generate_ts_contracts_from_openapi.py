#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from collections.abc import Mapping
from typing import Any

try:
    import yaml
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"PyYAML is required to run this generator: {exc}")


ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "contracts" / "openapi" / "openapi.v1.yaml"
OUTPUT_PATH = ROOT / "frontend" / "types" / "api" / "contracts.generated.ts"


def to_pascal(name: str) -> str:
    chunks = re.split(r"[^a-zA-Z0-9]+", name)
    return "".join(chunk[:1].upper() + chunk[1:] for chunk in chunks if chunk)


def path_key(path: str) -> str:
    if path.startswith("/api/"):
        return path[len("/api") :]
    return path


def unwrap_ref(schema: dict[str, Any]) -> str | None:
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return None
    return ref.split("/")[-1]


def schema_to_ts(schema: dict[str, Any], *, required: set[str] | None = None) -> str:
    ref = unwrap_ref(schema)
    if ref:
        return ref

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        literals = " | ".join(repr(v) for v in enum_values)
        ts = literals
        if schema.get("nullable"):
            ts = f"{ts} | null"
        return ts

    if "oneOf" in schema and isinstance(schema["oneOf"], list):
        variants = [schema_to_ts(item, required=None) for item in schema["oneOf"] if isinstance(item, dict)]
        ts = " | ".join(v for v in variants if v) or "unknown"
        if schema.get("nullable"):
            ts = f"{ts} | null"
        return ts

    if "allOf" in schema and isinstance(schema["allOf"], list):
        variants = [schema_to_ts(item, required=None) for item in schema["allOf"] if isinstance(item, dict)]
        ts = " & ".join(v for v in variants if v) or "unknown"
        if schema.get("nullable"):
            ts = f"{ts} | null"
        return ts

    schema_type = schema.get("type")
    if schema_type == "string":
        ts = "string"
    elif schema_type == "integer" or schema_type == "number":
        ts = "number"
    elif schema_type == "boolean":
        ts = "boolean"
    elif schema_type == "array":
        items_obj = schema.get("items")
        items: dict[str, Any] = items_obj if isinstance(items_obj, dict) else {}
        ts = f"Array<{schema_to_ts(items)}>"
    elif schema_type == "object" or "properties" in schema:
        properties_obj = schema.get("properties")
        properties: dict[str, Any] = properties_obj if isinstance(properties_obj, dict) else {}
        req = set(schema.get("required") or [])
        rows: list[str] = []
        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                continue
            opt = "" if prop_name in req else "?"
            rows.append(f"{prop_name}{opt}: {schema_to_ts(prop_schema)}")
        if schema.get("additionalProperties") is True:
            rows.append("[key: string]: unknown")
        elif isinstance(schema.get("additionalProperties"), dict):
            rows.append(f"[key: string]: {schema_to_ts(schema['additionalProperties'])}")
        ts = "{ " + "; ".join(rows) + " }"
    else:
        ts = "unknown"

    if schema.get("nullable"):
        ts = f"{ts} | null"
    return ts


def pick_request_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    request_body = operation.get("requestBody")
    if not isinstance(request_body, dict):
        return None
    content = request_body.get("content")
    if not isinstance(content, dict):
        return None
    for media_type in ("application/json", "application/x-www-form-urlencoded"):
        if media_type in content and isinstance(content[media_type], dict):
            schema = content[media_type].get("schema")
            if isinstance(schema, dict):
                return schema
    return None


def pick_success_response_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return None

    def is_success(code: str) -> bool:
        return code.startswith("2") or code.upper() == "DEFAULT"

    for code in sorted(responses.keys()):
        if not is_success(code):
            continue
        response = responses.get(code)
        if not isinstance(response, dict):
            continue
        content = response.get("content")
        if not isinstance(content, dict):
            continue
        for media_type in ("application/json", "application/octet-stream", "image/png", "image/svg+xml"):
            if media_type in content and isinstance(content[media_type], dict):
                schema = content[media_type].get("schema")
                if isinstance(schema, dict):
                    return schema
    return None


def load_openapi() -> dict[str, Any]:
    raw = OPENAPI_PATH.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw)
    return dict(loaded) if isinstance(loaded, Mapping) else {}


def generate() -> str:
    raw = OPENAPI_PATH.read_bytes()
    source_sha = hashlib.sha256(raw).hexdigest()
    spec = load_openapi()

    info_obj = spec.get("info")
    info: dict[str, Any] = info_obj if isinstance(info_obj, dict) else {}
    version = str(info.get("version") or "unknown")

    components_obj = spec.get("components")
    components: dict[str, Any] = components_obj if isinstance(components_obj, dict) else {}
    schemas_obj = components.get("schemas")
    schemas: dict[str, Any] = schemas_obj if isinstance(schemas_obj, dict) else {}

    lines: list[str] = []
    lines.append("/* eslint-disable */")
    lines.append("// AUTO-GENERATED FILE. DO NOT EDIT MANUALLY.")
    lines.append("// Source: contracts/openapi/openapi.v1.yaml")
    lines.append("")
    lines.append(f"export const OPENAPI_SOURCE_SHA256 = '{source_sha}' as const")
    lines.append(f"export const API_CONTRACT_REVISION = 'openapi-{version}' as const")
    lines.append("")

    for schema_name, schema in schemas.items():
        if not isinstance(schema, dict):
            continue
        lines.append(f"export type {schema_name} = {schema_to_ts(schema)}")
    lines.append("")

    paths_obj = spec.get("paths")
    paths: dict[str, Any] = paths_obj if isinstance(paths_obj, dict) else {}
    lines.append("export interface GeneratedApiContractMap {")
    for path, path_item in sorted(paths.items()):
        if not isinstance(path_item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue
            req_schema = pick_request_schema(op)
            res_schema = pick_success_response_schema(op)
            req_ts = schema_to_ts(req_schema) if isinstance(req_schema, dict) else "never"
            res_ts = schema_to_ts(res_schema) if isinstance(res_schema, dict) else "unknown"
            key = f"{method.upper()} {path_key(path)}"
            lines.append(f"  '{key}': {{")
            lines.append(f"    request: {req_ts}")
            lines.append(f"    response: {res_ts}")
            lines.append("    error: ErrorResponse")
            lines.append("  }")
    lines.append("}")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(generate(), encoding="utf-8")
    print(f"Generated: {OUTPUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
