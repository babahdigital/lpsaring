from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(cwd), check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh requirements.lock.txt, validate sync, and optionally run targeted regression tests."
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip targeted regression tests after lockfile refresh and sync check.",
    )
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parents[1]
    python_exe = sys.executable

    lockfile_path = backend_dir / "requirements.lock.txt"
    check_script = backend_dir / "scripts" / "check_requirements_lock_sync.py"

    print("Refreshing lockfile from current environment...")
    result = subprocess.run([python_exe, "-m", "pip", "freeze"], cwd=str(backend_dir), check=True, capture_output=True, text=True)
    lockfile_path.write_text(result.stdout, encoding="utf-8")

    print("Validating requirements.txt <-> requirements.lock.txt sync...")
    _run([python_exe, str(check_script)], cwd=backend_dir)

    if not args.skip_tests:
        print("Running targeted regression tests...")
        _run(
            [
                python_exe,
                "-m",
                "pytest",
                "tests/test_transaction_public_status.py",
                "tests/test_transactions_lifecycle.py",
                "tests/test_auth_verify_otp_auto_authorize.py",
                "-q",
            ],
            cwd=backend_dir,
        )

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
