"""Tests for layout="auto" — automatic split direction alternation.

When spawning agents one at a time (synapse spawn), the split direction
should alternate based on existing pane count so that panes tile evenly
instead of all splitting in the same direction.

Covers: tmux, iTerm2, Ghostty, zellij.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

# ============================================================
# TestTmuxAutoLayout - tmux auto layout
# ============================================================


class TestTmuxAutoLayout:
    """tmux auto layout should split the largest pane along its longer axis."""

    def test_auto_layout_wide_pane_splits_horizontal(self) -> None:
        """A wide pane (width >= height*2) should split horizontally (-h)."""
        from synapse.terminal_jump import _TmuxAutoSplit, create_tmux_panes

        env = os.environ.copy()
        env["SYNAPSE_SPAWN_PANES"] = "%0"

        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "synapse.terminal_jump._get_tmux_auto_split",
                return_value=_TmuxAutoSplit(target_pane="%0", flag="-h"),
            ),
        ):
            commands = create_tmux_panes(
                agents=["claude"],
                layout="auto",
                all_new=True,
            )
        split_cmds = [c for c in commands if "split-window" in c]
        assert len(split_cmds) == 1
        assert "split-window -h " in split_cmds[0]
        assert "-t %0 " in split_cmds[0]

    def test_auto_layout_tall_pane_splits_vertical(self) -> None:
        """A tall pane (height*2 > width) should split vertically (-v)."""
        from synapse.terminal_jump import _TmuxAutoSplit, create_tmux_panes

        env = os.environ.copy()
        env["SYNAPSE_SPAWN_PANES"] = "%1"

        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "synapse.terminal_jump._get_tmux_auto_split",
                return_value=_TmuxAutoSplit(target_pane="%1", flag="-v"),
            ),
        ):
            commands = create_tmux_panes(
                agents=["gemini"],
                layout="auto",
                all_new=True,
            )
        split_cmds = [c for c in commands if "split-window" in c]
        assert len(split_cmds) == 1
        assert "split-window -v " in split_cmds[0]
        assert "-t %1 " in split_cmds[0]

    def test_auto_layout_targets_largest_pane(self) -> None:
        """Should target the largest pane, not the current pane."""
        from synapse.terminal_jump import _TmuxAutoSplit, create_tmux_panes

        env = os.environ.copy()
        env["SYNAPSE_SPAWN_PANES"] = "%5"

        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "synapse.terminal_jump._get_tmux_auto_split",
                return_value=_TmuxAutoSplit(target_pane="%5", flag="-h"),
            ),
        ):
            commands = create_tmux_panes(
                agents=["codex"],
                layout="auto",
                all_new=True,
            )
        split_cmds = [c for c in commands if "split-window" in c]
        assert "-t %5 " in split_cmds[0]

    def test_auto_layout_does_not_affect_explicit_horizontal(self) -> None:
        """layout='horizontal' should still always use -h."""
        from synapse.terminal_jump import create_tmux_panes

        commands = create_tmux_panes(
            agents=["claude"],
            layout="horizontal",
            all_new=True,
        )
        split_cmds = [c for c in commands if "split-window" in c]
        assert len(split_cmds) == 1
        assert "split-window -h " in split_cmds[0]

    def test_auto_layout_does_not_affect_explicit_vertical(self) -> None:
        """layout='vertical' should still always use -v."""
        from synapse.terminal_jump import create_tmux_panes

        commands = create_tmux_panes(
            agents=["claude"],
            layout="vertical",
            all_new=True,
        )
        split_cmds = [c for c in commands if "split-window" in c]
        assert len(split_cmds) == 1
        assert "split-window -v " in split_cmds[0]

    def test_auto_layout_fallback_when_detection_fails(self) -> None:
        """If auto-split detection fails, should fall back to horizontal."""
        from synapse.terminal_jump import create_tmux_panes

        with patch("synapse.terminal_jump._get_tmux_auto_split", return_value=None):
            commands = create_tmux_panes(
                agents=["claude"],
                layout="auto",
                all_new=True,
            )
        split_cmds = [c for c in commands if "split-window" in c]
        assert len(split_cmds) == 1
        assert "split-window -h " in split_cmds[0]


# ============================================================
# TestITerm2AutoLayout - iTerm2 auto layout
# ============================================================


class TestITerm2AutoLayout:
    """iTerm2 should alternate split direction based on existing pane count."""

    def test_auto_layout_first_spawn_splits_vertically(self) -> None:
        """First spawn (1 existing pane) should split vertically (side-by-side)."""
        from synapse.terminal_jump import create_iterm2_panes

        with patch("synapse.terminal_jump._get_iterm2_session_count", return_value=1):
            script = create_iterm2_panes(
                agents=["claude"],
                all_new=True,
                layout="auto",
            )
        assert "split vertically" in script

    def test_auto_layout_second_spawn_splits_horizontally(self) -> None:
        """Second spawn (2 existing panes) should split horizontally (stacked)."""
        from synapse.terminal_jump import create_iterm2_panes

        with patch("synapse.terminal_jump._get_iterm2_session_count", return_value=2):
            script = create_iterm2_panes(
                agents=["gemini"],
                all_new=True,
                layout="auto",
            )
        assert "split horizontally" in script

    def test_auto_layout_fallback_when_count_fails(self) -> None:
        """If session count detection fails, should fall back to vertical."""
        from synapse.terminal_jump import create_iterm2_panes

        with patch(
            "synapse.terminal_jump._get_iterm2_session_count", return_value=None
        ):
            script = create_iterm2_panes(
                agents=["claude"],
                all_new=True,
                layout="auto",
            )
        assert "split vertically" in script


# ============================================================
# TestGhosttyAutoLayout - Ghostty auto layout
# ============================================================


class TestGhosttyAutoLayout:
    """Ghostty should alternate Cmd+D / Cmd+Shift+D based on existing pane count."""

    def test_auto_layout_first_spawn_splits_right(self) -> None:
        """First spawn should use Cmd+D (split right)."""
        from synapse.terminal_jump import create_ghostty_window

        with patch(
            "synapse.terminal_jump._get_ghostty_split_direction",
            return_value="right",
        ):
            commands = create_ghostty_window(
                agents=["claude"],
                layout="auto",
            )
        assert len(commands) == 1
        # Cmd+D = keystroke "d" using {command down}
        assert 'keystroke "d" using {command down}' in commands[0]

    def test_auto_layout_second_spawn_splits_down(self) -> None:
        """Second spawn should use Cmd+Shift+D (split down)."""
        from synapse.terminal_jump import create_ghostty_window

        with patch(
            "synapse.terminal_jump._get_ghostty_split_direction",
            return_value="down",
        ):
            commands = create_ghostty_window(
                agents=["claude"],
                layout="auto",
            )
        assert len(commands) == 1
        # Cmd+Shift+D = keystroke "d" using {command down, shift down}
        assert "shift down" in commands[0]


# ============================================================
# TestZellijAutoLayout - zellij auto layout
# ============================================================


class TestZellijAutoLayout:
    """zellij should alternate right/down based on existing pane count."""

    def test_auto_layout_first_spawn_goes_right(self) -> None:
        """First spawn (1 existing pane) should split right."""
        from synapse.terminal_jump import create_zellij_panes

        with patch("synapse.terminal_jump._get_zellij_pane_count", return_value=1):
            commands = create_zellij_panes(
                agents=["claude"],
                layout="auto",
                all_new=True,
            )
        assert len(commands) == 1
        assert "--direction right" in commands[0]

    def test_auto_layout_second_spawn_goes_down(self) -> None:
        """Second spawn (2 existing panes) should split down."""
        from synapse.terminal_jump import create_zellij_panes

        with patch("synapse.terminal_jump._get_zellij_pane_count", return_value=2):
            commands = create_zellij_panes(
                agents=["gemini"],
                layout="auto",
                all_new=True,
            )
        assert len(commands) == 1
        assert "--direction down" in commands[0]

    def test_auto_layout_fallback_when_count_fails(self) -> None:
        """If pane count detection fails, should fall back to right."""
        from synapse.terminal_jump import create_zellij_panes

        with patch("synapse.terminal_jump._get_zellij_pane_count", return_value=None):
            commands = create_zellij_panes(
                agents=["claude"],
                layout="auto",
                all_new=True,
            )
        assert len(commands) == 1
        assert "--direction right" in commands[0]


# ============================================================
# TestSpawnDefaultLayout - spawn.py uses auto layout
# ============================================================


class TestSpawnDefaultLayout:
    """spawn_agent() should default to layout='auto'."""

    def test_spawn_passes_auto_layout(self) -> None:
        """spawn_agent should pass layout='auto' to create_panes."""

        with (
            patch("synapse.spawn.load_profile"),
            patch("synapse.spawn.is_port_available", return_value=True),
            patch("synapse.spawn.detect_terminal_app", return_value="tmux"),
            patch(
                "synapse.spawn.create_panes", return_value=["echo test"]
            ) as mock_panes,
            patch("subprocess.run"),
        ):
            from synapse.spawn import spawn_agent

            spawn_agent(profile="claude", port=9999)

        mock_panes.assert_called_once()
        call_kwargs = mock_panes.call_args
        assert (
            call_kwargs.kwargs.get("layout") == "auto"
            or call_kwargs[1].get("layout") == "auto"
            or call_kwargs[0][1] == "auto"
        ), f"create_panes should be called with layout='auto', got: {call_kwargs}"


# ============================================================
# TestGetPaneCount - pane count helper functions
# ============================================================


# ============================================================
# TestTmuxSpawnZone - spawn zone pane filtering
# ============================================================


class TestTmuxSpawnZone:
    """tmux auto layout should filter panes by SYNAPSE_SPAWN_PANES."""

    def test_first_spawn_creates_spawn_zone(self) -> None:
        """First spawn (no SYNAPSE_SPAWN_PANES) should split current pane."""
        from synapse.terminal_jump import create_tmux_panes

        env = os.environ.copy()
        env.pop("SYNAPSE_SPAWN_PANES", None)
        env["TMUX_PANE"] = "%0"

        with (
            patch.dict(os.environ, env, clear=True),
            patch("synapse.terminal_jump._get_tmux_auto_split", return_value=None),
        ):
            commands = create_tmux_panes(
                agents=["claude"],
                layout="auto",
                all_new=True,
            )
        split_cmds = [c for c in commands if "split-window" in c]
        assert len(split_cmds) == 1
        assert "split-window -h " in split_cmds[0]

    def test_second_spawn_targets_spawn_zone(self) -> None:
        """Second spawn should split within spawn zone, not current pane."""
        from synapse.terminal_jump import _TmuxAutoSplit, create_tmux_panes

        env = os.environ.copy()
        env["SYNAPSE_SPAWN_PANES"] = "%5"
        env["TMUX_PANE"] = "%0"

        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "synapse.terminal_jump._get_tmux_auto_split",
                return_value=_TmuxAutoSplit(target_pane="%5", flag="-v"),
            ),
        ):
            commands = create_tmux_panes(
                agents=["gemini"],
                layout="auto",
                all_new=True,
            )
        split_cmds = [c for c in commands if "split-window" in c]
        assert len(split_cmds) == 1
        assert "-t %5 " in split_cmds[0]
        assert "split-window -v " in split_cmds[0]

    def test_auto_split_excludes_current_pane(self) -> None:
        """_get_tmux_auto_split should only consider spawn zone panes."""
        from synapse.terminal_jump import _get_tmux_auto_split

        env = os.environ.copy()
        env["TMUX_PANE"] = "%0"
        env["SYNAPSE_SPAWN_PANES"] = "%1,%2"

        with (
            patch.dict(os.environ, env, clear=True),
            patch("synapse.terminal_jump.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="%0 200 78\n%1 70 40\n%2 70 38\n",
            )
            result = _get_tmux_auto_split()

        # Should NOT pick %0 (current pane), even though it's largest
        assert result is not None
        assert result.target_pane in ("%1", "%2")

    def test_auto_split_picks_largest_in_spawn_zone(self) -> None:
        """Should pick the largest pane within spawn zone."""
        from synapse.terminal_jump import _get_tmux_auto_split

        env = os.environ.copy()
        env["TMUX_PANE"] = "%0"
        env["SYNAPSE_SPAWN_PANES"] = "%1,%2,%3"

        with (
            patch.dict(os.environ, env, clear=True),
            patch("synapse.terminal_jump.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="%0 200 78\n%1 70 40\n%2 140 78\n%3 70 38\n",
            )
            result = _get_tmux_auto_split()

        assert result is not None
        assert result.target_pane == "%2"


# ============================================================
# TestSpawnPaneTracking - spawn.py tracks spawn zone panes
# ============================================================


class TestSpawnPaneTracking:
    """spawn_agent() should track spawn zone pane IDs via SYNAPSE_SPAWN_PANES."""

    def test_spawn_records_new_pane_id(self) -> None:
        """After spawning, the new pane ID should be stored via tmux session env."""
        from synapse.spawn import spawn_agent

        # _get_tmux_pane_ids is called twice: before and after pane creation.
        # Before: {%0, %1}, After: {%0, %1, %5} — new pane is %5.
        with (
            patch("synapse.spawn.load_profile", return_value={}),
            patch("synapse.spawn.is_port_available", return_value=True),
            patch("synapse.spawn.detect_terminal_app", return_value="tmux"),
            patch("synapse.spawn.create_panes", return_value=["echo test"]),
            patch("subprocess.run"),
            patch(
                "synapse.spawn._get_tmux_pane_ids",
                side_effect=[{"%0", "%1"}, {"%0", "%1", "%5"}],
            ),
            patch("synapse.spawn._get_tmux_spawn_panes", return_value=""),
            patch("synapse.spawn._set_tmux_spawn_panes") as mock_set,
        ):
            spawn_agent(profile="claude", port=9999)
            mock_set.assert_called_once_with("%5")

    def test_spawn_appends_pane_id_to_existing(self) -> None:
        """Subsequent spawns should append to existing spawn zone panes."""
        from synapse.spawn import spawn_agent

        # Before: {%0, %1, %5}, After: {%0, %1, %5, %8} — new pane is %8.
        with (
            patch("synapse.spawn.load_profile", return_value={}),
            patch("synapse.spawn.is_port_available", return_value=True),
            patch("synapse.spawn.detect_terminal_app", return_value="tmux"),
            patch("synapse.spawn.create_panes", return_value=["echo test"]),
            patch("subprocess.run"),
            patch(
                "synapse.spawn._get_tmux_pane_ids",
                side_effect=[{"%0", "%1", "%5"}, {"%0", "%1", "%5", "%8"}],
            ),
            patch("synapse.spawn._get_tmux_spawn_panes", return_value="%5"),
            patch("synapse.spawn._set_tmux_spawn_panes") as mock_set,
        ):
            spawn_agent(profile="claude", port=9998)
            mock_set.assert_called_once_with("%5,%8")


# ============================================================
# TestGetPaneCount - pane count helper functions
# ============================================================


class TestGetPaneCount:
    """Tests for terminal pane count detection helpers."""

    def test_get_zellij_pane_count_uses_env_counter(self) -> None:
        """Should return current env count and increment it."""
        from synapse.terminal_jump import _get_zellij_pane_count

        with patch.dict(
            os.environ,
            {"SYNAPSE_ZELLIJ_PANE_COUNT": "4"},
            clear=False,
        ):
            count = _get_zellij_pane_count()
            assert count == 4
            assert os.environ["SYNAPSE_ZELLIJ_PANE_COUNT"] == "5"

    def test_get_zellij_pane_count_defaults_to_one(self) -> None:
        """Should default to one pane and seed the counter."""
        from synapse.terminal_jump import _get_zellij_pane_count

        with patch.dict(os.environ, {}, clear=True):
            count = _get_zellij_pane_count()
            assert count == 1
            assert os.environ["SYNAPSE_ZELLIJ_PANE_COUNT"] == "2"


class TestGetTmuxAutoSplit:
    """Tests for _get_tmux_auto_split — largest pane detection."""

    def test_wide_pane_returns_horizontal(self) -> None:
        """A wide pane (280x78) should return -h."""
        from synapse.terminal_jump import _get_tmux_auto_split

        with patch("synapse.terminal_jump.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="%0 280 78\n")
            result = _get_tmux_auto_split()
        assert result is not None
        assert result.target_pane == "%0"
        assert result.flag == "-h"

    def test_tall_pane_returns_vertical(self) -> None:
        """A tall pane (70x78) should return -v (width < height*2)."""
        from synapse.terminal_jump import _get_tmux_auto_split

        with patch("synapse.terminal_jump.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="%0 70 78\n")
            result = _get_tmux_auto_split()
        assert result is not None
        assert result.target_pane == "%0"
        assert result.flag == "-v"

    def test_picks_largest_pane(self) -> None:
        """Should pick the pane with the largest area."""
        from synapse.terminal_jump import _get_tmux_auto_split

        with patch("synapse.terminal_jump.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="%0 70 78\n%1 140 78\n%2 70 78\n",
            )
            result = _get_tmux_auto_split()
        assert result is not None
        assert result.target_pane == "%1"
        assert result.flag == "-v"  # 140 < 78*2=156, so vertical

    def test_returns_none_on_error(self) -> None:
        """Should return None if tmux command fails."""
        from synapse.terminal_jump import _get_tmux_auto_split

        with patch(
            "synapse.terminal_jump.subprocess.run", side_effect=Exception("fail")
        ):
            result = _get_tmux_auto_split()
        assert result is None


# ============================================================
# TestMultiAgentSplitAlternation - multi-agent "split" layout
# ============================================================


class TestGhosttyMultiAgentSplit:
    """Ghostty should alternate Cmd+D / Cmd+Shift+D for layout='split'."""

    def test_split_alternates_direction(self) -> None:
        """3 agents with layout='split' should alternate right/down/right."""
        from synapse.terminal_jump import create_ghostty_window

        commands = create_ghostty_window(
            agents=["claude", "gemini", "codex"],
            layout="split",
        )
        assert len(commands) == 3
        # index 0 → right (Cmd+D), index 1 → down (Cmd+Shift+D), index 2 → right
        assert 'keystroke "d" using {command down}' in commands[0]
        assert "shift down" not in commands[0]
        assert "shift down" in commands[1]
        assert 'keystroke "d" using {command down}' in commands[2]
        assert "shift down" not in commands[2]

    def test_horizontal_layout_no_alternation(self) -> None:
        """layout='horizontal' should always split right."""
        from synapse.terminal_jump import create_ghostty_window

        commands = create_ghostty_window(
            agents=["claude", "gemini"],
            layout="horizontal",
        )
        assert len(commands) == 2
        for cmd in commands:
            assert "shift down" not in cmd

    def test_vertical_layout_no_alternation(self) -> None:
        """layout='vertical' should always split down."""
        from synapse.terminal_jump import create_ghostty_window

        commands = create_ghostty_window(
            agents=["claude", "gemini"],
            layout="vertical",
        )
        assert len(commands) == 2
        for cmd in commands:
            assert "shift down" in cmd


class TestITerm2MultiAgentSplit:
    """iTerm2 should alternate split direction for layout='split'."""

    def test_split_alternates_all_new(self) -> None:
        """3 agents with all_new=True should alternate vertically/horizontally."""
        from synapse.terminal_jump import create_iterm2_panes

        script = create_iterm2_panes(
            agents=["claude", "gemini", "codex"],
            all_new=True,
            layout="split",
        )
        lines = script.splitlines()
        split_lines = [line for line in lines if "split " in line]
        assert len(split_lines) == 3
        # index 0 → vertically, index 1 → horizontally, index 2 → vertically
        assert "vertically" in split_lines[0]
        assert "horizontally" in split_lines[1]
        assert "vertically" in split_lines[2]

    def test_split_alternates_not_all_new(self) -> None:
        """With all_new=False, new panes should continue alternation from index 1."""
        from synapse.terminal_jump import create_iterm2_panes

        script = create_iterm2_panes(
            agents=["claude", "gemini", "codex"],
            all_new=False,
            layout="split",
        )
        lines = script.splitlines()
        split_lines = [line for line in lines if "split " in line]
        # First agent uses current session (no split), 2 new panes
        # index 1 → horizontally, index 2 → vertically
        assert len(split_lines) == 2
        assert "horizontally" in split_lines[0]
        assert "vertically" in split_lines[1]

    def test_horizontal_layout_no_alternation(self) -> None:
        """layout='horizontal' should always split horizontally."""
        from synapse.terminal_jump import create_iterm2_panes

        script = create_iterm2_panes(
            agents=["claude", "gemini", "codex"],
            all_new=True,
            layout="horizontal",
        )
        lines = script.splitlines()
        split_lines = [line for line in lines if "split " in line]
        assert len(split_lines) == 3
        for sl in split_lines:
            assert "horizontally" in sl


class TestZellijMultiAgentSplit:
    """Zellij should alternate right/down starting with right for layout='split'."""

    def test_split_alternates_direction(self) -> None:
        """Panes in 'split' layout should alternate direction.

        Index 0 skips --direction (first pane, no split needed).
        Subsequent panes alternate starting with right: 1→right, 2→down, 3→right.
        """
        from synapse.terminal_jump import create_zellij_panes

        commands = create_zellij_panes(
            agents=["claude", "gemini", "codex", "opencode"],
            layout="split",
        )
        assert len(commands) == 4
        assert "--direction" not in commands[0]
        # (i-1)%2: i=1→0→right, i=2→1→down, i=3→0→right
        assert "--direction right" in commands[1]
        assert "--direction down" in commands[2]
        assert "--direction right" in commands[3]

    def test_auto_layout_alternates(self) -> None:
        """Auto layout should alternate based on existing pane count."""
        from synapse.terminal_jump import create_zellij_panes

        with patch("synapse.terminal_jump._get_zellij_pane_count", return_value=1):
            commands = create_zellij_panes(
                agents=["claude", "gemini"],
                layout="auto",
                all_new=True,
            )
        assert len(commands) == 2
        # effective=1+0=1 → right, effective=1+1=2 → down
        assert "--direction right" in commands[0]
        assert "--direction down" in commands[1]
