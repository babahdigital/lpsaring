from flask import Flask

from app.infrastructure.http import public_user_routes


class _FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False
        self.is_active = True

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.committed = False


class _FakeDb:
    def __init__(self, session):
        self.session = session


def _unwrap_decorators(func):
    current = func
    while hasattr(current, "__wrapped__"):
        current = current.__wrapped__
    return current


def _make_app(enabled: bool) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test"
    app.config["PUBLIC_DB_UPDATE_FORM_ENABLED"] = enabled
    return app


def test_public_db_update_submission_rejected_when_feature_disabled(monkeypatch):
    fake_session = _FakeSession()
    monkeypatch.setattr(public_user_routes, "db", _FakeDb(fake_session))

    impl = _unwrap_decorators(public_user_routes.create_public_database_update_submission)

    app = _make_app(enabled=False)
    with app.test_request_context(
        "/api/users/database-update-submissions",
        method="POST",
        json={
            "full_name": "User Test",
            "role": "KOMANDAN",
            "blok": "A",
            "kamar": "1",
        },
    ):
        response, status = impl()

    assert status == 403
    assert response.get_json()["success"] is False


def test_public_db_update_submission_accepts_blank_phone(monkeypatch):
    fake_session = _FakeSession()
    monkeypatch.setattr(public_user_routes, "db", _FakeDb(fake_session))

    impl = _unwrap_decorators(public_user_routes.create_public_database_update_submission)

    app = _make_app(enabled=True)
    with app.test_request_context(
        "/api/users/database-update-submissions",
        method="POST",
        json={
            "full_name": "Abdullah",
            "role": "tamping",
            "blok": "b",
            "kamar": "2",
            "phone_number": "",
        },
    ):
        response, status = impl()

    assert status == 201
    assert response.get_json()["success"] is True
    assert fake_session.committed is True
    assert len(fake_session.added) == 1

    created = fake_session.added[0]
    assert created.full_name == "Abdullah"
    assert created.role == "TAMPING"
    assert created.blok == "B"
    assert created.kamar == "Kamar_2"
    assert created.phone_number is None


def test_public_db_update_submission_rejects_invalid_role(monkeypatch):
    fake_session = _FakeSession()
    monkeypatch.setattr(public_user_routes, "db", _FakeDb(fake_session))

    impl = _unwrap_decorators(public_user_routes.create_public_database_update_submission)

    app = _make_app(enabled=True)
    with app.test_request_context(
        "/api/users/database-update-submissions",
        method="POST",
        json={
            "full_name": "Abdullah",
            "role": "USER",
            "blok": "A",
            "kamar": "1",
        },
    ):
        response, status = impl()

    assert status == 422
    payload = response.get_json()
    assert payload["success"] is False
