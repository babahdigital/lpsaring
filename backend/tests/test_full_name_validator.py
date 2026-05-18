from __future__ import annotations

import pytest

from app.infrastructure.http.schemas.auth_schemas import _validate_full_name


def test_full_name_accepts_valid_indonesian_name() -> None:
    assert _validate_full_name("Abdullah Setiawan") == "Abdullah Setiawan"


def test_full_name_accepts_apostrophe_dash_dot() -> None:
    assert _validate_full_name("Mary-Ann O'Connor Jr.") == "Mary-Ann O'Connor Jr."


def test_full_name_strips_surrounding_whitespace() -> None:
    assert _validate_full_name("  Abdullah  ") == "Abdullah"


def test_full_name_rejects_too_short() -> None:
    with pytest.raises(ValueError, match="minimal 2 karakter"):
        _validate_full_name("A")


def test_full_name_rejects_too_long() -> None:
    with pytest.raises(ValueError, match="maksimal 80 karakter"):
        _validate_full_name("A" * 81)


def test_full_name_rejects_newline_injection() -> None:
    with pytest.raises(ValueError, match="karakter tidak valid"):
        _validate_full_name("Abdullah\nSetiawan")


def test_full_name_rejects_null_byte() -> None:
    with pytest.raises(ValueError, match="karakter tidak valid"):
        _validate_full_name("Abdullah\x00ST")


def test_full_name_rejects_rtl_override() -> None:
    # U+202E = Right-to-Left Override — sering dipakai spoofing.
    with pytest.raises(ValueError, match="karakter tidak valid"):
        _validate_full_name("Abdullah‮ST")


def test_full_name_rejects_zero_width_joiner() -> None:
    # U+200D = Zero Width Joiner.
    with pytest.raises(ValueError, match="karakter tidak valid"):
        _validate_full_name("Abdul‍lah")


def test_full_name_rejects_non_string() -> None:
    with pytest.raises(ValueError, match="berupa teks"):
        _validate_full_name(123)  # type: ignore[arg-type]
