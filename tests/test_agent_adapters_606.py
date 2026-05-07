"""Tests for explicit agent adapter interface (issue #606)."""


def test_known_cli_adapters_implement_send_and_status() -> None:
    from synapse.adapters import AgentAdapter, get_adapter

    for profile in ("claude", "codex", "gemini"):
        adapter = get_adapter(profile, target=f"synapse-{profile}-9999")
        assert isinstance(adapter, AgentAdapter)
        assert callable(adapter.send)
        assert callable(adapter.status)
        assert adapter.profile == profile


def test_unknown_adapter_profile_is_rejected() -> None:
    import pytest

    from synapse.adapters import UnknownAdapterError, get_adapter

    with pytest.raises(UnknownAdapterError):
        get_adapter("unknown", target="agent")
