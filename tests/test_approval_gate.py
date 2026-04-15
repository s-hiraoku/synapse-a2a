"""Tests for synapse.approval_gate — unified permission decision layer.

These tests pin down the contract between the gate's policy engine and
its HTTP apply path. They intentionally do not spin up a real agent; the
gate's job is to decide and dispatch, so the tests mock the permission
endpoints directly.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from synapse.approval_gate import (
    ApprovalDecision,
    ApprovalRequest,
    EscalationDeduper,
    apply,
    decide,
    decide_and_apply,
    get_default_deduper,
    request_from_a2a_metadata,
)


def _req(
    *,
    agent_type: str = "codex",
    task_id: str = "task-1",
    endpoint: str = "http://localhost:8126",
    pty_context: str = "1. Yes, proceed",
    metadata: dict[str, Any] | None = None,
) -> ApprovalRequest:
    return ApprovalRequest(
        task_id=task_id,
        endpoint=endpoint,
        target_agent_id="synapse-codex-8126",
        target_agent_type=agent_type,
        pty_context=pty_context,
        sender_id="synapse-claude-8103",
        metadata=metadata or {},
    )


class TestApprovalGateDecide:
    def test_default_approves_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no overrides and gate enabled, the default decision is approve."""

        def _policy() -> dict[str, Any]:
            return {
                "enabled": True,
                "default_action": "approve",
                "profile_overrides": {},
            }

        monkeypatch.setattr("synapse.approval_gate._load_policy", _policy)
        assert decide(_req()) is ApprovalDecision.APPROVE

    def test_disabled_gate_always_escalates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the gate is disabled via settings, every request must escalate
        so the legacy human-in-the-loop path keeps working."""

        def _policy() -> dict[str, Any]:
            return {
                "enabled": False,
                "default_action": "approve",
                "profile_overrides": {},
            }

        monkeypatch.setattr("synapse.approval_gate._load_policy", _policy)
        assert decide(_req()) is ApprovalDecision.ESCALATE

    def test_profile_override_beats_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _policy() -> dict[str, Any]:
            return {
                "enabled": True,
                "default_action": "approve",
                "profile_overrides": {"codex": "escalate"},
            }

        monkeypatch.setattr("synapse.approval_gate._load_policy", _policy)
        assert decide(_req(agent_type="codex")) is ApprovalDecision.ESCALATE
        # A different profile still hits the default
        assert decide(_req(agent_type="claude")) is ApprovalDecision.APPROVE

    def test_invalid_default_action_falls_back_to_escalate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When a caller bypasses ``_load_policy`` and hands the gate a
        malformed ``default_action`` value, ``decide`` must fall back to
        ``ESCALATE`` — silently auto-approving on a config typo is worse
        than routing the request through a human. (The normal
        ``_load_policy`` path already filters bad values, so this only
        matters for direct monkeypatches and tests.)"""

        def _policy() -> dict[str, Any]:
            return {
                "enabled": True,
                "default_action": "flibble",
                "profile_overrides": {},
            }

        monkeypatch.setattr("synapse.approval_gate._load_policy", _policy)
        assert decide(_req()) is ApprovalDecision.ESCALATE


