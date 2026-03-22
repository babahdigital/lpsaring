"""
Test suite untuk production configuration security (SEC-1).

Coverage:
- RuntimeError raised for hardcoded SECRET_KEY in production
- RuntimeError raised for hardcoded JWT_SECRET_KEY in production
- Normal operation in development/testing
"""

import pytest
import os
from unittest.mock import patch
import importlib
import sys


def _reload_config_module():
    sys.modules.pop("config", None)
    return importlib.import_module("config")


class TestSecretKeyProductionGuard:
    """Test SECRET_KEY and JWT_SECRET_KEY production guards."""

    def test_secret_key_hardcoded_in_production_raises_runtime_error(self):
        """Test that RuntimeError is raised if SECRET_KEY is hardcoded in production."""
        # This test verifies SEC-1 fix

        with patch.dict(
            os.environ,
            {
                "FLASK_ENV": "production",
                "SECRET_KEY": "",  # Empty to trigger default
                "JWT_SECRET_KEY": "valid-jwt-secret-key-xxxxxxxx",
                "DATABASE_URL": "sqlite:///:memory:",
                "SKIP_DOTENV_AUTOLOAD": "1",
            },
            clear=False,
        ):
            with pytest.raises(RuntimeError) as exc_info:
                _reload_config_module()

            assert "CRITICAL" in str(exc_info.value)
            assert "SECRET_KEY" in str(exc_info.value)
            assert "production" in str(exc_info.value).lower()

    def test_jwt_secret_key_hardcoded_in_production_raises_runtime_error(self):
        """Test that RuntimeError is raised if JWT_SECRET_KEY is hardcoded in production."""
        # This test verifies SEC-1 fix for JWT key
        with patch.dict(
            os.environ,
            {
                "FLASK_ENV": "production",
                "SECRET_KEY": "valid-secret-key-xxxxxxxxxxxx",
                "JWT_SECRET_KEY": "",  # Empty to trigger default
                "DATABASE_URL": "sqlite:///:memory:",
                "SKIP_DOTENV_AUTOLOAD": "1",
            },
            clear=False,
        ):
            with pytest.raises(RuntimeError) as exc_info:
                _reload_config_module()

            assert "CRITICAL" in str(exc_info.value)
            assert "JWT_SECRET_KEY" in str(exc_info.value)
            assert "production" in str(exc_info.value).lower()

    def test_secret_key_valid_in_production_with_env_var(self):
        """Test that valid env vars work in production."""
        with patch.dict(
            os.environ,
            {
                "FLASK_ENV": "production",
                "SECRET_KEY": "valid-secret-key-xxxxxxxxxxxx",
                "JWT_SECRET_KEY": "valid-jwt-secret-key-xxxxxxxx",
                "DATABASE_URL": "sqlite:///:memory:",
                "SKIP_DOTENV_AUTOLOAD": "1",
            },
            clear=False,
        ):
            config_module = _reload_config_module()

            # Should NOT raise error
            assert config_module.Config.SECRET_KEY == "valid-secret-key-xxxxxxxxxxxx"
            assert (
                config_module.Config.JWT_SECRET_KEY
                == "valid-jwt-secret-key-xxxxxxxx"
            )

    def test_hardcoded_keys_allowed_in_development(self):
        """Test that hardcoded keys are allowed in development without error."""
        with patch.dict(
            os.environ,
            {
                "FLASK_ENV": "development",
                "SECRET_KEY": "",  # Will use default
                "JWT_SECRET_KEY": "",  # Will use default
                "DATABASE_URL": "sqlite:///:memory:",
                "SKIP_DOTENV_AUTOLOAD": "1",
            },
            clear=False,
        ):
            config_module = _reload_config_module()

            # Should use defaults without error
            assert config_module.Config.SECRET_KEY == "dev-secret-key-ganti-ini-di-produksi"
            assert (
                config_module.Config.JWT_SECRET_KEY
                == "dev-jwt-secret-key-ganti-ini-di-produksi"
            )
