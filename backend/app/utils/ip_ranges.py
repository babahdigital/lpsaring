from __future__ import annotations

import ipaddress
from typing import Iterable, Set


def expand_ip_tokens(tokens: Iterable[str]) -> Set[str]:
    """Expand IP tokens into a set of IP strings.

    Supported tokens:
    - Single IP: "172.16.2.3"
    - Full range: "172.16.2.3-172.16.2.7"
    - Shorthand range (same /24): "172.16.2.3-7" (expands to 172.16.2.3..172.16.2.7)
    - Comma-separated strings are allowed inside a token and will be split.
    """
    result: Set[str] = set()

    def _add_single(ip_text: str) -> None:
        try:
            ip_obj = ipaddress.ip_address(ip_text)
        except Exception:
            return
        result.add(str(ip_obj))

    def _expand_range(start_text: str, end_text: str) -> None:
        try:
            start_ip = ipaddress.ip_address(start_text)
            end_ip = ipaddress.ip_address(end_text)
        except Exception:
            return
        if start_ip.version != end_ip.version:
            return
        start_int = int(start_ip)
        end_int = int(end_ip)
        if end_int < start_int:
            start_int, end_int = end_int, start_int
        for i in range(start_int, end_int + 1):
            result.add(str(ipaddress.ip_address(i)))

    for raw in tokens:
        if raw is None:
            continue
        for part in str(raw).split(","):
            text = part.strip()
            if not text:
                continue

            if "-" not in text:
                _add_single(text)
                continue

            left, right = (s.strip() for s in text.split("-", 1))
            if not left or not right:
                continue

            # Shorthand: 172.16.2.3-7
            if "." in left and "." not in right and right.isdigit():
                left_parts = left.split(".")
                if len(left_parts) == 4:
                    right_full = ".".join(left_parts[:3] + [right])
                    _expand_range(left, right_full)
                    continue

            _expand_range(left, right)

    return result
