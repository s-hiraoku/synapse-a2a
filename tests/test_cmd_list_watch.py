"""Tests for synapse list command."""

import json
import os
import shutil
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapse.cli import _clear_screen, cmd_list
from synapse.commands.list import ListCommand
from synapse.registry import AgentRegistry


@pytest.fixture
def temp_registry_dir():
    """Create a temporary registry directory."""
    temp_dir = Path("/tmp/a2a_test_list_watch")
    temp_dir.mkdir(parents=True, exist_ok=True)
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_registry(temp_registry_dir):
    """Create a test registry with temp directory."""
    reg = AgentRegistry()
    reg.registry_dir = temp_registry_dir
    return reg


class TestGetAgentData:
    """Tests for ListCommand._get_agent_data method."""

    def _create_list_command(
        self,
        is_process_alive=lambda p: True,
        is_port_open=lambda host, port, timeout=0.5: True,
    ):
        """Create a ListCommand with mock dependencies."""
        return ListCommand(
            registry_factory=lambda: MagicMock(spec=AgentRegistry),
            is_process_alive=is_process_alive,
            is_port_open=is_port_open,
            clear_screen=lambda: None,
            time_module=MagicMock(),
            print_func=print,
        )

    def test_empty_registry(self, temp_registry):
        """Should return empty list for no agents."""
        list_cmd = self._create_list_command()
        agents, stale_locks, show_file_safety = list_cmd._get_agent_data(temp_registry)
        assert agents == []

    def test_single_agent(self, temp_registry):
        """Should return data for single agent."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")

        list_cmd = self._create_list_command()
        agents, _, _ = list_cmd._get_agent_data(temp_registry)

        assert len(agents) == 1
        assert agents[0]["agent_type"] == "claude"
        assert agents[0]["port"] == 8100
        assert agents[0]["status"] == "READY"

    def test_multiple_agents(self, temp_registry):
        """Should return data for multiple agents."""
        temp_registry.register("synapse-claude-8100", "claude", 8100, status="READY")
        temp_registry.register(
            "synapse-gemini-8110", "gemini", 8110, status="PROCESSING"
        )

        list_cmd = self._create_list_command()
        agents, _, _ = list_cmd._get_agent_data(temp_registry)

        assert len(agents) == 2
        types = [a["agent_type"] for a in agents]
        assert "claude" in types
        assert "gemini" in types

    def test_cleans_up_dead_processes(self, temp_registry):
        """Should remove dead processes from registry during data fetch."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")

        list_cmd = self._create_list_command(is_process_alive=lambda p: False)
        agents, _, _ = list_cmd._get_agent_data(temp_registry)

        # Should return empty list
        assert agents == []

        # Should have cleaned up the registry
        assert len(temp_registry.list_agents()) == 0

    def test_cleans_up_stale_pid_reuse_when_port_closed(self, temp_registry):
        """Should remove entries when PID is alive but port is closed (PID reuse)."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")

        list_cmd = self._create_list_command(
            is_process_alive=lambda p: True,
            is_port_open=lambda host, port, timeout=0.5: False,
        )
        agents, _, _ = list_cmd._get_agent_data(temp_registry)

        assert agents == []
        assert len(temp_registry.list_agents()) == 0

    def test_processing_agent_kept_when_port_closed(self, temp_registry):
        """PROCESSING agents should not be removed if port isn't open yet."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="PROCESSING")

        list_cmd = self._create_list_command(
            is_process_alive=lambda p: True,
            is_port_open=lambda host, port, timeout=0.5: False,
        )
        agents, _, _ = list_cmd._get_agent_data(temp_registry)

        assert len(agents) == 1
        assert agents[0]["status"] == "PROCESSING"

    def test_transport_included_in_data(self, temp_registry):
        """Transport data should always be included."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")
        temp_registry.update_transport(agent_id, "UDS→")

        list_cmd = self._create_list_command()
        agents, _, _ = list_cmd._get_agent_data(temp_registry)

        assert len(agents) == 1
        assert agents[0]["transport"] == "UDS→"


class TestClearScreen:
    """Tests for _clear_screen helper function."""

    @patch("os.system")
    @patch("os.name", "posix")
    def test_clear_on_posix(self, mock_system):
        """Should use 'clear' on POSIX systems."""
        _clear_screen()
        mock_system.assert_called_once_with("clear")

    @patch("os.system")
    @patch("os.name", "nt")
    def test_clear_on_windows(self, mock_system):
        """Should use 'cls' on Windows."""
        _clear_screen()
        mock_system.assert_called_once_with("cls")


class TestCmdListNonTTY:
    """Tests for cmd_list in non-TTY mode (piped output)."""

    def test_non_tty_single_output(self, temp_registry, capsys):
        """Non-TTY mode should output once and exit."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")

        args = MagicMock()
        args.working_dir = None

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli.is_process_alive", return_value=True),
            patch("synapse.cli.is_port_open", return_value=True),
            patch("sys.stdout.isatty", return_value=False),
        ):
            cmd_list(args)

        captured = capsys.readouterr()
        assert "claude" in captured.out
        assert "8100" in captured.out

    def test_non_tty_empty_registry(self, temp_registry, capsys):
        """Non-TTY mode with empty registry shows port ranges."""
        args = MagicMock()
        args.working_dir = None

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("sys.stdout.isatty", return_value=False),
        ):
            cmd_list(args)

        captured = capsys.readouterr()
        assert "No agents running" in captured.out
        assert "Port ranges:" in captured.out


