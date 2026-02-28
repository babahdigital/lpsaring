from app.services.user_management.user_profile import _resolve_unblock_notification_template


class _UserStub:
    pass


def test_unblock_notification_template_active(monkeypatch):
    user = _UserStub()
    monkeypatch.setattr(
        "app.services.user_management.user_profile.get_user_access_status",
        lambda _u: "active",
    )

    assert _resolve_unblock_notification_template(user) == "user_debt_cleared_unblock"


def test_unblock_notification_template_habis(monkeypatch):
    user = _UserStub()
    monkeypatch.setattr(
        "app.services.user_management.user_profile.get_user_access_status",
        lambda _u: "habis",
    )

    assert _resolve_unblock_notification_template(user) == "user_debt_cleared"
