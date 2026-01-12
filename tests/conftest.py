"""Pytest configuration and shared fixtures."""

import asyncio
import sys
from collections.abc import Generator
from pathlib import Path

import pytest

# Add synapse to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def reset_global_state() -> Generator[None, None, None]:
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
        # Get the current running event loop if it exists
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No event loop running in current thread
        loop = None

    # Explicitly handle three cases: None, running, or closed
    if loop is None:
        pass
    elif loop.is_running():
        # Loop is still running - don't close it
        # This can happen if test cleanup is called while async work is ongoing
        # Using debug=True to help troubleshoot test issues
        import sys

        print(
            f"[DEBUG] Event loop still running at cleanup for {sys.argv[0]}",
            file=sys.stderr,
        )
    elif not loop.is_closed():
        # Loop exists, is not running, and is not closed - properly close it
        loop.close()

    # Force creation of a fresh event loop for next test
    # This prevents accumulation of old event loops
    try:
        asyncio.set_event_loop(None)
    except RuntimeError as e:
        # RuntimeError: event loop is running in current thread
        print(
            f"[DEBUG] RuntimeError when setting event loop to None: {e}",
            file=sys.stderr,
        )
    except ValueError as e:
        # ValueError: event loop policy does not support set_event_loop
        print(
            f"[DEBUG] ValueError when setting event loop to None: {e}", file=sys.stderr
        )