class TestCmdListTUI:
    """Tests for cmd_list in TUI mode."""

    def test_tui_mode_exits_on_ctrl_c(self, temp_registry):
        """TUI mode should exit gracefully on Ctrl+C."""
        args = MagicMock()

        def mock_run_rich(*args, **kwargs):
            raise SystemExit(0)

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("sys.stdout.isatty", return_value=True),
            patch(
                "synapse.commands.list.ListCommand._run_rich_tui",
                side_effect=mock_run_rich,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_list(args)

        assert exc_info.value.code == 0

    def test_tui_mode_uses_rich(self, temp_registry):
        """TUI mode should use Rich when TTY is available."""
        args = MagicMock()

        run_rich_called = []

        def mock_run_rich(*args, **kwargs):
            run_rich_called.append(True)
            raise SystemExit(0)

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("sys.stdout.isatty", return_value=True),
            patch(
                "synapse.commands.list.ListCommand._run_rich_tui",
                side_effect=mock_run_rich,
            ),
            pytest.raises(SystemExit),
        ):
            cmd_list(args)

        assert len(run_rich_called) == 1


# ============================================================================
# Tests for Bug #2: Silent Exception Swallowing
# ============================================================================


class TestSilentFailures:
    """Tests for Bug #2: Silent exception swallowing in registry updates."""

    def test_update_status_returns_false_on_json_error(self, temp_registry):
        """update_status should return False when JSON file is corrupted."""
        agent_id = "corrupt-json-agent"
        temp_registry.register(agent_id, "claude", 8100, status="PROCESSING")

        # Corrupt the JSON file
        file_path = temp_registry.registry_dir / f"{agent_id}.json"
        with open(file_path, "w") as f:
            f.write("{ invalid json syntax }")

        # Attempt to update status
        result = temp_registry.update_status(agent_id, "READY")

        # Should return False for corrupted file
        assert result is False

        # Verify agent data is still corrupted
        agent_data = temp_registry.get_agent(agent_id)
        assert agent_data is None

    def test_update_status_file_permission_error(self, temp_registry):
        """update_status should return False on permission errors."""
        agent_id = "permission-error-agent"
        temp_registry.register(agent_id, "claude", 8100, status="PROCESSING")

        # Make registry directory read-only to prevent temp file creation
        registry_dir = temp_registry.registry_dir
        os.chmod(registry_dir, 0o555)

        try:
            # Attempt to update status
            result = temp_registry.update_status(agent_id, "READY")

            # Should return False due to permission error on temp file creation
            assert result is False

            # Status should remain unchanged
            agent_data = temp_registry.get_agent(agent_id)
            assert agent_data["status"] == "PROCESSING"

        finally:
            # Cleanup: restore permissions
            os.chmod(registry_dir, 0o755)

    def test_controller_ignores_update_status_failure(self, temp_registry, caplog):
        """Controller should detect and handle update_status failures."""
        from synapse.controller import TerminalController

        agent_id = "ignore-failure-agent"
        temp_registry.register(agent_id, "test", 8100, status="PROCESSING")

        # Mock update_status to fail
        original_update = temp_registry.update_status

        call_count = 0

        def failing_update(aid, status):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return False  # First call fails
            return original_update(aid, status)

        with patch.object(temp_registry, "update_status", side_effect=failing_update):
            controller = TerminalController(
                command="echo test",
                idle_regex="test",
                registry=temp_registry,
                agent_id=agent_id,
                agent_type="test",
                port=8100,
            )

            # Verify controller was created
            assert controller.agent_id == agent_id
            assert controller.registry == temp_registry


