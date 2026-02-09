"""Quality Gates: Hook mechanism for status transition control.

Hooks are shell commands that run at key lifecycle events (e.g., on_idle,
on_task_completed). Exit code semantics:
  - 0: allow (hook passed)
  - 2: deny (hook explicitly blocked the transition)
  - other: allow with warning (hook errored but doesn't block)
"""

from __future__ import annotations

import logging
import os
import subprocess

logger = logging.getLogger(__name__)


class HookManager:
    """Manages hook configuration and execution."""

    def __init__(
        self,
        hooks_config: dict[str, str] | None = None,
        profile_hooks: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> None:
        self._hooks: dict[str, str] = dict(hooks_config or {})
        # Profile hooks override base config
        if profile_hooks:
            self._hooks.update(profile_hooks)
        self._timeout = timeout

    def get_hook(self, name: str) -> str:
        """Return the command string for a named hook, or empty string."""
        return self._hooks.get(name, "")

    def run_hook(self, name: str, **env_kwargs: str) -> bool:
        """Execute a hook and return True (allow) or False (deny).

        Args:
            name: Hook name (e.g. "on_idle", "on_task_completed").
            **env_kwargs: Keyword arguments forwarded to ``_build_env``.

        Returns:
            True if the transition is allowed, False if denied (exit code 2).
        """
        command = self.get_hook(name)
        if not command:
            return True

        hook_env = {**os.environ, **self._build_env(**env_kwargs)}

        try:
            result = subprocess.run(
                command,
                shell=True,
                timeout=self._timeout,
                capture_output=True,
                env=hook_env,
            )
            if result.returncode == 0:
                return True
            if result.returncode == 2:
                logger.info("Hook '%s' denied transition (exit 2)", name)
                return False
            # Other non-zero: allow with warning
            logger.warning(
                "Hook '%s' exited with code %d (allowing by default)",
                name,
                result.returncode,
            )
            return True
        except subprocess.TimeoutExpired:
            logger.warning(
                "Hook '%s' timed out after %ds (allowing by default)",
                name,
                self._timeout,
            )
            return True

    def _build_env(
        self,
        agent_id: str = "",
        agent_name: str = "",
        status_from: str = "",
        status_to: str = "",
        last_task_id: str = "",
    ) -> dict[str, str]:
        """Build environment variables dict for hook subprocess."""
        mapping = {
            "SYNAPSE_AGENT_ID": agent_id,
            "SYNAPSE_AGENT_NAME": agent_name,
            "SYNAPSE_STATUS_FROM": status_from,
            "SYNAPSE_STATUS_TO": status_to,
            "SYNAPSE_LAST_TASK_ID": last_task_id,
        }
        return {key: value for key, value in mapping.items() if value}
