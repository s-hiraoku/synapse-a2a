"""Pytest configuration and shared fixtures."""

import asyncio
import contextlib
import sys
from pathlib import Path

import pytest

# Add synapse to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global state between tests and clean up event loops."""
    # Reset any singleton instances
    from synapse import a2a_client

    a2a_client._client = None

    yield

    # Cleanup after test
    a2a_client._client = None

    # Clean up event loop created by asyncio.run() in tests
    # This is critical for preventing event loop accumulation
    try:
        # asyncio.run() sets the event loop but doesn't always clean it up
        # Get the current event loop without creating a new one
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop is not None and not loop.is_closed() and loop.is_running():
            # This shouldn't happen in normal test cleanup
            pass
    except RuntimeError:
        # No event loop in current thread
        pass

    # Force creation of a fresh event loop for next test
    # This prevents accumulation of old event loops
    with contextlib.suppress(Exception):
        asyncio.set_event_loop(None)
