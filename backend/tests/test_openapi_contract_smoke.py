from __future__ import annotations

from pathlib import Path


def _extract_declared_methods_for_path(spec_text: str, path: str) -> set[str]:
    marker = f"  {path}:"
    start = spec_text.find(marker)
    if start < 0:
        return set()

    trailing = spec_text[start + len(marker) :]
    lines = trailing.splitlines()
    methods: set[str] = set()
    for line in lines:
        if line.startswith("  /"):
            break
        stripped = line.strip().lower()
        if stripped in {"get:", "post:", "put:", "patch:", "delete:"}:
            methods.add(stripped.rstrip(":"))
    return methods


def test_openapi_priority_paths_and_methods_present():
    repo_root = Path(__file__).resolve().parents[2]
    spec_path = repo_root / 'contracts' / 'openapi' / 'openapi.v1.yaml'
    assert spec_path.exists(), f'OpenAPI spec not found: {spec_path}'

    spec_text = spec_path.read_text(encoding='utf-8')

    expected = {
        '/auth/me': {'get'},
        '/transactions/initiate': {'post'},
        '/transactions/debt/initiate': {'post'},
        '/transactions/by-order-id/{order_id}': {'get'},
        '/transactions/public/by-order-id/{order_id}': {'get'},
        '/transactions/{order_id}/cancel': {'post'},
        '/transactions/public/{order_id}/cancel': {'post'},
    }

    missing_paths = [path for path in expected if f'  {path}:' not in spec_text]
    assert not missing_paths, f'Missing contract paths: {missing_paths}'

    method_mismatches: list[str] = []
    for path, expected_methods in expected.items():
        declared = _extract_declared_methods_for_path(spec_text, path)
        if not expected_methods.issubset(declared):
            method_mismatches.append(f'{path} expected {sorted(expected_methods)} got {sorted(declared)}')

    assert not method_mismatches, f'Contract method mismatch: {method_mismatches}'
