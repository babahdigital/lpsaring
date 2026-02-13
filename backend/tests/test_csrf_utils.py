from app.utils.csrf_utils import is_trusted_origin


def test_is_trusted_origin_matches_exact_origin():
    trusted = ["https://portal.example.com", "http://localhost:3010"]
    assert is_trusted_origin("https://portal.example.com", trusted)
    assert is_trusted_origin("http://localhost:3010", trusted)


def test_is_trusted_origin_rejects_missing_or_malformed():
    trusted = ["https://portal.example.com"]
    assert not is_trusted_origin(None, trusted)
    assert not is_trusted_origin("", trusted)
    assert not is_trusted_origin("portal.example.com", trusted)
    assert not is_trusted_origin("https://evil.example.com", trusted)
