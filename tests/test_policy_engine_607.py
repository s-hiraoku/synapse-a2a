"""Tests for formal PolicyEngine wrapper (issue #607)."""

from synapse.approval_gate import ApprovalDecision, ApprovalRequest


def test_policy_engine_decides_with_provider_override(monkeypatch) -> None:
    from synapse.approval_gate import PolicyEngine

    def fake_policy() -> dict:
        return {
            "enabled": True,
            "default_action": "deny",
            "profile_overrides": {"codex": {"permission_request": "approve"}},
        }

    monkeypatch.setattr("synapse.approval_gate._load_policy", fake_policy)
    request = ApprovalRequest(
        task_id="task",
        endpoint="http://localhost:8120",
        target_agent_id="synapse-codex-8120",
        target_agent_type="codex",
        pty_context="Allow this command? [y/N]",
    )

    assert PolicyEngine().decide(request) == ApprovalDecision.APPROVE
