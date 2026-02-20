from __future__ import annotations

import re
from typing import Optional


_HMS_RE = re.compile(r"^(?P<h>\d+):(?P<m>\d{1,2}):(?P<s>\d{1,2})$")
_RO_RE = re.compile(r"^(?:(?P<d>\d+)d)?(?:(?P<h>\d+)h)?(?:(?P<m>\d+)m)?(?:(?P<s>\d+)s)?$")


def parse_routeros_duration_to_seconds(value: Optional[str]) -> int:
    """Parse common RouterOS duration strings to seconds.

    Supported examples:
    - "10m", "1h2m3s", "2d5h", "45s"
    - "01:02:03" (HH:MM:SS)

    Returns 0 on invalid/empty input.
    """
    if not value:
        return 0
    text = str(value).strip()
    if not text:
        return 0

    m = _HMS_RE.match(text)
    if m:
        h = int(m.group("h"))
        minutes = int(m.group("m"))
        s = int(m.group("s"))
        return max(0, h * 3600 + minutes * 60 + s)

    # RouterOS style: 2d5h10m3s (any subset)
    m = _RO_RE.match(text)
    if not m:
        return 0

    # Reject plain "" or unmatched garbage. Our regex matches empty groups, so ensure at least one unit exists.
    if not any(m.group(k) for k in ("d", "h", "m", "s")):
        return 0

    days = int(m.group("d") or 0)
    hours = int(m.group("h") or 0)
    minutes = int(m.group("m") or 0)
    seconds = int(m.group("s") or 0)
    return max(0, days * 86400 + hours * 3600 + minutes * 60 + seconds)