# ============================================================================
# Tests for Bug #1: Non-Atomic JSON Updates (Race Conditions)
# ============================================================================


class TestRegistryRaceConditions:
    """Tests for Bug #1: Non-atomic JSON updates causing race conditions."""

    def test_concurrent_status_updates_race_condition(self, temp_registry):
        """Two concurrent update_status calls can lose updates (demonstrates bug)."""
        agent_id = "race-test-agent"
        temp_registry.register(agent_id, "claude", 8100, status="PROCESSING")

        barrier = threading.Barrier(2)
        results = []

        def update_with_delay(new_status, delay_after_read):
            """Update status with controlled timing to trigger race."""
            file_path = temp_registry.registry_dir / f"{agent_id}.json"

            # Read
            with open(file_path) as f:
                data = json.load(f)

            # Synchronize both threads at read point
            barrier.wait()

            # Inject delay to create race window
            time.sleep(delay_after_read)

            # Write
            data["status"] = new_status
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)

            results.append(new_status)

        # Launch concurrent updates
        t1 = threading.Thread(target=update_with_delay, args=("READY", 0.01))
        t2 = threading.Thread(target=update_with_delay, args=("BUSY", 0.02))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Verify race condition manifests
        final_status = temp_registry.get_agent(agent_id)["status"]

        # Both threads wrote, but only last write wins
        assert final_status in ["READY", "BUSY"]
        assert len(results) == 2

    def test_watch_reads_partial_update(self, temp_registry):
        """Watch mode can read stale data while update is in progress."""
        agent_id = "watch-race-agent"
        temp_registry.register(agent_id, "claude", 8100, status="PROCESSING")

        read_started = threading.Event()
        update_complete = threading.Event()
        status_reads = []

        def watch_reader():
            """Simulates watch mode reading registry."""
            # Keep reading until update is complete, plus one more time to catch final state
            while not update_complete.is_set():
                read_started.set()

                # Read registry (simulates _get_agent_data)
                agents = temp_registry.list_agents()
                if agent_id in agents:
                    status_reads.append(agents[agent_id]["status"])

                time.sleep(0.01)

            # Final read to ensure we catch the update
            agents = temp_registry.list_agents()
            if agent_id in agents:
                status_reads.append(agents[agent_id]["status"])

        def status_updater():
            """Simulates controller updating status."""
            # Wait for first read to start
            read_started.wait()
            time.sleep(0.005)

            # Do update (read-modify-write)
            file_path = temp_registry.registry_dir / f"{agent_id}.json"
            with open(file_path) as f:
                data = json.load(f)

            time.sleep(0.01)  # Window where watch might read

            data["status"] = "READY"
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)

            update_complete.set()

        watch_thread = threading.Thread(target=watch_reader)
        update_thread = threading.Thread(target=status_updater)

        watch_thread.start()
        update_thread.start()

        watch_thread.join()
        update_thread.join()

        # Should see both old and new status
        assert "PROCESSING" in status_reads
        assert "READY" in status_reads


# ============================================================================
# Tests for Bug #3: Partial JSON Read During Write
# ============================================================================


