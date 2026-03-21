from __future__ import annotations

from datetime import date, datetime, timezone

from app.utils.formatters import format_app_date_display, format_app_datetime_display


def test_format_app_date_display_accepts_iso_date_string():
    assert format_app_date_display("2026-03-21") == "21-03-2026"


def test_format_app_date_display_accepts_datetime_and_localizes():
    value = datetime(2026, 3, 21, 1, 2, 3, tzinfo=timezone.utc)
    assert format_app_date_display(value) == "21-03-2026"


def test_format_app_date_display_accepts_date_object():
    assert format_app_date_display(date(2026, 3, 21)) == "21-03-2026"


def test_format_app_datetime_display_accepts_iso_datetime_string():
    assert format_app_datetime_display("2026-03-21T01:02:03+00:00") == "21-03-2026 09:02:03"


def test_format_app_datetime_display_accepts_yyyy_mm_dd_string():
    assert format_app_datetime_display("2026-03-21", include_seconds=False) == "21-03-2026 08:00"


def test_format_app_datetime_display_preserves_existing_dd_mm_yyyy_input():
    assert format_app_datetime_display("21-03-2026 12:34", include_seconds=False) == "21-03-2026 12:34"