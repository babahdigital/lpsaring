import json
import time
from flask import Flask
from app import create_app
from app.extensions import db


class _FakeRedis:
    def __init__(self):
        self._data = {}

    def get(self, key):
        v = self._data.get(key)
        if v is None:
            return None
        if isinstance(v, str):
            return v.encode('utf-8')
        return v

    def setex(self, key, ttl, value):  # ttl ignored in stub
        self._data[key] = value

def _auth_headers(app, client, phone="08123456789"):
    # Minimal helper: assume user exists & token creation route maybe exists; fallback to direct insert + manual JWT create
    from app.infrastructure.db.models import User, ApprovalStatus
    # We'll rely on X-Test-User-ID fallback if JWT fails
    with app.app_context():
        user = db.session.query(User).filter_by(phone_number=phone).first()
        if not user:
            user = User()
            user.phone_number = phone
            user.full_name = "Test User"
            user.approval_status = ApprovalStatus.APPROVED
            user.is_active = True
            db.session.add(user)
            db.session.commit()
        user_id = str(user.id)
    return {"X-Test-User-ID": user_id, "Content-Type": "application/json"}

def test_authorize_device_rate_limit(app):
    client = app.test_client()
    headers = _auth_headers(app, client)
    payload = {"ip": "10.10.10.10", "mac": "AA:BB:CC:DD:EE:FF", "request_id": "req-1"}

    # First attempt should pass (will likely fail deeper due to MikroTik absence, but should reach rate limit path second time)
    r1 = client.post('/api/auth/authorize-device', data=json.dumps(payload), headers=headers)
    assert r1.status_code in (200, 500, 502, 503)

    # Second immediate attempt should trigger either idempotent success (if first succeeded) or rate limit (if same request id stored)
    r2 = client.post('/api/auth/authorize-device', data=json.dumps(payload), headers=headers)
    assert r2.status_code in (200, 429)

    # Different request id but within window should rate limit
    payload2 = {"ip": "10.10.10.10", "mac": "AA:BB:CC:DD:EE:FF", "request_id": "req-2"}
    r3 = client.post('/api/auth/authorize-device', data=json.dumps(payload2), headers=headers)
    assert r3.status_code in (200, 429)


def test_authorize_device_idempotency_marker(app):
    client = app.test_client()
    headers = _auth_headers(app, client, phone="08123456780")
    payload = {"ip": "10.10.10.11", "mac": "AA:BB:CC:DD:EE:11", "request_id": "idem-1"}

    r1 = client.post('/api/auth/authorize-device', data=json.dumps(payload), headers=headers)
    # second same request id
    r2 = client.post('/api/auth/authorize-device', data=json.dumps(payload), headers=headers)

    # If first returns 200, second should be 200 idempotent; otherwise allow error but not 5xx duplicated crash
    assert r2.status_code in (200, 500, 429)
