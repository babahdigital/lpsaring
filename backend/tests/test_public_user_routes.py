# pyright: reportCallIssue=false
import json
from http import HTTPStatus

def test_body_kosong(client):
    resp = client.post("/api/users/check-or-register", data="{}", content_type="application/json")
    assert resp.status_code == HTTPStatus.BAD_REQUEST

def test_payload_salah_tipe(client):
    resp = client.post("/api/users/check-or-register",
                       data=json.dumps({"phone_number": 123}),  # seharusnya string
                       content_type="application/json")
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

def test_nomor_terdaftar(client, app):
    # Insert dummy user
    from app.infrastructure.db.models import User
    from app.extensions import db
    with app.app_context():
        user = User(full_name="X", phone_number="+62812345678")
        db.session.add(user); db.session.commit()
    resp = client.post("/api/users/check-or-register",
                       data=json.dumps({"phone_number": "+62812345678"}),
                       content_type="application/json")
    body = resp.get_json()
    assert body["user_exists"] is True

def test_nomor_baru(client):
    resp = client.post("/api/users/check-or-register",
                       data=json.dumps({"phone_number": "+62887654321"}),
                       content_type="application/json")
    body = resp.get_json()
    assert body["user_exists"] is False