"""Tests for shell_hook.py - Shell integration hook generation."""

from unittest.mock import patch

from synapse.shell_hook import BASH_HOOK, ZSH_HOOK_SIMPLE, generate_hook, main

# ============================================================
# BASH_HOOK Constant Tests
# ============================================================


class TestBashHookConstant:
    """Test BASH_HOOK constant content."""

    def test_bash_hook_contains_function(self):
        """Should contain synapse_preexec function."""
        assert "synapse_preexec()" in BASH_HOOK

    def test_bash_hook_checks_at_pattern(self):
        """Should check for @ prefix pattern."""
        assert "@*" in BASH_HOOK or "== @*" in BASH_HOOK

    def test_bash_hook_extracts_agent_name(self):
        """Should extract agent name from command."""
        assert "agent=" in BASH_HOOK
        assert "sed" in BASH_HOOK

    def test_bash_hook_extracts_message(self):
        """Should extract message from command."""
        assert "message=" in BASH_HOOK

    def test_bash_hook_checks_response_flag(self):
        """Should check for --response flag."""
        assert "--response" in BASH_HOOK

    def test_bash_hook_uses_synapse_send(self):
        """Should use synapse send command for sending."""
        assert "synapse send" in BASH_HOOK

    def test_bash_hook_has_zsh_section(self):
        """Should have ZSH-specific section."""
        assert "ZSH_VERSION" in BASH_HOOK
        assert "autoload" in BASH_HOOK or "zsh" in BASH_HOOK.lower()

    def test_bash_hook_has_bash_section(self):
        """Should have Bash-specific section."""
        assert "BASH_VERSION" in BASH_HOOK

    def test_bash_hook_has_debug_trap(self):
        """Should have DEBUG trap for bash."""
        assert "DEBUG" in BASH_HOOK
        assert "trap" in BASH_HOOK

    def test_bash_hook_prints_info(self):
        """Should print info message about usage."""
        assert "@Agent" in BASH_HOOK
        assert "echo" in BASH_HOOK

    def test_bash_hook_prevents_original_execution(self):
        """Should return 1 to prevent original command execution."""
        assert "return 1" in BASH_HOOK


# ============================================================
# ZSH_HOOK_SIMPLE Constant Tests
# ============================================================


class TestZshHookSimpleConstant:
    """Test ZSH_HOOK_SIMPLE constant content."""

    def test_zsh_hook_contains_function(self):
        """Should contain synapse-send function."""
        assert "synapse-send()" in ZSH_HOOK_SIMPLE

    def test_zsh_hook_checks_at_pattern(self):
        """Should check for @ prefix pattern."""
        assert "@*" in ZSH_HOOK_SIMPLE or "== @*" in ZSH_HOOK_SIMPLE

    def test_zsh_hook_extracts_agent_name(self):
        """Should extract agent name from command."""
        assert "agent=" in ZSH_HOOK_SIMPLE
        assert "sed" in ZSH_HOOK_SIMPLE

    def test_zsh_hook_uses_synapse_send(self):
        """Should use synapse send command for sending."""
        assert "synapse send" in ZSH_HOOK_SIMPLE

    def test_zsh_hook_has_alias(self):
        """Should create @ alias."""
        assert "alias @=" in ZSH_HOOK_SIMPLE

    def test_zsh_hook_shows_usage(self):
        """Should show usage on incorrect input."""
        assert "Usage" in ZSH_HOOK_SIMPLE


# ============================================================
# generate_hook Function Tests
# ============================================================


class TestGenerateHook:
    """Test generate_hook() function."""

    def test_generate_hook_bash(self):
        """Should return BASH_HOOK for bash type."""
        result = generate_hook("bash")
        assert result == BASH_HOOK

    def test_generate_hook_zsh(self):
        """Should return BASH_HOOK for zsh type (uses same hook)."""
        result = generate_hook("zsh")
        assert result == BASH_HOOK

    def test_generate_hook_simple(self):
        """Should return ZSH_HOOK_SIMPLE for simple type."""
        result = generate_hook("simple")
        assert result == ZSH_HOOK_SIMPLE

    def test_generate_hook_default(self):
        """Should return BASH_HOOK for unknown type."""
        result = generate_hook("unknown")
        assert result == BASH_HOOK

    def test_generate_hook_no_arg(self):
        """Should return BASH_HOOK with no argument."""
        result = generate_hook()
        assert result == BASH_HOOK


# ============================================================
# main Function Tests
# ============================================================


