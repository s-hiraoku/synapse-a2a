"""Tests for B2: Quality Gates (Hook mechanism).

Test-first development: tests for hook management and execution.
"""

from __future__ import annotations

# ============================================================
# TestHookManager - Hook configuration
# ============================================================


class TestHookManager:
    """Tests for HookManager configuration loading."""

    def test_empty_settings(self):
        """Should handle empty hook settings."""
        from synapse.hooks import HookManager

        manager = HookManager(hooks_config={})
        assert manager.get_hook("on_idle") == ""
        assert manager.get_hook("on_task_completed") == ""

    def test_load_from_settings(self):
        """Should load hooks from settings dict."""
        from synapse.hooks import HookManager

        config = {
            "on_idle": "pytest tests/ --tb=short",
            "on_task_completed": "pytest tests/ && ruff check",
        }
        manager = HookManager(hooks_config=config)
        assert manager.get_hook("on_idle") == "pytest tests/ --tb=short"
        assert manager.get_hook("on_task_completed") == "pytest tests/ && ruff check"

    def test_profile_override(self):
        """Profile-specific hooks should override default settings."""
        from synapse.hooks import HookManager

        config = {"on_idle": "default-command"}
        profile_hooks = {"on_idle": "profile-command"}

        manager = HookManager(hooks_config=config, profile_hooks=profile_hooks)
        assert manager.get_hook("on_idle") == "profile-command"


# ============================================================
# TestHookExecution - Hook execution and exit codes
# ============================================================


class TestHookExecution:
    """Tests for hook execution with different exit codes."""

    def test_exit_0_allows(self):
        """Exit code 0 should return True (allowed)."""
        from synapse.hooks import HookManager

        manager = HookManager(hooks_config={"on_idle": "true"})
        result = manager.run_hook("on_idle")
        assert result is True

    def test_exit_2_denies(self):
        """Exit code 2 should return False (denied)."""
        from synapse.hooks import HookManager

        manager = HookManager(hooks_config={"on_idle": "exit 2"})
        result = manager.run_hook("on_idle")
        assert result is False

    def test_other_exit_allows_with_warning(self):
        """Other exit codes should return True (allowed with warning)."""
        from synapse.hooks import HookManager

        manager = HookManager(hooks_config={"on_idle": "exit 1"})
        result = manager.run_hook("on_idle")
        assert result is True  # Non-2 errors allow by default

    def test_timeout(self):
        """Hook should timeout after configured duration."""
        from synapse.hooks import HookManager

        manager = HookManager(
            hooks_config={"on_idle": "sleep 10"},
            timeout=1,
        )
        result = manager.run_hook("on_idle")
        assert result is True  # Timeout allows by default

    def test_empty_hook_allows(self):
        """Empty hook command should return True (no hook = allow)."""
        from synapse.hooks import HookManager

        manager = HookManager(hooks_config={})
        result = manager.run_hook("on_idle")
        assert result is True


# ============================================================
# TestHookEnvironment - Environment variable injection
# ============================================================


class TestHookEnvironment:
    """Tests for environment variables passed to hooks."""

    def test_agent_id_env_var(self):
        """SYNAPSE_AGENT_ID should be set."""
        from synapse.hooks import HookManager

        # Use a command that prints env var
        manager = HookManager(
            hooks_config={"on_idle": "echo $SYNAPSE_AGENT_ID"},
        )
        env_vars = manager._build_env(
            agent_id="synapse-claude-8100",
            agent_name="my-claude",
        )
        assert env_vars["SYNAPSE_AGENT_ID"] == "synapse-claude-8100"

    def test_agent_name_env_var(self):
        """SYNAPSE_AGENT_NAME should be set when available."""
        from synapse.hooks import HookManager

        manager = HookManager(hooks_config={})
        env_vars = manager._build_env(
            agent_id="synapse-claude-8100",
            agent_name="my-claude",
        )
        assert env_vars["SYNAPSE_AGENT_NAME"] == "my-claude"

    def test_status_env_vars(self):
        """SYNAPSE_STATUS_FROM and SYNAPSE_STATUS_TO should be set."""
        from synapse.hooks import HookManager

        manager = HookManager(hooks_config={})
        env_vars = manager._build_env(
            agent_id="synapse-claude-8100",
            status_from="PROCESSING",
            status_to="READY",
        )
        assert env_vars["SYNAPSE_STATUS_FROM"] == "PROCESSING"
        assert env_vars["SYNAPSE_STATUS_TO"] == "READY"


# ============================================================
# TestHookIntegration - Integration with controller
# ============================================================


class TestHookIntegration:
    """Tests for hook integration with status transitions."""

    def test_on_idle_deny_keeps_processing(self):
        """on_idle returning False should prevent READY transition."""
        from synapse.hooks import HookManager

        manager = HookManager(hooks_config={"on_idle": "exit 2"})
        # When on_idle denies, the status should stay PROCESSING
        result = manager.run_hook("on_idle")
        assert result is False

    def test_on_task_completed_deny(self):
        """on_task_completed returning False should prevent completion."""
        from synapse.hooks import HookManager

        manager = HookManager(hooks_config={"on_task_completed": "exit 2"})
        result = manager.run_hook("on_task_completed")
        assert result is False
