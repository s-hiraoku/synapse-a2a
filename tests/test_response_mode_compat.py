"""Tests for response_mode backward compatibility."""

from synapse.a2a_compat import _resolve_response_mode


def test_resolve_response_mode_new_key():
    """Should use new response_mode key if present."""
    assert _resolve_response_mode({"response_mode": "wait"}) == "wait"
    assert _resolve_response_mode({"response_mode": "notify"}) == "notify"
    assert _resolve_response_mode({"response_mode": "silent"}) == "silent"


def test_resolve_response_mode_backward_compat():
    """Should map legacy response_expected boolean to new modes."""
    assert _resolve_response_mode({"response_expected": True}) == "wait"
    assert _resolve_response_mode({"response_expected": False}) == "silent"


def test_resolve_response_mode_default():
    """Should default to 'notify' when no keys are present."""
    assert _resolve_response_mode({}) == "notify"
    assert _resolve_response_mode({"other": "data"}) == "notify"


def test_resolve_response_mode_priority():
    """New key should have priority over legacy key."""
    metadata = {"response_mode": "notify", "response_expected": True}
    assert _resolve_response_mode(metadata) == "notify"
