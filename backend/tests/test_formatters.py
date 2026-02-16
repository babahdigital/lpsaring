import pytest

from app.utils.formatters import (
    format_to_local_phone,
    get_phone_number_variations,
    normalize_to_e164,
    normalize_to_local,
)


def test_normalize_to_e164_accepts_local_formats():
    assert normalize_to_e164("0811580039") == "+62811580039"
    assert normalize_to_e164("62811580039") == "+62811580039"
    assert normalize_to_e164("+62811580039") == "+62811580039"
    assert normalize_to_e164("811580039") == "+62811580039"
    assert normalize_to_e164("67512345678") == "+67512345678"
    assert normalize_to_e164("+67512345678") == "+67512345678"
    assert normalize_to_e164("0067512345678") == "+67512345678"
    assert normalize_to_e164("+123456789012345") == "+123456789012345"  # 15 digits (E.164 max)


def test_normalize_to_e164_rejects_invalid():
    with pytest.raises(ValueError):
        normalize_to_e164("")
    with pytest.raises(ValueError):
        normalize_to_e164("1234")
    with pytest.raises(ValueError):
        normalize_to_e164("0000000000")


def test_normalize_to_local():
    assert normalize_to_local("+62811580039") == "0811580039"
    assert normalize_to_local("62811580039") == "0811580039"
    assert normalize_to_local("0811580039") == "0811580039"


def test_format_to_local_phone():
    assert format_to_local_phone("+62811580039") == "0811580039"
    assert format_to_local_phone("62811580039") == "0811580039"
    assert format_to_local_phone("811580039") == "0811580039"
    assert format_to_local_phone("0811580039") == "0811580039"


def test_get_phone_number_variations_contains_expected():
    variations = get_phone_number_variations("0811580039")
    assert "+62811580039" in variations
    assert "62811580039" in variations
    assert "0811580039" in variations
    assert "811580039" in variations