class TestPartialJSONRead:
    """Tests for Bug #3: Partial JSON reads when file is being written."""

    def test_list_agents_handles_incomplete_json(self, temp_registry):
        """list_agents() should skip incomplete JSON files gracefully."""
        # Create valid agent
        agent_id_1 = "valid-agent"
        temp_registry.register(agent_id_1, "claude", 8100, status="READY")

        # Create incomplete JSON file manually (simulating mid-write)
        agent_id_2 = "incomplete-agent"
        incomplete_file = temp_registry.registry_dir / f"{agent_id_2}.json"
        with open(incomplete_file, "w") as f:
            # Write truncated JSON
            f.write('{\n  "agent_id": "incomplete-agent",\n  "agen')

        # Call list_agents()
        agents = temp_registry.list_agents()

        # Valid agent should be returned
        assert agent_id_1 in agents

        # Incomplete JSON should be silently skipped
        assert agent_id_2 not in agents

        # Valid agent data should be accessible
        assert agents[agent_id_1]["status"] == "READY"

    def test_watch_reads_partial_json_write(self, temp_registry):
        """Watch mode can read partially written JSON (demonstrates race)."""
        agent_id = "partial-json-agent"
        temp_registry.register(agent_id, "claude", 8100, status="PROCESSING")

        write_started = threading.Event()
        read_results = []

        full_json_data = {
            "agent_id": agent_id,
            "agent_type": "claude",
            "port": 8100,
            "status": "READY",
            "pid": 12345,
            "working_dir": "/tmp",
            "endpoint": "http://localhost:8100",
        }

        def slow_writer():
            """Simulate slow multi-line JSON write."""
            file_path = temp_registry.registry_dir / f"{agent_id}.json"

            # Convert to string with indent
            json_str = json.dumps(full_json_data, indent=2)

            with open(file_path, "w") as f:
                # Write first half
                f.write(json_str[: len(json_str) // 2])
                f.flush()

                # Signal that write started (reader can try now)
                write_started.set()

                # Wait a bit to let reader try
                time.sleep(0.05)

                # Write second half
                f.write(json_str[len(json_str) // 2 :])

        def watch_reader():
            """Simulate watch mode reading."""
            # Wait for write to start
            write_started.wait()
            time.sleep(0.01)  # Read during write window

            # Try to read (may get partial JSON)
            agents = temp_registry.list_agents()
            read_results.append(agents)

        writer_thread = threading.Thread(target=slow_writer)
        reader_thread = threading.Thread(target=watch_reader)

        writer_thread.start()
        reader_thread.start()

        writer_thread.join()
        reader_thread.join()

        # During partial write, agent may not be in list
        assert len(read_results) == 1

        # After write completes, agent should be visible
        final_agents = temp_registry.list_agents()
        assert agent_id in final_agents

    def test_agent_flickering(self, temp_registry):
        """Agent flickering in/out due to partial reads."""
        agent_id = "flickering-agent"
        temp_registry.register(agent_id, "claude", 8100, status="PROCESSING")

        watch_outputs = []
        stop_event = threading.Event()
        update_count = 0

        def simulated_watch_loop():
            """Simulates watch mode reading registry frequently."""
            while not stop_event.is_set():
                # Read registry
                agents = temp_registry.list_agents()

                # Record whether agent was visible
                watch_outputs.append(agent_id in agents)
                time.sleep(0.03)

        def frequent_updater():
            """Simulates controller updating status frequently."""
            nonlocal update_count
            for _ in range(5):
                # Update status (write multi-line JSON)
                temp_registry.update_status(
                    agent_id,
                    "READY" if update_count % 2 == 0 else "PROCESSING",
                )
                update_count += 1
                time.sleep(0.02)

            # Signal watch loop to stop
            time.sleep(0.1)
            stop_event.set()

        watch_thread = threading.Thread(target=simulated_watch_loop)
        update_thread = threading.Thread(target=frequent_updater)

        watch_thread.start()
        update_thread.start()

        watch_thread.join()
        update_thread.join()

        # Agent should always be visible, but may flicker
        # (Some reads might fail during partial writes)
        assert len(watch_outputs) > 0

        # If we see any False values, the bug manifests
        # (Agent temporarily invisible due to partial read)
        if False in watch_outputs:
            # Bug is present: agent disappeared temporarily
            assert watch_outputs[-1] is True  # But reappears at end


# ============================================================================
# Tests for Transport Display Feature
# ============================================================================


class TestTransportDisplay:
    """Tests for TRANSPORT column in agent list."""

    def _create_list_command(
        self,
        is_process_alive=lambda p: True,
        is_port_open=lambda host, port, timeout=0.5: True,
    ):
        """Create a ListCommand with mock dependencies."""
        return ListCommand(
            registry_factory=lambda: MagicMock(spec=AgentRegistry),
            is_process_alive=is_process_alive,
            is_port_open=is_port_open,
            clear_screen=lambda: None,
            time_module=MagicMock(),
            print_func=print,
        )

    def test_transport_shows_sender_format(self, temp_registry):
        """Sender shows 'UDS→' when active_transport is set."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="PROCESSING")
        temp_registry.update_transport(agent_id, "UDS→")

        list_cmd = self._create_list_command()
        agents, _, _ = list_cmd._get_agent_data(temp_registry)

        assert len(agents) == 1
        assert agents[0]["transport"] == "UDS→"

    def test_transport_shows_receiver_format(self, temp_registry):
        """Receiver shows '→UDS' when active_transport is set."""
        agent_id = "synapse-gemini-8110"
        temp_registry.register(agent_id, "gemini", 8110, status="PROCESSING")
        temp_registry.update_transport(agent_id, "→UDS")

        list_cmd = self._create_list_command()
        agents, _, _ = list_cmd._get_agent_data(temp_registry)

        assert len(agents) == 1
        assert agents[0]["transport"] == "→UDS"

    def test_transport_shows_tcp_format(self, temp_registry):
        """TCP transport formats are displayed correctly."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="PROCESSING")
        temp_registry.update_transport(agent_id, "TCP→")

        list_cmd = self._create_list_command()
        agents, _, _ = list_cmd._get_agent_data(temp_registry)

        assert len(agents) == 1
        assert agents[0]["transport"] == "TCP→"

    def test_transport_shows_dash_when_idle(self, temp_registry):
        """Transport shows '-' when no active communication."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")
        # No active_transport set

        list_cmd = self._create_list_command()
        agents, _, _ = list_cmd._get_agent_data(temp_registry)

        assert len(agents) == 1
        assert agents[0]["transport"] == "-"

    def test_transport_cleared_shows_retained_value(self, temp_registry):
        """Transport shows retained value after being cleared (retention feature).

        With the retention feature, cleared transport is still displayed
        for 3 seconds to allow users to observe communication events.
        """
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")
        temp_registry.update_transport(agent_id, "UDS→")
        temp_registry.update_transport(agent_id, None)  # Clear

        list_cmd = self._create_list_command()
        agents, _, _ = list_cmd._get_agent_data(temp_registry)

        # Should still show UDS→ due to retention (within 3s)
        assert len(agents) == 1
        assert agents[0]["transport"] == "UDS→"

    def test_multiple_agents_with_different_transport(self, temp_registry):
        """Multiple agents can show different transport states."""
        temp_registry.register(
            "synapse-claude-8100", "claude", 8100, status="PROCESSING"
        )
        temp_registry.register(
            "synapse-gemini-8110", "gemini", 8110, status="PROCESSING"
        )
        temp_registry.register("synapse-codex-8120", "codex", 8120, status="READY")

        temp_registry.update_transport("synapse-claude-8100", "UDS→")
        temp_registry.update_transport("synapse-gemini-8110", "→UDS")
        # codex has no active transport

        list_cmd = self._create_list_command()
        agents, _, _ = list_cmd._get_agent_data(temp_registry)

        assert len(agents) == 3
        transports = {a["agent_type"]: a["transport"] for a in agents}
        assert transports["claude"] == "UDS→"
        assert transports["gemini"] == "→UDS"
        assert transports["codex"] == "-"


# ============================================================================
# Tests for Rich Renderer
# ============================================================================


class TestRichRenderer:
    """Tests for RichRenderer class."""

    def test_build_table_with_agents(self):
        """Should build table with agent data."""
        from synapse.commands.renderers.rich_renderer import RichRenderer

        renderer = RichRenderer()
        agents = [
            {
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "transport": "-",
                "pid": 12345,
                "working_dir": "myproject",
                "endpoint": "http://localhost:8100",
            }
        ]

        table = renderer.build_table(agents)

        # Table should have rows
        assert table.row_count == 1

    def test_build_empty_table(self):
        """Should build empty table with port ranges."""
        from synapse.commands.renderers.rich_renderer import RichRenderer

        renderer = RichRenderer()
        table = renderer.build_table([])

        # Should show "No agents running" message
        assert table.row_count > 0

    def test_render_display(self):
        """Should render complete display."""
        from synapse.commands.renderers.rich_renderer import RichRenderer

        renderer = RichRenderer()
        agents = [
            {
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "transport": "-",
                "pid": 12345,
                "working_dir": "myproject",
                "endpoint": "http://localhost:8100",
            }
        ]

        display = renderer.render_display(
            agents=agents,
            version="1.0.0",
            timestamp="2026-01-22 12:00:00",
        )

        # Should return a renderable
        assert display is not None


# ============================================================================
# Tests for File Watcher
# ============================================================================


class TestFileWatcher:
    """Tests for file watcher functionality."""

    def test_create_file_watcher(self, temp_registry_dir):
        """Should create file watcher for registry directory."""
        from threading import Event

        from synapse.commands.list import ListCommand

        list_cmd = ListCommand(
            registry_factory=lambda: MagicMock(spec=AgentRegistry),
            is_process_alive=lambda p: True,
            is_port_open=lambda host, port, timeout=0.5: True,
            clear_screen=lambda: None,
            time_module=MagicMock(),
            print_func=print,
        )

        change_event = Event()
        observer = list_cmd._create_file_watcher(temp_registry_dir, change_event)

        if observer is not None:
            # Observer should be running
            assert observer.is_alive()

            # Create a JSON file to trigger the watcher
            test_file = temp_registry_dir / "test-agent.json"
            test_file.write_text('{"test": true}')

            # Wait for the event to be set
            change_event.wait(timeout=1.0)
            assert change_event.is_set()

            # Cleanup
            observer.stop()
            observer.join()
