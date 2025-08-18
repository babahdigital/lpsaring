# tests/conftest.py
# pyright: reportArgumentType=false
import os
import pytest

# Ensure mandatory config env vars exist before importing app/config
os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('JWT_SECRET_KEY', 'jwt-test-secret')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('ALLOW_LAX_CONFIG_IMPORT', '1')
os.environ.setdefault('RATELIMIT_STORAGE_URI', 'memory://')

from app import create_app
from app.extensions import db as _db
from flask_limiter.extension import Limiter

@pytest.fixture(scope="session")
def app():
    app = create_app('testing')
    # Apply overrides
    app.config.update({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "JWT_SECRET_KEY": "jwt-test-secret",
        "RATELIMIT_ENABLED": False,
    })
    with app.app_context():
        # Attach fake redis client to simulate rate limiting / idempotency
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
            def setex(self, key, ttl, value):
                self._data[key] = value
            def ping(self):
                return True
            def delete(self, *keys):
                for k in keys:
                    self._data.pop(k, None)
            def keys(self, pattern):  # simplistic
                prefix = pattern.replace('*','')
                return [k for k in self._data if k.startswith(prefix)]
        app.redis_client_otp = _FakeRedis()  # type: ignore[attr-defined]
        # Disable limiter storage hitting real redis
        app.config['RATELIMIT_ENABLED'] = False
        # Monkey patch limiter to bypass storage calls
        limiter = app.extensions.get('limiter')
        if limiter and isinstance(limiter, Limiter):
            limiter._storage = None  # type: ignore
            limiter.hit = lambda *a, **k: None  # type: ignore
        # Remove any before_request funcs referencing flask_limiter to prevent redis usage
        for bp, funcs in list(app.before_request_funcs.items()):
            app.before_request_funcs[bp] = [f for f in funcs if 'flask_limiter' not in getattr(f, '__module__', '')]
        _db.create_all()
        yield app
        _db.drop_all()

@pytest.fixture(scope="function")
def client(app):
    return app.test_client()