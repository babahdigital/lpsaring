from __future__ import annotations

import sys
from pathlib import Path


FORBIDDEN_PATTERNS = (
    'typescript-version/full-version',
    'starter-kit/src',
)

ALLOWED_EXTENSIONS = {'.ts', '.tsx', '.vue', '.js', '.jsx', '.mjs', '.cjs'}


def iter_frontend_source(frontend_dir: Path):
    for path in frontend_dir.rglob('*'):
        if not path.is_file():
            continue
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        relative = path.relative_to(frontend_dir)
        if any(part in {'.nuxt', '.output', 'node_modules', 'dist'} for part in relative.parts):
            continue
        yield path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    frontend_dir = repo_root / 'frontend'
    if not frontend_dir.exists():
        print('[ui-standards] frontend directory not found; skip')
        return 0

    violations: list[str] = []
    for file_path in iter_frontend_source(frontend_dir):
        try:
            text = file_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue

        for pattern in FORBIDDEN_PATTERNS:
            if pattern in text:
                rel = file_path.relative_to(repo_root).as_posix()
                violations.append(f'{rel}: contains forbidden reference "{pattern}"')

    if violations:
        print('[ui-standards] FAILED: forbidden template references found')
        for item in violations:
            print(f' - {item}')
        print('Use docs/UI_STYLING_STANDARDS.md as reference; do not import/copy runtime from Vuexy full-version.')
        return 1

    print('[ui-standards] OK: no forbidden full-version/starter-kit runtime references detected')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
