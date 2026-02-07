"""Tests for synapse.paths module."""

import os
from pathlib import Path
from unittest.mock import patch

from synapse.paths import (
    get_external_registry_dir,
    get_history_db_path,
    get_registry_dir,
)

# ============================================================
# Item 4: History DB Path Tests
# ============================================================


class TestGetHistoryDbPath:
    """Test get_history_db_path() function."""

    def test_get_history_db_path_default(self):
        """Default should be ~/.synapse/history/history.db."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the env var if present
            os.environ.pop("SYNAPSE_HISTORY_DB_PATH", None)
            result = get_history_db_path()
            expected = str(Path.home() / ".synapse" / "history" / "history.db")
            assert result == expected


# ============================================================
# Item 3: Registry/History Path Environment Variable Tests
# ============================================================


class TestGetRegistryDir:
    """Test get_registry_dir() function."""

    def test_get_registry_dir_default(self):
        """Default should be ~/.a2a/registry."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SYNAPSE_REGISTRY_DIR", None)
            result = get_registry_dir()
            expected = str(Path.home() / ".a2a" / "registry")
            assert result == expected

    def test_get_registry_dir_env_override(self):
        """SYNAPSE_REGISTRY_DIR should override default."""
        with patch.dict(os.environ, {"SYNAPSE_REGISTRY_DIR": "/tmp/test-registry"}):
            result = get_registry_dir()
            assert result == "/tmp/test-registry"


class TestGetExternalRegistryDir:
    """Test get_external_registry_dir() function."""

    def test_get_external_registry_dir_default(self):
        """Default should be ~/.a2a/external."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SYNAPSE_EXTERNAL_REGISTRY_DIR", None)
            result = get_external_registry_dir()
            expected = str(Path.home() / ".a2a" / "external")
            assert result == expected

    def test_get_external_registry_dir_env_override(self):
        """SYNAPSE_EXTERNAL_REGISTRY_DIR should override default."""
        with patch.dict(
            os.environ, {"SYNAPSE_EXTERNAL_REGISTRY_DIR": "/tmp/test-external"}
        ):
            result = get_external_registry_dir()
            assert result == "/tmp/test-external"


class TestGetHistoryDbPathEnvOverride:
    """Test get_history_db_path() with environment variable override."""

    def test_get_history_db_path_env_override(self):
        """SYNAPSE_HISTORY_DB_PATH should override default."""
        with patch.dict(
            os.environ, {"SYNAPSE_HISTORY_DB_PATH": "/tmp/test-history.db"}
        ):
            result = get_history_db_path()
            assert result == "/tmp/test-history.db"