class TestApprovalGateBlockedStates:
    """Regression coverage for the Step D diagnostic (2026-04-15).

    When a child is stuck on a non-permission terminal state — e.g. an
    OpenAI usage-limit banner — sending the profile's runtime_response
    (``y\\r`` for codex) does nothing because the modal does not accept
    it. The child then re-emits the escalation every few seconds and
    floods the parent inbox. ``decide`` must recognise these screens up
    front and return ``ESCALATE`` so ``apply`` never touches the
    approve endpoint.
    """

    @pytest.fixture(autouse=True)
    def _approve_policy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _policy() -> dict[str, Any]:
            return {
                "enabled": True,
                "default_action": "approve",
                "profile_overrides": {},
            }

        monkeypatch.setattr("synapse.approval_gate._load_policy", _policy)

    def test_openai_usage_limit_banner_escalates(self) -> None:
        ctx = (
            "\u25a0 You've hit your usage limit. Upgrade to Pro "
            "(https://chatgpt.com/explore/pro), visit "
            "https://chatgpt.com/codex/settings/usage to purchase "
            "more credits or try again at Apr 17th, 2026 6:28 AM."
        )
        assert decide(_req(pty_context=ctx)) is ApprovalDecision.ESCALATE

    def test_upgrade_to_pro_fragment_alone_escalates(self) -> None:
        assert (
            decide(_req(pty_context="Upgrade to Pro for more credits"))
            is ApprovalDecision.ESCALATE
        )

    def test_try_again_fragment_alone_escalates(self) -> None:
        assert (
            decide(_req(pty_context="try again at Apr 17th, 2026 6:28 AM"))
            is ApprovalDecision.ESCALATE
        )

    def test_normal_permission_prompt_still_approves(self) -> None:
        assert (
            decide(_req(pty_context="› 1. Yes, proceed (y)"))
            is ApprovalDecision.APPROVE
        )

    def test_blocked_state_overrides_profile_approve(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even when the profile policy says approve, a blocked state
        must escalate — the blocked-state guard is a safety floor that
        the policy cannot override downward."""

        def _policy() -> dict[str, Any]:
            return {
                "enabled": True,
                "default_action": "approve",
                "profile_overrides": {"codex": "approve"},
            }

        monkeypatch.setattr("synapse.approval_gate._load_policy", _policy)
        ctx = "■ You've hit your usage limit."
        assert decide(_req(pty_context=ctx)) is ApprovalDecision.ESCALATE


class TestEscalationDeduper:
    """The Step D capture showed four distinct task_ids carrying the
    same blocked-state pty_context within 4 seconds. Task-id-level
    dedupe is not enough; dedupe must key on
    ``(target_agent_id, pty_context hash)`` so the same child stuck on
    the same screen cannot walk around the guard by minting new tasks.
    """

    def test_first_occurrence_is_not_duplicate(self) -> None:
        dedup = EscalationDeduper(ttl_seconds=60.0)
        assert dedup.seen(_req(task_id="t1", pty_context="banner")) is False

    def test_same_target_same_context_within_ttl_is_duplicate(self) -> None:
        dedup = EscalationDeduper(ttl_seconds=60.0)
        dedup.seen(_req(task_id="t1", pty_context="banner"))
        # Different task_id, same target + context: must be flagged.
        assert dedup.seen(_req(task_id="t2", pty_context="banner")) is True

    def test_different_context_is_not_duplicate(self) -> None:
        dedup = EscalationDeduper(ttl_seconds=60.0)
        dedup.seen(_req(task_id="t1", pty_context="banner one"))
        assert dedup.seen(_req(task_id="t2", pty_context="banner two")) is False

    def test_ttl_expiry_releases_the_guard(self) -> None:
        now = [1000.0]

        def clock() -> float:
            return now[0]

        dedup = EscalationDeduper(ttl_seconds=10.0, clock=clock)
        assert dedup.seen(_req(task_id="t1", pty_context="banner")) is False
        now[0] += 5.0
        assert dedup.seen(_req(task_id="t2", pty_context="banner")) is True
        now[0] += 20.0  # well past 10s TTL
        assert dedup.seen(_req(task_id="t3", pty_context="banner")) is False

    def test_different_targets_are_independent(self) -> None:
        dedup = EscalationDeduper(ttl_seconds=60.0)
        a = ApprovalRequest(
            task_id="t1",
            endpoint="http://localhost:8126",
            target_agent_id="synapse-codex-8126",
            target_agent_type="codex",
            pty_context="banner",
        )
        b = ApprovalRequest(
            task_id="t2",
            endpoint="http://localhost:8127",
            target_agent_id="synapse-codex-8127",
            target_agent_type="codex",
            pty_context="banner",
        )
        assert dedup.seen(a) is False
        assert dedup.seen(b) is False

    def test_empty_pty_context_is_never_duplicate(self) -> None:
        """If we have no pty_context we cannot prove the child is stuck
        in the same state, so do not suppress the escalation."""
        dedup = EscalationDeduper(ttl_seconds=60.0)
        assert dedup.seen(_req(task_id="t1", pty_context="")) is False
        assert dedup.seen(_req(task_id="t2", pty_context="")) is False

    def test_default_deduper_is_singleton(self) -> None:
        assert get_default_deduper() is get_default_deduper()


class TestApprovalGateApply:
    def test_approve_posts_to_approve_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def _fake_post(url: str, timeout: float = 10.0) -> Any:
            captured["url"] = url
            captured["timeout"] = timeout
            resp = MagicMock()
            resp.status_code = 200
            resp.text = ""
            return resp

        monkeypatch.setattr("synapse.approval_gate.requests.post", _fake_post)

        ok = apply(_req(task_id="abc"), ApprovalDecision.APPROVE)

        assert ok is True
        assert captured["url"] == "http://localhost:8126/tasks/abc/permission/approve"

    def test_deny_posts_to_deny_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def _fake_post(url: str, timeout: float = 10.0) -> Any:
            captured["url"] = url
            resp = MagicMock()
            resp.status_code = 200
            resp.text = ""
            return resp

        monkeypatch.setattr("synapse.approval_gate.requests.post", _fake_post)

        ok = apply(_req(task_id="abc"), ApprovalDecision.DENY)

        assert ok is True
        assert captured["url"] == "http://localhost:8126/tasks/abc/permission/deny"

    def test_escalate_is_no_op_and_returns_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called = {"post": 0}

        def _fake_post(*a: Any, **k: Any) -> Any:  # pragma: no cover - must not run
            called["post"] += 1
            raise AssertionError("escalate must not call requests.post")

        monkeypatch.setattr("synapse.approval_gate.requests.post", _fake_post)

        ok = apply(_req(), ApprovalDecision.ESCALATE)

        assert ok is True
        assert called["post"] == 0

    def test_http_error_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        resp = MagicMock()
        resp.status_code = 404
        resp.text = "task not found"
        monkeypatch.setattr("synapse.approval_gate.requests.post", lambda *a, **k: resp)
        ok = apply(_req(), ApprovalDecision.APPROVE)
        assert ok is False

    def test_missing_endpoint_returns_false(self) -> None:
        req = ApprovalRequest(
            task_id="abc",
            endpoint="",
            target_agent_id="id",
            target_agent_type="codex",
        )
        assert apply(req, ApprovalDecision.APPROVE) is False


class TestDecideAndApply:
    def test_returns_decision_and_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "synapse.approval_gate._load_policy",
            lambda: {
                "enabled": True,
                "default_action": "approve",
                "profile_overrides": {},
            },
        )
        resp = MagicMock()
        resp.status_code = 200
        resp.text = ""
        monkeypatch.setattr("synapse.approval_gate.requests.post", lambda *a, **k: resp)

        decision, ok = decide_and_apply(_req())

        assert decision is ApprovalDecision.APPROVE
        assert ok is True


class TestRequestBuilder:
    def test_builds_request_from_permission_metadata(self) -> None:
        metadata = {
            "permission": {
                "pty_context": "1. Yes, proceed",
                "agent_type": "codex",
                "detected_at": 12345.0,
            }
        }
        req = request_from_a2a_metadata(
            task_id="abc",
            endpoint="http://localhost:8126",
            target_agent_id="id",
            target_agent_type="codex",
            metadata=metadata,
            sender_id="parent",
        )
        assert req.task_id == "abc"
        assert req.pty_context == "1. Yes, proceed"
        assert req.sender_id == "parent"
        assert req.metadata == metadata

    def test_builds_request_without_permission_block(self) -> None:
        req = request_from_a2a_metadata(
            task_id="abc",
            endpoint="http://localhost:8126",
            target_agent_id="id",
            target_agent_type="codex",
            metadata={},
        )
        assert req.pty_context == ""
        assert req.metadata == {}
