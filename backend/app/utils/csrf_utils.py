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
    return f"{parsed.scheme}://{parsed.netloc}"


def is_trusted_origin(origin: Optional[str], trusted_origins: Iterable[str]) -> bool:
    if not origin:
        return False
    normalized_origin = _normalize_origin(origin)
    if not normalized_origin:
        return False
    normalized_trusted = {_normalize_origin(item) for item in trusted_origins if item}
    normalized_trusted.discard(None)
    return normalized_origin in normalized_trusted
