from app.utils.mikrotik_duration import parse_routeros_duration_to_seconds


def test_parse_routeros_duration_to_seconds_routeros_units():
    assert parse_routeros_duration_to_seconds("10m") == 600
    assert parse_routeros_duration_to_seconds("45s") == 45
    assert parse_routeros_duration_to_seconds("1h") == 3600
    assert parse_routeros_duration_to_seconds("1h2m3s") == 3723
    assert parse_routeros_duration_to_seconds("2d5h") == 2 * 86400 + 5 * 3600


def test_parse_routeros_duration_to_seconds_hms():
    assert parse_routeros_duration_to_seconds("00:10:12") == 612
    assert parse_routeros_duration_to_seconds("1:02:03") == 3723


def test_parse_routeros_duration_to_seconds_invalid():
    assert parse_routeros_duration_to_seconds("") == 0
    assert parse_routeros_duration_to_seconds(None) == 0
    assert parse_routeros_duration_to_seconds("abc") == 0
