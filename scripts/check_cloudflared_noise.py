#!/usr/bin/env python3
"""Cloudflared context-canceled noise checker for production monitoring.

Run this script on the host that runs container `global-cloudflared`.
It reads docker logs for a time window, calculates context-canceled counts,
and returns a non-zero exit code when thresholds are exceeded.

Exit codes:
- 0: OK
- 1: WARN
- 2: CRITICAL
- 3: runtime error (docker/log command failed)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass


_CONTEXT_PATTERN = re.compile(r"context canceled", re.IGNORECASE)
_REQUEST_FAILED_PATTERN = re.compile(r"request failed", re.IGNORECASE)
_STREAM_CLOSED_PATTERN = re.compile(r"stream closed|connection with edge closed", re.IGNORECASE)


@dataclass
class NoiseSummary:
    container: str
    window: str
    total_lines: int
    request_failed_count: int
    context_canceled_count: int
    stream_closed_count: int
    context_canceled_ratio: float
    severity: str


def _run_logs(container: str, window: str) -> str:
    cmd = ["docker", "logs", "--since", window, container]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)

    # docker logs writes mostly to stderr.
    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)

    if completed.returncode != 0:
        raise RuntimeError(
            f"docker logs failed (exit={completed.returncode}) for container={container}: {output.strip()}"
        )

    return output


def _build_summary(raw_logs: str, *, container: str, window: str) -> NoiseSummary:
    lines = [line for line in raw_logs.splitlines() if line.strip()]
    request_failed_count = sum(1 for line in lines if _REQUEST_FAILED_PATTERN.search(line))
    context_canceled_count = sum(1 for line in lines if _CONTEXT_PATTERN.search(line))
    stream_closed_count = sum(1 for line in lines if _STREAM_CLOSED_PATTERN.search(line))

    ratio = 0.0
    if request_failed_count > 0:
        ratio = context_canceled_count / request_failed_count

    return NoiseSummary(
        container=container,
        window=window,
        total_lines=len(lines),
        request_failed_count=request_failed_count,
        context_canceled_count=context_canceled_count,
        stream_closed_count=stream_closed_count,
        context_canceled_ratio=round(ratio, 4),
        severity="ok",
    )


def _determine_severity(
    summary: NoiseSummary,
    *,
    warn_count: int,
    crit_count: int,
    warn_ratio: float,
    crit_ratio: float,
) -> tuple[str, int]:
    ratio = summary.context_canceled_ratio
    count = summary.context_canceled_count

    if count >= crit_count or ratio >= crit_ratio:
        return "critical", 2
    if count >= warn_count or ratio >= warn_ratio:
        return "warn", 1
    return "ok", 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check cloudflared context-canceled noise level.")
    parser.add_argument("--container", default="global-cloudflared", help="Container name (default: global-cloudflared)")
    parser.add_argument("--window", default="6h", help="docker logs --since value (default: 6h)")
    parser.add_argument("--warn-count", type=int, default=30, help="Warn threshold for context-canceled count")
    parser.add_argument("--crit-count", type=int, default=120, help="Critical threshold for context-canceled count")
    parser.add_argument("--warn-ratio", type=float, default=0.35, help="Warn threshold for context-canceled/request-failed ratio")
    parser.add_argument("--crit-ratio", type=float, default=0.65, help="Critical threshold for context-canceled/request-failed ratio")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        raw_logs = _run_logs(args.container, args.window)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "container": args.container,
                    "window": args.window,
                    "severity": "error",
                    "message": str(exc),
                },
                ensure_ascii=True,
            )
        )
        return 3

    summary = _build_summary(raw_logs, container=args.container, window=args.window)
    severity, code = _determine_severity(
        summary,
        warn_count=args.warn_count,
        crit_count=args.crit_count,
        warn_ratio=args.warn_ratio,
        crit_ratio=args.crit_ratio,
    )
    summary.severity = severity

    print(json.dumps(asdict(summary), ensure_ascii=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
