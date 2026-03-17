import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from synapse.cli import interactive_agent_setup
from synapse.skills import ensure_core_skills


class TestInteractiveSetup(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.patcher_cwd = patch("pathlib.Path.cwd", return_value=self.test_dir)
        self.patcher_cwd.start()

    def tearDown(self):
        self.patcher_cwd.stop()
        shutil.rmtree(self.test_dir)

    @patch("synapse.cli.input")
    @patch("synapse.skills.load_skill_sets")
    @patch("termios.tcgetattr")
    @patch("termios.tcsetattr")
    def test_interactive_agent_setup_no_skill_sets(
        self, mock_set, mock_get, mock_load, mock_input
    ):
        """Test setup flow when no skill sets are defined."""
        mock_load.return_value = {}
        # User provides Name and Role
        mock_input.side_effect = ["MyAgent", "MyRole"]

        with patch("sys.stdin.isatty", return_value=True):
            name, role, skill_set = interactive_agent_setup("synapse-claude-8100", 8100)

        self.assertEqual(name, "MyAgent")
        self.assertEqual(role, "MyRole")
        self.assertIsNone(skill_set)

    @patch("synapse.cli.input")
    @patch("synapse.skills.load_skill_sets")
    @patch("termios.tcgetattr")
    @patch("termios.tcsetattr")
    def test_interactive_agent_setup_skip_provided_fields(
        self, mock_set, mock_get, mock_load, mock_input
    ):
        """Test that provided fields are not prompted."""
        mock_load.return_value = {}

        # Name and Role are provided, only Skill Set check happens
        with patch("sys.stdin.isatty", return_value=True):
            name, role, skill_set = interactive_agent_setup(
                "synapse-claude-8100",
                8100,
                current_name="PreDefinedName",
                current_role="PreDefinedRole",
            )

        self.assertEqual(name, "PreDefinedName")
        self.assertEqual(role, "PreDefinedRole")
        self.assertIsNone(skill_set)
        # input() should NOT have been called for name/role
        mock_input.assert_not_called()

    @patch("shutil.copytree")
    @patch("synapse.skills.Path.exists", autospec=True)
    def test_ensure_core_skills_deploys_when_missing(self, mock_exists, mock_copy):
        """Test ensure_core_skills copies synapse-a2a if missing."""

        # Path.exists(self) -> mock_exists(self)
        def exists_side_effect(path_obj):
            path_str = str(path_obj)
            if "plugins" in path_str:
                return True  # Source exists
            return "skills/synapse-a2a" not in path_str

        mock_exists.side_effect = exists_side_effect

        messages = ensure_core_skills("claude")

        self.assertTrue(
            any("Auto-deployed core skill 'synapse-a2a'" in m for m in messages)
        )
        mock_copy.assert_called()

    @patch("synapse.skills.Path.exists")
    def test_ensure_core_skills_skips_when_exists(self, mock_exists):
        """Test ensure_core_skills skips if synapse-a2a already exists."""
        mock_exists.return_value = True  # Everything exists

        messages = ensure_core_skills("claude")

        self.assertEqual(len(messages), 0)

    @patch("synapse.cli.input")
    @patch("synapse.skills.load_skill_sets")
    @patch("termios.tcgetattr")
    @patch("termios.tcsetattr")
    def test_name_placeholder_accepted_on_enter(
        self, mock_set, mock_get, mock_load, mock_input
    ):
        """Enter on name prompt should adopt the suggested petname."""
        mock_load.return_value = {}
        # Empty string for name (accept placeholder), then "MyRole" for role
        mock_input.side_effect = ["", "MyRole"]

        with patch("sys.stdin.isatty", return_value=True):
            name, role, skill_set = interactive_agent_setup(
                "synapse-claude-8100", 8100, profile="claude"
            )

        # suggest_petname_ids("claude") returns "claude-agent" as first candidate
        self.assertIsNotNone(name)
        self.assertTrue(len(name) > 0)
        self.assertEqual(role, "MyRole")
        self.assertIsNone(skill_set)

    @patch("synapse.cli.input")
    @patch("synapse.skills.load_skill_sets")
    @patch("termios.tcgetattr")
    @patch("termios.tcsetattr")
    def test_name_placeholder_overridden_by_user_input(
        self, mock_set, mock_get, mock_load, mock_input
    ):
        """User input on name prompt should override the placeholder."""
        mock_load.return_value = {}
        mock_input.side_effect = ["custom-name", "MyRole"]

        with patch("sys.stdin.isatty", return_value=True):
            name, role, skill_set = interactive_agent_setup(
                "synapse-claude-8100", 8100, profile="claude"
            )

        self.assertEqual(name, "custom-name")
        self.assertEqual(role, "MyRole")
        self.assertIsNone(skill_set)

    @patch("synapse.cli.input")
    @patch("synapse.skills.load_skill_sets")
    @patch("termios.tcgetattr")
    @patch("termios.tcsetattr")
    def test_name_fallback_when_no_profile(
        self, mock_set, mock_get, mock_load, mock_input
    ):
        """Enter with no profile should adopt a generic fallback name."""
        mock_load.return_value = {}
        # Empty string for name (accept fallback), then "MyRole" for role
        mock_input.side_effect = ["", "MyRole"]

        with patch("sys.stdin.isatty", return_value=True):
            name, role, skill_set = interactive_agent_setup("synapse-claude-8100", 8100)

        # suggest_petname_ids("") returns generic fallbacks like "silent-snake"
        self.assertIsNotNone(name)
        self.assertTrue("-" in name)
        self.assertEqual(role, "MyRole")
        self.assertIsNone(skill_set)


if __name__ == "__main__":
    unittest.main()
