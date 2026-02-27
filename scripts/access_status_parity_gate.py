#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_STATUS_FILE = ROOT / "frontend" / "types" / "accessStatus.ts"
BACKEND_STATUS_FILE = ROOT / "backend" / "app" / "utils" / "access_status.py"
STATUS_MATRIX_DOC = ROOT / "docs" / "ACCESS_STATUS_MATRIX.md"

CANONICAL = ["ok", "blocked", "inactive", "expired", "habis", "fup"]
STATUS_PAGE_ALLOWED = ["blocked", "inactive", "expired", "habis", "fup"]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_quoted_list(text: str, const_name: str) -> list[str]:
    pattern = re.compile(rf"{re.escape(const_name)}\s*=\s*\[(.*?)\]", re.S)
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Cannot find list for {const_name}")

    body = match.group(1)
    values = re.findall(r"['\"]([a-z_]+)['\"]", body)
    if not values:
        raise ValueError(f"No values extracted for {const_name}")
    return values


def _extract_backend_order(text: str) -> list[str]:
    pattern = re.compile(r"ACCESS_STATUS_ORDER\s*:\s*tuple\[str,\s*\.\.\.\]\s*=\s*\((.*?)\)", re.S)
    match = pattern.search(text)
    if not match:
        raise ValueError("Cannot find ACCESS_STATUS_ORDER")

    block = match.group(1)
    values = re.findall(r"AccessStatus\.([A-Z_]+)", block)
    if not values:
        raise ValueError("No AccessStatus entries in ACCESS_STATUS_ORDER")

    enum_map = {
        "OK": "ok",
        "BLOCKED": "blocked",
        "INACTIVE": "inactive",
        "EXPIRED": "expired",
        "HABIS": "habis",
        "FUP": "fup",
    }
    return [enum_map[v] for v in values]


def _extract_backend_status_page_allowed(text: str) -> list[str]:
    pattern = re.compile(r"STATUS_PAGE_ALLOWED\s*:\s*set\[str\]\s*=\s*\{(.*?)\}", re.S)
    match = pattern.search(text)
    if not match:
        raise ValueError("Cannot find STATUS_PAGE_ALLOWED")

    block = match.group(1)
    values = re.findall(r"AccessStatus\.([A-Z_]+)", block)
    enum_map = {
        "OK": "ok",
        "BLOCKED": "blocked",
        "INACTIVE": "inactive",
        "EXPIRED": "expired",
        "HABIS": "habis",
        "FUP": "fup",
    }
    extracted = [enum_map[v] for v in values]
    return sorted(set(extracted), key=lambda s: STATUS_PAGE_ALLOWED.index(s) if s in STATUS_PAGE_ALLOWED else 999)


def _extract_doc_enum(text: str) -> list[str]:
    section_pattern = re.compile(r"## Status Enum\s*(.*?)\n## ", re.S)
    match = section_pattern.search(text + "\n## ")
    if not match:
        raise ValueError("Cannot find '## Status Enum' section")

    section = match.group(1)
    values = re.findall(r"-\s*`([a-z_]+)`", section)
    if not values:
        raise ValueError("No status values found in docs enum section")
    return values


def main() -> int:
    frontend_text = _read(FRONTEND_STATUS_FILE)
    backend_text = _read(BACKEND_STATUS_FILE)
    doc_text = _read(STATUS_MATRIX_DOC)

    frontend_all = _extract_quoted_list(frontend_text, "ACCESS_STATUS_VALUES")
    frontend_allowed = _extract_quoted_list(frontend_text, "STATUS_PAGE_ALLOWED_VALUES")
    backend_all = _extract_backend_order(backend_text)
    backend_allowed = _extract_backend_status_page_allowed(backend_text)
    docs_all = _extract_doc_enum(doc_text)

    errors: list[str] = []

    if frontend_all != CANONICAL:
        errors.append(f"frontend ACCESS_STATUS_VALUES mismatch: {frontend_all} != {CANONICAL}")
    if backend_all != CANONICAL:
        errors.append(f"backend ACCESS_STATUS_ORDER mismatch: {backend_all} != {CANONICAL}")
    if docs_all != CANONICAL:
        errors.append(f"docs Status Enum mismatch: {docs_all} != {CANONICAL}")

    if frontend_allowed != STATUS_PAGE_ALLOWED:
        errors.append(f"frontend STATUS_PAGE_ALLOWED_VALUES mismatch: {frontend_allowed} != {STATUS_PAGE_ALLOWED}")
    if backend_allowed != STATUS_PAGE_ALLOWED:
        errors.append(f"backend STATUS_PAGE_ALLOWED mismatch: {backend_allowed} != {STATUS_PAGE_ALLOWED}")

    if errors:
        print("[access-status-parity-gate] FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("[access-status-parity-gate] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
