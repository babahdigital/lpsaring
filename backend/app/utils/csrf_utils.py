from __future__ import annotations

from typing import Iterable, Optional
from urllib.parse import urlparse


def _normalize_origin(origin: str) -> Optional[str]:
    if not origin:
        return None
    try:
        parsed = urlparse(origin)
    except ValueError:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None
    # Sprint 17 BUG-3 (LOW): RFC 6454 mandates case-insensitive host comparison
    # + default-port equivalence. Sebelumnya pakai `parsed.netloc` apa adanya
    # → `Origin: https://Example.COM` atau `https://example.com:443` TIDAK
    # match `https://example.com` di trusted list → legitimate request 403.
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return None
    port = parsed.port
    # Strip port kalau matches scheme default.
    if port is not None and (
        (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    ):
        port = None
    netloc = f"{hostname}:{port}" if port is not None else hostname
    return f"{scheme}://{netloc}"


def is_trusted_origin(origin: Optional[str], trusted_origins: Iterable[str]) -> bool:
    if not origin:
        return False
    normalized_origin = _normalize_origin(origin)
    if not normalized_origin:
        return False
    normalized_trusted = {_normalize_origin(item) for item in trusted_origins if item}
    normalized_trusted.discard(None)
    return normalized_origin in normalized_trusted
