"""Tests for synapse/session_id_detector.py — detect + list CLI sessions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from synapse.session_id_detector import (
    detect_session_id,
    list_sessions,
)

# ── helpers ──────────────────────────────────────────────────────


def _touch(path: Path, content: str = "", mtime: float | None = None) -> Path:
    """Create a file with optional mtime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if mtime is not None:
        import os

        os.utime(path, (mtime, mtime))
    return path


def _claude_project_hash(working_dir: str) -> str:
    """Mimic Claude's project hash: replace / with -."""
    return working_dir.replace("/", "-")


def _gemini_project_hash(working_dir: str) -> str:
    """Mimic Gemini's SHA256 hash of working dir."""
    return hashlib.sha256(working_dir.encode()).hexdigest()


# ── detect_session_id: Claude ────────────────────────────────────


class TestDetectClaude:
    def test_detect_claude_session_id(self, tmp_path: Path) -> None:
        """Multiple .jsonl files — should pick the most recent by mtime."""
        working_dir = "/Volumes/SSD/myproject"
        project_hash = _claude_project_hash(working_dir)
        project_dir = tmp_path / ".claude" / "projects" / project_hash
        project_dir.mkdir(parents=True)

        _touch(project_dir / "aaa-old-uuid.jsonl", "old", mtime=1000.0)
        _touch(project_dir / "bbb-new-uuid.jsonl", "new", mtime=2000.0)

        result = detect_session_id(
            "claude", working_dir, claude_home=tmp_path / ".claude"
        )
        assert result == "bbb-new-uuid"

    def test_detect_claude_no_project_dir(self, tmp_path: Path) -> None:
        """Project directory doesn't exist → None."""
        result = detect_session_id(
            "claude", "/nonexistent/project", claude_home=tmp_path / ".claude"
        )
        assert result is None

    def test_detect_claude_empty_project_dir(self, tmp_path: Path) -> None:
        """Project directory exists but no .jsonl files → None."""
        working_dir = "/Volumes/SSD/empty"
        project_hash = _claude_project_hash(working_dir)
        project_dir = tmp_path / ".claude" / "projects" / project_hash
        project_dir.mkdir(parents=True)

        result = detect_session_id(
            "claude", working_dir, claude_home=tmp_path / ".claude"
        )
        assert result is None


# ── detect_session_id: Gemini ────────────────────────────────────


class TestDetectGemini:
    def test_detect_gemini_session_id_by_hash(self, tmp_path: Path) -> None:
        """SHA256 hash directory → detect from chats/."""
        working_dir = "/Volumes/SSD/myproject"
        proj_hash = _gemini_project_hash(working_dir)
        chats_dir = tmp_path / ".gemini" / "tmp" / proj_hash / "chats"
        chats_dir.mkdir(parents=True)

        _touch(chats_dir / "session-2026-03-04-abc.json", "{}", mtime=3000.0)

        result = detect_session_id(
            "gemini", working_dir, gemini_home=tmp_path / ".gemini"
        )
        assert result == "session-2026-03-04-abc"

    def test_detect_gemini_session_id_by_named_project(self, tmp_path: Path) -> None:
        """projects.json named mapping → detect from that dir's chats/."""
        working_dir = "/Volumes/SSD/myproject"
        gemini_home = tmp_path / ".gemini"
        gemini_home.mkdir(parents=True)

        # projects.json maps working_dir to a named ref
        projects_json = gemini_home / "projects.json"
        projects_json.write_text(json.dumps({working_dir: "my-named-ref"}))

        chats_dir = gemini_home / "tmp" / "my-named-ref" / "chats"
        chats_dir.mkdir(parents=True)
        _touch(chats_dir / "session-named-123.json", "{}", mtime=4000.0)

        result = detect_session_id("gemini", working_dir, gemini_home=gemini_home)
        assert result == "session-named-123"

    def test_detect_gemini_no_chats_dir(self, tmp_path: Path) -> None:
        """chats directory doesn't exist → None."""
        result = detect_session_id(
            "gemini", "/some/project", gemini_home=tmp_path / ".gemini"
        )
        assert result is None


# ── detect_session_id: Codex ─────────────────────────────────────


class TestDetectCodex:
    def test_detect_codex_session_id(self, tmp_path: Path) -> None:
        """Date subdirectories → detect most recent .jsonl."""
        sessions_dir = tmp_path / ".codex" / "sessions" / "2026" / "03" / "04"
        sessions_dir.mkdir(parents=True)
        _touch(
            sessions_dir / "rollout-2026-03-04T06-31-abc.jsonl", "data", mtime=5000.0
        )

        older_dir = tmp_path / ".codex" / "sessions" / "2026" / "03" / "03"
        older_dir.mkdir(parents=True)
        _touch(older_dir / "rollout-2026-03-03T10-00-xyz.jsonl", "old", mtime=1000.0)

        result = detect_session_id("codex", "/any", codex_home=tmp_path / ".codex")
        assert result == "rollout-2026-03-04T06-31-abc"

    def test_detect_codex_no_sessions(self, tmp_path: Path) -> None:
        """No sessions directory → None."""
        result = detect_session_id("codex", "/any", codex_home=tmp_path / ".codex")
        assert result is None


