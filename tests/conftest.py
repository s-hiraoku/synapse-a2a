"""Pytest configuration and shared fixtures."""

import sys
from pathlib import Path

import pytest

# Add synapse to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global state between tests."""
    # Reset any singleton instances
    from synapse import a2a_client

    a2a_client._client = None

    yield

    # Cleanup after test
    a2a_client._client = None
