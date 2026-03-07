"""Tests for layout="auto" — automatic split direction alternation.

When spawning agents one at a time (synapse spawn), the split direction
should alternate based on existing pane count so that panes tile evenly
instead of all splitting in the same direction.

Covers: tmux, iTerm2, Ghostty, zellij.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ============================================================
# TestTmuxAutoLayout - tmux auto layout
# ============================================================


class TestTmuxAutoLayout:
    """tmux auto layout should split the largest pane along its longer axis."""

    def test_auto_layout_wide_pane_splits_horizontal(self) -> None:
        """A wide pane (width >= height*2) should split horizontally (-h)."""
        from synapse.terminal_jump import _TmuxAutoSplit, create_tmux_panes

        with patch(
            "synapse.terminal_jump._get_tmux_auto_split",
            return_value=_TmuxAutoSplit(target_pane="%0", flag="-h"),
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

        with patch(
            "synapse.terminal_jump._get_tmux_auto_split",
            return_value=_TmuxAutoSplit(target_pane="%1", flag="-v"),
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

        with patch(
            "synapse.terminal_jump._get_tmux_auto_split",
            return_value=_TmuxAutoSplit(target_pane="%5", flag="-h"),
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


class TestGetPaneCount:
    """Tests for terminal pane count detection helpers."""

    def test_get_tmux_pane_count_parses_output(self) -> None:
        """Should parse tmux list-panes output to get count."""
        from synapse.terminal_jump import _get_tmux_pane_count

        with patch("synapse.terminal_jump.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="%0\n%1\n%2\n")
            count = _get_tmux_pane_count()
        assert count == 3

    def test_get_tmux_pane_count_returns_none_on_error(self) -> None:
        """Should return None if tmux command fails."""
        from synapse.terminal_jump import _get_tmux_pane_count

        with patch(
            "synapse.terminal_jump.subprocess.run", side_effect=Exception("not in tmux")
        ):
            count = _get_tmux_pane_count()
        assert count is None

    def test_get_zellij_pane_count_parses_output(self) -> None:
        """Should parse zellij pane count."""
        from synapse.terminal_jump import _get_zellij_pane_count

        with patch("synapse.terminal_jump.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="tab1\ntab2\n")
            count = _get_zellij_pane_count()
        assert count == 2

    def test_get_zellij_pane_count_returns_none_on_error(self) -> None:
        """Should return None if zellij command fails."""
        from synapse.terminal_jump import _get_zellij_pane_count

        with patch(
            "synapse.terminal_jump.subprocess.run",
            side_effect=Exception("not in zellij"),
        ):
            count = _get_zellij_pane_count()
        assert count is None


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
