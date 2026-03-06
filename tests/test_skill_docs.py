"""Content checks for Synapse skill docs and helper scripts."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PLUGIN_SKILLS = REPO_ROOT / "plugins" / "synapse-a2a" / "skills"


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text()


def test_messaging_doc_softens_vscode_capability_claim() -> None:
    text = _read("plugins/synapse-a2a/skills/synapse-a2a/references/messaging.md")
    assert "VS Code integrated terminal -- opens to the working directory" not in text
    assert "brings the application/window to the front;" in text
    assert "does not switch the integrated terminal or change WORKING_DIR" in text


def test_spawning_doc_uses_current_gemini_flag_and_safe_examples() -> None:
    text = _read("plugins/synapse-a2a/skills/synapse-a2a/references/spawning.md")
    assert "| **Gemini CLI** | `--approval-mode=yolo` |" in text
    assert "synapse spawn gemini -- --approval-mode=yolo" in text
    assert "synapse spawn gemini -- -y" not in text
    assert (
        "synapse team start claude gemini -- --dangerously-skip-permissions" not in text
    )


def test_commands_quick_ref_includes_reopen_with_supported_syntax() -> None:
    text = _read(
        "plugins/synapse-a2a/skills/synapse-manager/references/commands-quick-ref.md"
    )
    assert "`synapse tasks reopen <id>`" in text
    assert "Reopen a completed or failed task" in text
    reopen_line = next(line for line in text.splitlines() if "tasks reopen" in line)
    assert "--reason" not in reopen_line


def test_check_team_status_reports_failures_and_empty_states_distinctly() -> None:
    text = _read(
        "plugins/synapse-a2a/skills/synapse-manager/scripts/check_team_status.sh"
    )
    assert "command -v synapse" in text
    assert "list_output=$(synapse list 2>&1)" in text
    assert "list_status=$?" in text
    assert "synapse list failed:" in text
    assert "No agents running." in text
    assert "task_output=$(synapse tasks list 2>&1)" in text
    assert "task_status=$?" in text
    assert "synapse tasks list failed:" in text
    assert "2>/dev/null" not in text


def test_regression_triage_removes_unused_tracked_changes_variable() -> None:
    text = _read(
        "plugins/synapse-a2a/skills/synapse-manager/scripts/regression_triage.sh"
    )
    assert "has_tracked_changes" not in text


def test_wait_ready_uses_targeted_status_check() -> None:
    text = _read("plugins/synapse-a2a/skills/synapse-manager/scripts/wait_ready.sh")
    assert 'synapse status "$agent" --json' in text
    assert '"status": "READY"' in text or "READY" in text
    assert 'grep -F "$agent"' not in text


def test_synapse_manager_skill_emphasizes_tests_before_implementation() -> None:
    text = _read("plugins/synapse-a2a/skills/synapse-manager/SKILL.md")
    step2_index = text.index("### Step 2:")
    tests_index = text.index("New tests first")
    assert tests_index < step2_index
    assert "create tests -> present/confirm spec -> then implement" in text
    assert (
        "--blocked-by tests" in text
        or "--blocked-by 2" in text
        or "--blocked-by 1" in text
    )
    assert "scripts/wait_ready.sh" in text
    assert "working directory" in text.lower()
    assert "--force" in text


def test_synapse_a2a_skill_shows_cleanup_verification() -> None:
    text = _read("plugins/synapse-a2a/skills/synapse-a2a/SKILL.md")
    assert "synapse list                              # Verify agent appears" in text
    assert "synapse kill Tester -f" in text
    assert "synapse list                              # Verify cleanup" in text
    assert "retry" in text.lower()


def test_worker_guide_waits_for_helper_completion_before_kill() -> None:
    text = _read(
        "plugins/synapse-a2a/skills/synapse-manager/references/worker-guide.md"
    )
    assert "synapse send Helper" in text
    assert "--wait" in text or "--notify" in text
    assert "--priority 4" in text or "--priority 5" in text
    assert "synapse kill Helper -f" in text
    assert "--silent" not in text.split("synapse kill Helper -f")[0][-200:]


def test_reinst_skill_documents_source_and_synced_invocations() -> None:
    text = _read("plugins/synapse-a2a/skills/synapse-reinst/SKILL.md")
    assert "python plugins/synapse-a2a/skills/synapse-reinst/scripts/reinst.py" in text
    assert (
        "cd .claude/skills/synapse-reinst" in text
        or "cd .agents/skills/synapse-reinst" in text
    )


def test_architecture_doc_describes_dev_only_skill_storage_accurately() -> None:
    text = _read("site-docs/concepts/architecture.md")
    assert "Dev-only skills" in text
    assert "live exclusively in `.agents/skills/`" not in text
    assert ".claude/skills" in text


def test_sync_targets_exist_for_plugin_skills() -> None:
    for root in (REPO_ROOT / ".agents" / "skills", REPO_ROOT / ".claude" / "skills"):
        for skill_name in ("synapse-a2a", "synapse-manager", "synapse-reinst"):
            assert (root / skill_name / "SKILL.md").exists()
