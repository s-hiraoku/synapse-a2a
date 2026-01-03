"""
Authentication and Authorization for Synapse A2A.

Provides API Key authentication with optional OAuth2 support.
"""

import hashlib
import hmac
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader, APIKeyQuery

# Environment variable names
ENV_API_KEYS = "SYNAPSE_API_KEYS"  # Comma-separated list of valid API keys
ENV_AUTH_ENABLED = "SYNAPSE_AUTH_ENABLED"  # "true" to enable, default disabled
ENV_ADMIN_KEY = "SYNAPSE_ADMIN_KEY"  # Admin key for management operations
ENV_ALLOW_LOCALHOST = "SYNAPSE_ALLOW_LOCALHOST"  # "false" to require auth for localhost


@dataclass
class APIKeyInfo:
    """Information about an API key."""

    key_hash: str  # SHA-256 hash of the key
    name: str = "default"
    scopes: set[str] = field(default_factory=lambda: {"read", "write"})
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    rate_limit: int = 1000  # Requests per hour


@dataclass
class AuthConfig:
    """Authentication configuration."""

    enabled: bool = False
    api_keys: list[APIKeyInfo] = field(default_factory=list)
    allow_localhost: bool = True  # Skip auth for localhost
    admin_key_hash: str | None = None


# Global auth configuration
_auth_config: AuthConfig | None = None


def hash_key(key: str) -> str:
    """Hash an API key using SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    """Generate a new random API key."""
    return f"synapse_{secrets.token_urlsafe(32)}"


def load_auth_config() -> AuthConfig:
    """Load authentication configuration from environment."""
    global _auth_config

    if _auth_config is not None:
        return _auth_config

    enabled = os.environ.get(ENV_AUTH_ENABLED, "").lower() == "true"

    api_keys = []
    keys_str = os.environ.get(ENV_API_KEYS, "")
    if keys_str:
        for key in keys_str.split(","):
            key = key.strip()
            if key:
                api_keys.append(APIKeyInfo(key_hash=hash_key(key)))

    admin_key = os.environ.get(ENV_ADMIN_KEY)
    admin_key_hash = hash_key(admin_key) if admin_key else None

    # Allow localhost by default, unless explicitly disabled
    allow_localhost_str = os.environ.get(ENV_ALLOW_LOCALHOST, "true").lower()
    allow_localhost = allow_localhost_str != "false"

    _auth_config = AuthConfig(
        enabled=enabled,
        api_keys=api_keys,
        admin_key_hash=admin_key_hash,
        allow_localhost=allow_localhost,
    )

    return _auth_config


def reset_auth_config() -> None:
    """Reset auth config (for testing)."""
    global _auth_config
    _auth_config = None


def is_localhost(request: Request) -> bool:
    """Check if request is from localhost."""
    client_host = request.client.host if request.client else None
    return client_host in ("127.0.0.1", "localhost", "::1", None)


def validate_api_key(key: str, required_scope: str | None = None) -> APIKeyInfo | None:
    """
    Validate an API key and return its info.

    Args:
        key: The API key to validate
        required_scope: Optional scope that must be present

    Returns:
        APIKeyInfo if valid, None otherwise
    """
    config = load_auth_config()
    key_hash = hash_key(key)

    for api_key in config.api_keys:
        if hmac.compare_digest(api_key.key_hash, key_hash):
            # Check expiration
            if api_key.expires_at and datetime.now(timezone.utc) > api_key.expires_at:
                return None

            # Check scope
            if required_scope and required_scope not in api_key.scopes:
                return None

            return api_key

    return None


def is_admin_key(key: str) -> bool:
    """Check if the key is the admin key."""
    config = load_auth_config()
    if not config.admin_key_hash:
        return False
    return hmac.compare_digest(config.admin_key_hash, hash_key(key))


# FastAPI security schemes
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)


async def get_api_key(
    request: Request,
    api_key_header_value: str | None = Security(api_key_header),
    api_key_query_value: str | None = Security(api_key_query),
) -> str | None:
    """
    Extract API key from request (header or query parameter).

    FastAPI dependency that extracts the API key from either:
    - X-API-Key header
    - api_key query parameter
    """
    return api_key_header_value or api_key_query_value


async def require_auth(
    request: Request,
    api_key: str | None = Security(get_api_key),
) -> APIKeyInfo | None:
    """
    FastAPI dependency that requires authentication.

    Raises HTTPException 401 if authentication fails.
    Returns APIKeyInfo for valid authenticated requests.
    Allows localhost requests if configured.
    """
    config = load_auth_config()

    # Skip auth if disabled
    if not config.enabled:
        return None

    # Allow localhost if configured
    if config.allow_localhost and is_localhost(request):
        return None

    # Require API key
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Validate API key
    key_info = validate_api_key(api_key)
    if not key_info:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return key_info


async def require_admin(
    request: Request,
    api_key: str | None = Security(get_api_key),
) -> None:
    """
    FastAPI dependency that requires admin authentication.

    Raises HTTPException 401/403 if not admin.
    """
    config = load_auth_config()

    # Skip auth if disabled
    if not config.enabled:
        return

    # Allow localhost if configured
    if config.allow_localhost and is_localhost(request):
        return

    # Require API key
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Admin API key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Check if admin key
    if not is_admin_key(api_key):
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )


def require_scope(scope: str) -> Callable:
    """
    Create a FastAPI dependency that requires a specific scope.

    Usage:
        @router.post("/sensitive", dependencies=[Depends(require_scope("admin"))])
        async def sensitive_endpoint():
            ...
    """

    async def check_scope(
        request: Request,
        api_key: str | None = Security(get_api_key),
    ) -> "APIKeyInfo | None":
        """Check API key scope and validate request authorization."""
        config = load_auth_config()

        # Skip auth if disabled
        if not config.enabled:
            return None

        # Allow localhost if configured
        if config.allow_localhost and is_localhost(request):
            return None

        # Require API key
        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="API key required",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        # Validate with scope
        key_info = validate_api_key(api_key, required_scope=scope)
        if not key_info:
            raise HTTPException(
                status_code=403,
                detail=f"Scope '{scope}' required",
            )

        return key_info

    return check_scope
