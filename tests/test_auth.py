"""Tests for authentication module."""

import asyncio
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from synapse.auth import (
    APIKeyInfo,
    generate_api_key,
    hash_key,
    is_admin_key,
    is_localhost,
    load_auth_config,
    require_admin,
    require_auth,
    require_scope,
    reset_auth_config,
    validate_api_key,
)


def run_async(coro):
    """Helper to run async functions in sync tests."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


@pytest.fixture(autouse=True)
def reset_config():
    """Reset auth config before each test."""
    reset_auth_config()
    yield
    reset_auth_config()


class TestHashKey:
    """Tests for key hashing."""

    def test_hash_key_returns_hex_string(self):
        result = hash_key("test-key")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 produces 64 hex chars

    def test_hash_key_deterministic(self):
        key = "my-api-key"
        assert hash_key(key) == hash_key(key)

    def test_different_keys_different_hashes(self):
        assert hash_key("key1") != hash_key("key2")


class TestGenerateApiKey:
    """Tests for API key generation."""

    def test_generate_api_key_format(self):
        key = generate_api_key()
        assert key.startswith("synapse_")
        assert len(key) > 20

    def test_generate_api_key_unique(self):
        keys = [generate_api_key() for _ in range(10)]
        assert len(set(keys)) == 10


class TestLoadAuthConfig:
    """Tests for loading auth configuration."""

    def test_load_config_disabled_by_default(self):
        config = load_auth_config()
        assert config.enabled is False

    def test_load_config_enabled(self):
        with patch.dict(os.environ, {"SYNAPSE_AUTH_ENABLED": "true"}):
            reset_auth_config()
            config = load_auth_config()
            assert config.enabled is True

    def test_load_config_with_api_keys(self):
        with patch.dict(
            os.environ,
            {"SYNAPSE_AUTH_ENABLED": "true", "SYNAPSE_API_KEYS": "key1,key2,key3"},
        ):
            reset_auth_config()
            config = load_auth_config()
            assert len(config.api_keys) == 3

    def test_load_config_with_admin_key(self):
        with patch.dict(os.environ, {"SYNAPSE_ADMIN_KEY": "admin-secret"}):
            reset_auth_config()
            config = load_auth_config()
            assert config.admin_key_hash is not None

    def test_load_config_allow_localhost_default(self):
        """Test that allow_localhost is True by default."""
        reset_auth_config()
        config = load_auth_config()
        assert config.allow_localhost is True

    def test_load_config_allow_localhost_disabled(self):
        """Test that allow_localhost can be disabled via environment variable."""
        with patch.dict(os.environ, {"SYNAPSE_ALLOW_LOCALHOST": "false"}):
            reset_auth_config()
            config = load_auth_config()
            assert config.allow_localhost is False

    def test_load_config_allow_localhost_explicit_true(self):
        """Test that allow_localhost can be explicitly enabled."""
        with patch.dict(os.environ, {"SYNAPSE_ALLOW_LOCALHOST": "true"}):
            reset_auth_config()
            config = load_auth_config()
            assert config.allow_localhost is True


class TestValidateApiKey:
    """Tests for API key validation."""

    def test_validate_valid_key(self):
        with patch.dict(
            os.environ,
            {"SYNAPSE_AUTH_ENABLED": "true", "SYNAPSE_API_KEYS": "valid-key"},
        ):
            reset_auth_config()
            result = validate_api_key("valid-key")
            assert result is not None
            assert isinstance(result, APIKeyInfo)

    def test_validate_invalid_key(self):
        with patch.dict(
            os.environ,
            {"SYNAPSE_AUTH_ENABLED": "true", "SYNAPSE_API_KEYS": "valid-key"},
        ):
            reset_auth_config()
            result = validate_api_key("invalid-key")
            assert result is None

    def test_validate_empty_key(self):
        result = validate_api_key("")
        assert result is None

    def test_validate_expired_key(self):
        """Expired key should be rejected."""
        from datetime import datetime, timedelta, timezone

        # Create an expired key
        expired_key = "expired-test-key"
        expired_key_info = APIKeyInfo(
            key_hash=hash_key(expired_key),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        with patch.dict(os.environ, {"SYNAPSE_AUTH_ENABLED": "true"}):
            reset_auth_config()
            # Manually add expired key to config
            config = load_auth_config()
            config.api_keys.append(expired_key_info)
            result = validate_api_key(expired_key)
            assert result is None


class TestIsAdminKey:
    """Tests for admin key checking."""

    def test_is_admin_key_valid(self):
        with patch.dict(os.environ, {"SYNAPSE_ADMIN_KEY": "admin-secret"}):
            reset_auth_config()
            assert is_admin_key("admin-secret") is True

    def test_is_admin_key_invalid(self):
        with patch.dict(os.environ, {"SYNAPSE_ADMIN_KEY": "admin-secret"}):
            reset_auth_config()
            assert is_admin_key("wrong-key") is False

    def test_is_admin_key_no_admin_key_set(self):
        reset_auth_config()
        assert is_admin_key("any-key") is False


class TestIsLocalhost:
    """Tests for localhost detection."""

    def test_is_localhost_127_0_0_1(self):
        request = MagicMock()
        request.client.host = "127.0.0.1"
        assert is_localhost(request) is True

    def test_is_localhost_ipv6(self):
        request = MagicMock()
        request.client.host = "::1"
        assert is_localhost(request) is True

    def test_is_localhost_false(self):
        request = MagicMock()
        request.client.host = "192.168.1.100"
        assert is_localhost(request) is False

    def test_is_localhost_no_client(self):
        request = MagicMock()
        request.client = None
        assert is_localhost(request) is True


class TestRequireAuthDependency:
    """Tests for require_auth FastAPI dependency."""

    def test_require_auth_disabled(self):
        """When auth is disabled, should return None."""
        request = MagicMock()
        result = run_async(require_auth(request, api_key=None))
        assert result is None

    def test_require_auth_localhost_allowed(self):
        """Localhost should be allowed when configured."""
        with patch.dict(os.environ, {"SYNAPSE_AUTH_ENABLED": "true"}):
            reset_auth_config()
            request = MagicMock()
            request.client.host = "127.0.0.1"
            result = run_async(require_auth(request, api_key=None))
            assert result is None

    def test_require_auth_no_key_raises(self):
        """Missing API key should raise 401."""
        with (
            patch.dict(os.environ, {"SYNAPSE_AUTH_ENABLED": "true"}),
            pytest.raises(HTTPException) as exc_info,
        ):
            reset_auth_config()
            request = MagicMock()
            request.client.host = "192.168.1.100"

            run_async(require_auth(request, api_key=None))

        assert exc_info.value.status_code == 401
        assert "API key required" in exc_info.value.detail

    def test_require_auth_invalid_key_raises(self):
        """Invalid API key should raise 401."""
        with (
            patch.dict(
                os.environ,
                {"SYNAPSE_AUTH_ENABLED": "true", "SYNAPSE_API_KEYS": "valid-key"},
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            reset_auth_config()
            request = MagicMock()
            request.client.host = "192.168.1.100"

            run_async(require_auth(request, api_key="invalid-key"))

        assert exc_info.value.status_code == 401
        assert "Invalid API key" in exc_info.value.detail

    def test_require_auth_valid_key_passes(self):
        """Valid API key should return APIKeyInfo."""
        with patch.dict(
            os.environ,
            {"SYNAPSE_AUTH_ENABLED": "true", "SYNAPSE_API_KEYS": "valid-key"},
        ):
            reset_auth_config()
            request = MagicMock()
            request.client.host = "192.168.1.100"

            result = run_async(require_auth(request, api_key="valid-key"))
            assert isinstance(result, APIKeyInfo)


class TestRequireAdminDependency:
    """Tests for require_admin FastAPI dependency."""

    def test_require_admin_disabled(self):
        """When auth is disabled, should pass."""
        request = MagicMock()
        result = run_async(require_admin(request, api_key=None))
        assert result is None

    def test_require_admin_no_key_raises(self):
        """Missing API key should raise 401."""
        with (
            patch.dict(os.environ, {"SYNAPSE_AUTH_ENABLED": "true"}),
            pytest.raises(HTTPException) as exc_info,
        ):
            reset_auth_config()
            request = MagicMock()
            request.client.host = "192.168.1.100"

            run_async(require_admin(request, api_key=None))

        assert exc_info.value.status_code == 401

    def test_require_admin_non_admin_key_raises(self):
        """Non-admin key should raise 403."""
        with (
            patch.dict(
                os.environ,
                {"SYNAPSE_AUTH_ENABLED": "true", "SYNAPSE_ADMIN_KEY": "admin-secret"},
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            reset_auth_config()
            request = MagicMock()
            request.client.host = "192.168.1.100"

            run_async(require_admin(request, api_key="user-key"))

        assert exc_info.value.status_code == 403

    def test_require_admin_valid_admin_key_passes(self):
        """Admin key should pass."""
        with patch.dict(
            os.environ,
            {"SYNAPSE_AUTH_ENABLED": "true", "SYNAPSE_ADMIN_KEY": "admin-secret"},
        ):
            reset_auth_config()
            request = MagicMock()
            request.client.host = "192.168.1.100"

            result = run_async(require_admin(request, api_key="admin-secret"))
            assert result is None


class TestRequireScopeDependency:
    """Tests for require_scope FastAPI dependency."""

    def test_require_scope_disabled(self):
        """When auth is disabled, should pass."""
        check_scope = require_scope("admin")
        request = MagicMock()
        result = run_async(check_scope(request, api_key=None))
        assert result is None

    def test_require_scope_no_key_raises(self):
        """Missing API key should raise 401."""
        with (
            patch.dict(os.environ, {"SYNAPSE_AUTH_ENABLED": "true"}),
            pytest.raises(HTTPException) as exc_info,
        ):
            reset_auth_config()
            check_scope = require_scope("admin")
            request = MagicMock()
            request.client.host = "192.168.1.100"

            run_async(check_scope(request, api_key=None))

        assert exc_info.value.status_code == 401


class TestIntegration:
    """Integration tests with FastAPI TestClient."""

    def test_protected_endpoint_without_auth(self):
        """Protected endpoint should work when auth is disabled."""
        app = FastAPI()

        @app.get("/protected")
        async def protected(_=Depends(require_auth)):
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/protected")
        assert response.status_code == 200

    def test_protected_endpoint_with_auth_enabled_no_key(self):
        """Protected endpoint should reject without key when auth enabled."""
        with (
            patch.dict(os.environ, {"SYNAPSE_AUTH_ENABLED": "true"}),
            patch("synapse.auth.is_localhost", return_value=False),
        ):
            reset_auth_config()

            app = FastAPI()

            @app.get("/protected")
            async def protected(_=Depends(require_auth)):
                return {"status": "ok"}

            client = TestClient(app)
            # TestClient uses localhost by default, which is allowed
            # So we need to override the client host check
            response = client.get("/protected")
            assert response.status_code == 401

    def test_protected_endpoint_with_valid_key(self):
        """Protected endpoint should accept valid key."""
        with (
            patch.dict(
                os.environ,
                {"SYNAPSE_AUTH_ENABLED": "true", "SYNAPSE_API_KEYS": "test-key"},
            ),
            patch("synapse.auth.is_localhost", return_value=False),
        ):
            reset_auth_config()

            app = FastAPI()

            @app.get("/protected")
            async def protected(_=Depends(require_auth)):
                return {"status": "ok"}

            client = TestClient(app)
            response = client.get("/protected", headers={"X-API-Key": "test-key"})
            assert response.status_code == 200

    def test_protected_endpoint_with_query_param_key(self):
        """Protected endpoint should accept key via query param."""
        with (
            patch.dict(
                os.environ,
                {"SYNAPSE_AUTH_ENABLED": "true", "SYNAPSE_API_KEYS": "test-key"},
            ),
            patch("synapse.auth.is_localhost", return_value=False),
        ):
            reset_auth_config()

            app = FastAPI()

            @app.get("/protected")
            async def protected(_=Depends(require_auth)):
                return {"status": "ok"}

            client = TestClient(app)
            response = client.get("/protected?api_key=test-key")
            assert response.status_code == 200
