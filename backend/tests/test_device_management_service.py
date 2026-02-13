from app.services.device_management_service import normalize_mac


def test_normalize_mac_handles_none():
    assert normalize_mac(None) is None


def test_normalize_mac_normalizes_common_formats():
    assert normalize_mac("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert normalize_mac("aa:bb:cc:dd:ee:ff") == "AA:BB:CC:DD:EE:FF"


def test_normalize_mac_decodes_percent_encoded():
    assert normalize_mac("AA%3ABB%3ACC%3ADD%3AEE%3AFF") == "AA:BB:CC:DD:EE:FF"
    assert normalize_mac("AA%253ABB%253ACC%253ADD%253AEE%253AFF") == "AA:BB:CC:DD:EE:FF"