class TestMainFunction:
    """Test main() function."""

    @patch("builtins.print")
    @patch("sys.argv", ["shell_hook.py"])
    def test_main_default_bash(self, mock_print):
        """main() with no args should print BASH_HOOK."""
        main()
        mock_print.assert_called_once_with(BASH_HOOK)

    @patch("builtins.print")
    @patch("sys.argv", ["shell_hook.py", "--type", "bash"])
    def test_main_bash_flag(self, mock_print):
        """main() with --type bash should print BASH_HOOK."""
        main()
        mock_print.assert_called_once_with(BASH_HOOK)

    @patch("builtins.print")
    @patch("sys.argv", ["shell_hook.py", "--type", "zsh"])
    def test_main_zsh_flag(self, mock_print):
        """main() with --type zsh should print BASH_HOOK."""
        main()
        mock_print.assert_called_once_with(BASH_HOOK)

    @patch("builtins.print")
    @patch("sys.argv", ["shell_hook.py", "--type", "simple"])
    def test_main_simple_flag(self, mock_print):
        """main() with --type simple should print ZSH_HOOK_SIMPLE."""
        main()
        mock_print.assert_called_once_with(ZSH_HOOK_SIMPLE)


# ============================================================
# Hook Script Syntax Tests
# ============================================================


class TestHookScriptSyntax:
    """Test that hook scripts have valid shell syntax patterns."""

    def test_bash_hook_has_balanced_braces(self):
        """BASH_HOOK should have balanced braces."""
        open_braces = BASH_HOOK.count("{")
        close_braces = BASH_HOOK.count("}")
        assert open_braces == close_braces

    def test_bash_hook_has_balanced_quotes(self):
        """BASH_HOOK should have balanced double quotes."""
        # Count quotes not escaped
        # Note: This is a simplified check
        quote_count = BASH_HOOK.count('"')
        # Double quotes should be even (opening + closing)
        assert quote_count % 2 == 0

    def test_zsh_hook_simple_has_balanced_braces(self):
        """ZSH_HOOK_SIMPLE should have balanced braces."""
        open_braces = ZSH_HOOK_SIMPLE.count("{")
        close_braces = ZSH_HOOK_SIMPLE.count("}")
        assert open_braces == close_braces

    def test_bash_hook_has_shebang_comment(self):
        """BASH_HOOK should start with comment (for sourcing)."""
        # Should be sourceable - starts with comment
        first_non_empty = BASH_HOOK.strip().split("\n")[0]
        assert first_non_empty.startswith("#")

    def test_zsh_hook_simple_has_shebang_comment(self):
        """ZSH_HOOK_SIMPLE should start with comment."""
        first_non_empty = ZSH_HOOK_SIMPLE.strip().split("\n")[0]
        assert first_non_empty.startswith("#")


# ============================================================
# Hook Functionality Tests
# ============================================================


class TestHookFunctionality:
    """Test hook scripts contain required functionality."""

    def test_bash_hook_has_pythonpath(self):
        """BASH_HOOK should set PYTHONPATH for imports."""
        assert "PYTHONPATH" in BASH_HOOK

    def test_bash_hook_uses_python3(self):
        """BASH_HOOK should use python3."""
        assert "python3" in BASH_HOOK

    def test_bash_hook_imports_synapse_shell(self):
        """BASH_HOOK should import SynapseShell for --response."""
        assert "SynapseShell" in BASH_HOOK

    def test_bash_hook_sets_priority(self):
        """BASH_HOOK should set message priority."""
        assert "--priority" in BASH_HOOK

    def test_zsh_hook_simple_uses_synapse_send(self):
        """ZSH_HOOK_SIMPLE should use synapse send command."""
        assert "synapse send" in ZSH_HOOK_SIMPLE

    def test_zsh_hook_simple_sets_priority(self):
        """ZSH_HOOK_SIMPLE should set message priority."""
        assert "--priority" in ZSH_HOOK_SIMPLE


# ============================================================
# Integration Pattern Tests
# ============================================================


class TestIntegrationPatterns:
    """Test hook integration patterns."""

    def test_bash_hook_suggested_for_bashrc(self):
        """BASH_HOOK should mention .bashrc."""
        assert ".bashrc" in BASH_HOOK or "bashrc" in BASH_HOOK.lower()

    def test_bash_hook_suggested_for_zshrc(self):
        """BASH_HOOK should mention .zshrc."""
        assert ".zshrc" in BASH_HOOK or "zshrc" in BASH_HOOK.lower()

    def test_zsh_hook_simple_suggested_for_zshrc(self):
        """ZSH_HOOK_SIMPLE should mention .zshrc."""
        assert ".zshrc" in ZSH_HOOK_SIMPLE or "zshrc" in ZSH_HOOK_SIMPLE.lower()

    def test_bash_hook_mentions_synapse_shell(self):
        """BASH_HOOK should mention synapse-shell as alternative."""
        assert "synapse-shell" in BASH_HOOK or "synapse shell" in BASH_HOOK.lower()
