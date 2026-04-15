from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from synapse.commands.multiagent import _PATTERN_TEMPLATES
from synapse.patterns.agent_teams import AgentTeamsConfig, AgentTeamsPattern
from synapse.patterns.base import CoordinationPattern, PatternConfig, TaskResult
from synapse.patterns.generator_verifier import (
    GeneratorVerifierConfig,
    GeneratorVerifierPattern,
)
from synapse.patterns.message_bus import MessageBusConfig, MessageBusPattern
from synapse.patterns.orchestrator_subagent import (
    OrchestratorSubagentConfig,
    OrchestratorSubagentPattern,
)
from synapse.patterns.shared_state import SharedStateConfig, SharedStatePattern


def _cfg(pattern_type: str, name: str = "test") -> dict:
    return {"name": name, **_PATTERN_TEMPLATES[pattern_type]}


def _assert_no_side_effects(pattern: CoordinationPattern) -> None:
    """describe_plan must never spawn agents or send messages."""
    pattern.spawn_agent.assert_not_called()
    pattern.send.assert_not_called()
    assert pattern._agents == []


def _install_tripwires(pattern: CoordinationPattern) -> None:
    pattern.spawn_agent = AsyncMock(
        side_effect=AssertionError("describe_plan called spawn_agent")
    )
    pattern.send = AsyncMock(side_effect=AssertionError("describe_plan called send"))


# ---------- base default ----------


class _NoopPattern(CoordinationPattern):
    name = "noop"

    async def run(self, task: str, config: PatternConfig) -> TaskResult:
        return TaskResult(status="completed")


def test_base_describe_plan_returns_placeholder_list() -> None:
    pattern = _NoopPattern(run_id="noop")
    plan = pattern.describe_plan("do something", PatternConfig())

    assert isinstance(plan, list)
    assert plan
    assert all(isinstance(line, str) for line in plan)


# ---------- generator-verifier ----------


def test_generator_verifier_describe_plan_lists_spawns_and_loop() -> None:
    pattern = GeneratorVerifierPattern(run_id="run-gv")
    _install_tripwires(pattern)
    config = GeneratorVerifierConfig.from_dict(_cfg("generator-verifier"))

    plan = pattern.describe_plan("Review the auth module", config)

    joined = "\n".join(plan)
    assert "Generator" in joined
    assert "Verifier" in joined
    assert "claude" in joined
    assert "pytest" in joined
    assert "3" in joined  # max_iterations
    assert "escalate" in joined
    assert "Review the auth module" in joined
    _assert_no_side_effects(pattern)


# ---------- orchestrator-subagent ----------


def test_orchestrator_subagent_describe_plan_lists_subtasks() -> None:
    pattern = OrchestratorSubagentPattern(run_id="run-os")
    _install_tripwires(pattern)
    config = OrchestratorSubagentConfig.from_dict(_cfg("orchestrator-subagent"))

    plan = pattern.describe_plan("Summarize the repo", config)

    joined = "\n".join(plan)
    assert "Lead" in joined
    assert "subtask-1" in joined
    assert "subtask-2" in joined
    assert "First subtask" in joined
    assert "parallel" in joined.lower()
    assert "Summarize the repo" in joined
    _assert_no_side_effects(pattern)


# ---------- agent-teams ----------


def test_agent_teams_describe_plan_lists_queue_and_team_count() -> None:
    pattern = AgentTeamsPattern(run_id="run-at")
    _install_tripwires(pattern)
    config = AgentTeamsConfig.from_dict(_cfg("agent-teams"))

    plan = pattern.describe_plan("Process items", config)

    joined = "\n".join(plan)
    assert "3" in joined  # team.count
    assert "claude" in joined
    assert "Task 1" in joined
    assert "Task 2" in joined
    assert "Task 3" in joined
    assert "all-done" in joined or "3600" in joined
    _assert_no_side_effects(pattern)


# ---------- message-bus ----------


def test_message_bus_describe_plan_lists_router_and_subscribers() -> None:
    pattern = MessageBusPattern(run_id="run-mb")
    _install_tripwires(pattern)
    config = MessageBusConfig.from_dict(_cfg("message-bus"))

    plan = pattern.describe_plan("Broadcast notice", config)

    joined = "\n".join(plan)
    assert "Router" in joined
    assert "events" in joined  # topic name
    assert "Handler-1" in joined
    assert "Handler-2" in joined
    assert "Broadcast notice" in joined
    _assert_no_side_effects(pattern)


# ---------- shared-state ----------


def test_shared_state_describe_plan_lists_agents_and_budget() -> None:
    pattern = SharedStatePattern(run_id="run-ss")
    _install_tripwires(pattern)
    config = SharedStateConfig.from_dict(_cfg("shared-state"))

    plan = pattern.describe_plan("Research topic", config)

    joined = "\n".join(plan)
    assert "Researcher-1" in joined
    assert "Researcher-2" in joined
    assert "Research aspect A" in joined
    assert "wiki" in joined
    assert "600" in joined  # termination.budget
    _assert_no_side_effects(pattern)


# ---------- CLI integration: dry-run uses describe_plan ----------


def test_dry_run_output_uses_describe_plan(
    tmp_path, monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`synapse map run <name> --task ... --dry-run` must print a plan
    generated by describe_plan, not the raw YAML dump."""
    import argparse

    from synapse.commands.multiagent import (
        _build_template,
        cmd_multiagent_run,
    )
    from synapse.patterns.runner import PatternRunner
    from synapse.patterns.store import PatternStore

    store_dir = tmp_path / ".synapse" / "patterns"
    store = PatternStore(
        project_dir=store_dir, user_dir=tmp_path / ".home" / ".synapse" / "patterns"
    )
    store.save(_build_template("generator-verifier", "plan-gv"))

    # Pin store and runner to real implementations. Other test modules
    # (notably test_cmd_multiagent.py) install fake synapse.patterns.*
    # modules in sys.modules, which can otherwise leak into this test.
    real_runner = PatternRunner()
    monkeypatch.setattr("synapse.commands.multiagent._get_pattern_store", lambda: store)
    monkeypatch.setattr(
        "synapse.commands.multiagent._get_pattern_runner", lambda: real_runner
    )

    args = argparse.Namespace(
        pattern_name="plan-gv",
        task="Ship the feature",
        dry_run=True,
        run_async=False,
        project=False,
        user=False,
    )
    cmd_multiagent_run(args)

    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "plan-gv" in out
    assert "Ship the feature" in out
    # Must contain pattern-specific plan content
    assert "Generator" in out
    assert "Verifier" in out
    assert "pytest" in out
    # Must NOT be a raw YAML dump: these YAML-specific lines shouldn't appear
    assert "max_iterations: 3" not in out
    assert "on_failure: escalate" not in out
    assert "pattern: generator-verifier" not in out
