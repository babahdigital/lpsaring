# backend/scripts/scan_external_hosts.py
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)

TEXT_FILE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".vue",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".env",
    ".example",
    ".html",
    ".ini",
    ".toml",
    ".sh",
}

SKIP_DIRS = {
    ".git",
    ".nuxt",
    ".next",
    "node_modules",
    ".pnpm-store",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


def _iter_files(root: Path):
    for path in root.rglob("*"):
        try:
            is_file = path.is_file()
        except OSError:
            continue
        if not is_file:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_FILE_SUFFIXES or path.name.endswith(".env"):
            yield path


def _extract_urls(content: str) -> list[str]:
    return URL_PATTERN.findall(content)


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").strip().lower()
    except Exception:
        return ""


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    findings: dict[str, set[str]] = defaultdict(set)

    for file_path in _iter_files(repo_root):
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for url in _extract_urls(content):
            host = _host(url)
            if not host:
                continue
            relative = file_path.relative_to(repo_root).as_posix()
            findings[host].add(relative)

    payload = {
        "root": repo_root.as_posix(),
        "total_hosts": len(findings),
        "hosts": [
            {
                "host": host,
                "files": sorted(files),
                "references": len(files),
            }
            for host, files in sorted(findings.items())
        ],
    }

    output_path = repo_root / "tmp" / "external_hosts_inventory.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Scanned external hosts: {payload['total_hosts']}")
    print(f"Output: {output_path.as_posix()}")


if __name__ == "__main__":
    main()
