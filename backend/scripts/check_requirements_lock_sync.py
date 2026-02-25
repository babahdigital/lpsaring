from __future__ import annotations

from pathlib import Path


def _normalize_package_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _strip_inline_comment(line: str) -> str:
    in_brackets = 0
    for idx, ch in enumerate(line):
        if ch == "[":
            in_brackets += 1
        elif ch == "]" and in_brackets > 0:
            in_brackets -= 1
        elif ch == "#" and in_brackets == 0:
            return line[:idx].strip()
    return line.strip()


def _parse_pinned_requirements(path: Path) -> dict[str, str]:
    packages: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = _strip_inline_comment(raw)
        if not line:
            continue
        if line.startswith("-"):
            continue
        if "==" not in line:
            continue
        name_part, version = line.split("==", 1)
        package_name = _normalize_package_name(name_part.split("[", 1)[0])
        package_version = version.strip()
        if package_name and package_version:
            packages[package_name] = package_version
    return packages


def main() -> int:
    backend_dir = Path(__file__).resolve().parents[1]
    req_path = backend_dir / "requirements.txt"
    lock_path = backend_dir / "requirements.lock.txt"

    if not req_path.exists():
        print(f"ERROR: file not found: {req_path}")
        return 2
    if not lock_path.exists():
        print(f"ERROR: file not found: {lock_path}")
        return 2

    requirements = _parse_pinned_requirements(req_path)
    lockfile = _parse_pinned_requirements(lock_path)

    missing: list[str] = []
    mismatch: list[tuple[str, str, str]] = []

    for package_name, expected_version in sorted(requirements.items()):
        actual_version = lockfile.get(package_name)
        if actual_version is None:
            missing.append(package_name)
            continue
        if actual_version != expected_version:
            mismatch.append((package_name, expected_version, actual_version))

    if missing or mismatch:
        print("requirements.lock.txt is out of sync with requirements.txt")
        if missing:
            print("- Missing in lockfile:")
            for package_name in missing:
                print(f"  - {package_name}")
        if mismatch:
            print("- Version mismatch:")
            for package_name, expected, actual in mismatch:
                print(f"  - {package_name}: requirements.txt={expected}, requirements.lock.txt={actual}")
        print("Regenerate lockfile with: python -m pip freeze > requirements.lock.txt")
        return 1

    print("OK: requirements.txt and requirements.lock.txt are in sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())