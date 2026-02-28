#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass


CRITICAL_CONTRACT_FILES = {
    "contracts/openapi/openapi.v1.yaml",
    "frontend/types/api/contracts.generated.ts",
    "frontend/types/api/contracts.ts",
}

REQUIRED_DOC_FILES = {
    "docs/API_DETAIL.md",
}

ENDPOINT_SENSITIVE_PREFIXES = (
    "backend/app/infrastructure/http/",
)


@dataclass
class GateResult:
    ok: bool
    endpoint_changed_files: list[str]
    missing_contract_files: list[str]
    missing_doc_files: list[str]


def _run_git(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git command failed")
    return proc.stdout


def _resolve_base_head(base: str | None, head: str | None) -> tuple[str, str]:
    resolved_head = head or "HEAD"
    if base:
        return base, resolved_head
    return "HEAD~1", resolved_head


def _run_diff_with_range_fallback(
    *,
    base: str,
    head: str,
    diff_options: list[str],
    pathspec: list[str] | None = None,
) -> str:
    primary_range = f"{base}...{head}"
    primary_cmd = ["diff", *diff_options, primary_range]
    if pathspec:
        primary_cmd.extend(["--", *pathspec])

    try:
        return _run_git(primary_cmd)
    except RuntimeError as exc:
        error_text = str(exc).lower()
        recoverable = (
            "invalid symmetric difference expression" in error_text
            or "bad revision" in error_text
            or "unknown revision" in error_text
        )
        if not recoverable:
            raise

    fallback_range = f"{head}~1..{head}"
    fallback_cmd = ["diff", *diff_options, fallback_range]
    if pathspec:
        fallback_cmd.extend(["--", *pathspec])
    return _run_git(fallback_cmd)


def _changed_files(base: str, head: str) -> list[str]:
    out = _run_diff_with_range_fallback(base=base, head=head, diff_options=["--name-only"])
    return [line.strip() for line in out.splitlines() if line.strip()]


def _contains_endpoint_signature_change(base: str, head: str, file_path: str) -> bool:
    diff = _run_diff_with_range_fallback(
        base=base,
        head=head,
        diff_options=["--unified=0"],
        pathspec=[file_path],
    )
    for line in diff.splitlines():
        if not line.startswith(("+", "-")):
            continue
        if line.startswith(("+++", "---")):
            continue
        if re.search(r"@\w+\.route\(", line):
            return True
        if "Blueprint(" in line and "url_prefix" in line:
            return True
    return False


def run_gate(base: str | None, head: str | None) -> GateResult:
    base_ref, head_ref = _resolve_base_head(base, head)
    files = _changed_files(base_ref, head_ref)
    changed_set = set(files)

    candidate_endpoint_files = [
        p
        for p in files
        if p.startswith(ENDPOINT_SENSITIVE_PREFIXES)
        and p.endswith(".py")
    ]

    endpoint_changed_files: list[str] = []
    for file_path in candidate_endpoint_files:
        if _contains_endpoint_signature_change(base_ref, head_ref, file_path):
            endpoint_changed_files.append(file_path)

    if not endpoint_changed_files:
        return GateResult(ok=True, endpoint_changed_files=[], missing_contract_files=[], missing_doc_files=[])

    missing_contract_files = [p for p in sorted(CRITICAL_CONTRACT_FILES) if p not in changed_set]
    missing_doc_files = [p for p in sorted(REQUIRED_DOC_FILES) if p not in changed_set]

    ok = not missing_contract_files and not missing_doc_files
    return GateResult(
        ok=ok,
        endpoint_changed_files=sorted(endpoint_changed_files),
        missing_contract_files=missing_contract_files,
        missing_doc_files=missing_doc_files,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Contract gate for FE-BE critical API changes")
    parser.add_argument("--base", default=None, help="Base git ref/sha")
    parser.add_argument("--head", default=None, help="Head git ref/sha")
    args = parser.parse_args()

    try:
        result = run_gate(args.base, args.head)
    except Exception as exc:
        print(f"[contract-gate] ERROR: {exc}")
        return 2

    if result.ok:
        print("[contract-gate] PASS")
        if result.endpoint_changed_files:
            print("[contract-gate] Endpoint signature changes detected and contract artifacts updated:")
            for file_path in result.endpoint_changed_files:
                print(f"  - {file_path}")
        else:
            print("[contract-gate] No endpoint signature changes detected.")
        return 0

    print("[contract-gate] FAIL")
    print("[contract-gate] Endpoint signature changes detected in:")
    for file_path in result.endpoint_changed_files:
        print(f"  - {file_path}")

    if result.missing_contract_files:
        print("[contract-gate] Missing required contract updates:")
        for file_path in result.missing_contract_files:
            print(f"  - {file_path}")

    if result.missing_doc_files:
        print("[contract-gate] Missing required API docs updates:")
        for file_path in result.missing_doc_files:
            print(f"  - {file_path}")

    print("[contract-gate] Update OpenAPI + typed contract + API detail docs in the same PR.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