# ── detect_session_id: Copilot ───────────────────────────────────


class TestDetectCopilot:
    def test_detect_copilot_session_id(self, tmp_path: Path) -> None:
        """session-state/*.jsonl → detect most recent."""
        state_dir = tmp_path / ".copilot" / "session-state"
        state_dir.mkdir(parents=True)
        _touch(state_dir / "eb391e88-uuid.jsonl", "data", mtime=6000.0)
        _touch(state_dir / "older-uuid.jsonl", "old", mtime=1000.0)

        result = detect_session_id(
            "copilot", "/any", copilot_home=tmp_path / ".copilot"
        )
        assert result == "eb391e88-uuid"

    def test_detect_copilot_no_sessions(self, tmp_path: Path) -> None:
        """session-state doesn't exist → None."""
        result = detect_session_id(
            "copilot", "/any", copilot_home=tmp_path / ".copilot"
        )
        assert result is None


# ── detect_session_id: edge cases ────────────────────────────────


class TestDetectEdgeCases:
    def test_detect_opencode_returns_none(self, tmp_path: Path) -> None:
        """OpenCode has no session support → always None."""
        result = detect_session_id("opencode", "/any")
        assert result is None

    def test_detect_unknown_profile_returns_none(self, tmp_path: Path) -> None:
        """Unknown profile → None."""
        result = detect_session_id("unknown-agent", "/any")
        assert result is None

    def test_detect_handles_permission_error(self, tmp_path: Path, monkeypatch) -> None:
        """PermissionError during detection → None (not raised)."""
        from synapse import session_id_detector

        def _boom(*args, **kwargs):
            raise PermissionError("access denied")

        monkeypatch.setattr(session_id_detector, "_detect_claude", _boom)
        result = detect_session_id("claude", "/any", claude_home=tmp_path / ".claude")
        assert result is None


# ── list_sessions ────────────────────────────────────────────────


class TestListSessions:
    def test_list_claude_sessions(self, tmp_path: Path) -> None:
        """Should return multiple sessions sorted by mtime descending."""
        working_dir = "/Volumes/SSD/myproject"
        project_hash = _claude_project_hash(working_dir)
        project_dir = tmp_path / ".claude" / "projects" / project_hash
        project_dir.mkdir(parents=True)

        _touch(project_dir / "session-a.jsonl", "a" * 100, mtime=1000.0)
        _touch(project_dir / "session-b.jsonl", "b" * 200, mtime=3000.0)
        _touch(project_dir / "session-c.jsonl", "c" * 50, mtime=2000.0)

        results = list_sessions("claude", working_dir, claude_home=tmp_path / ".claude")

        assert len(results) == 3
        # Sorted by mtime descending
        assert results[0].session_id == "session-b"
        assert results[1].session_id == "session-c"
        assert results[2].session_id == "session-a"
        # Check fields
        assert results[0].profile == "claude"
        assert results[0].size_bytes == 200
        assert results[0].modified_at == 3000.0

    def test_list_sessions_limit(self, tmp_path: Path) -> None:
        """limit parameter should cap the number of results."""
        working_dir = "/Volumes/SSD/limited"
        project_hash = _claude_project_hash(working_dir)
        project_dir = tmp_path / ".claude" / "projects" / project_hash
        project_dir.mkdir(parents=True)

        for i in range(5):
            _touch(
                project_dir / f"session-{i}.jsonl",
                f"data-{i}",
                mtime=float(1000 + i),
            )

        results = list_sessions(
            "claude", working_dir, limit=2, claude_home=tmp_path / ".claude"
        )
        assert len(results) == 2

    def test_list_sessions_empty(self, tmp_path: Path) -> None:
        """No sessions → empty list."""
        results = list_sessions(
            "claude", "/nonexistent", claude_home=tmp_path / ".claude"
        )
        assert results == []

    def test_list_all_profiles(self, tmp_path: Path) -> None:
        """profile=None should aggregate from all profiles."""
        working_dir = "/Volumes/SSD/multi"

        # Claude session
        claude_hash = _claude_project_hash(working_dir)
        claude_dir = tmp_path / ".claude" / "projects" / claude_hash
        claude_dir.mkdir(parents=True)
        _touch(claude_dir / "claude-sess.jsonl", "c", mtime=2000.0)

        # Codex session
        codex_dir = tmp_path / ".codex" / "sessions" / "2026" / "03" / "04"
        codex_dir.mkdir(parents=True)
        _touch(codex_dir / "rollout-codex.jsonl", "x", mtime=3000.0)

        results = list_sessions(
            None,
            working_dir,
            claude_home=tmp_path / ".claude",
            codex_home=tmp_path / ".codex",
            gemini_home=tmp_path / ".gemini",
            copilot_home=tmp_path / ".copilot",
        )

        profiles = {r.profile for r in results}
        assert "claude" in profiles
        assert "codex" in profiles
