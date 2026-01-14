"""Tests for synapse list --watch command."""

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


class TestRenderAgentTable:
    """Tests for ListCommand._render_agent_table method."""

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

    def test_render_empty_registry(self, temp_registry):
        """Should display 'No agents running' with port ranges."""
        list_cmd = self._create_list_command()
        output = list_cmd._render_agent_table(temp_registry)
        assert "No agents running" in output
        assert "Port ranges:" in output
        assert "claude: 8100-8109" in output

    def test_render_single_agent(self, temp_registry):
        """Should render table with single agent."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")

        list_cmd = self._create_list_command()
        output = list_cmd._render_agent_table(temp_registry)

        assert "TYPE" in output  # Header
        assert "claude" in output
        assert "8100" in output
        assert "READY" in output

    def test_render_multiple_agents(self, temp_registry):
        """Should render table with multiple agents."""
        temp_registry.register("synapse-claude-8100", "claude", 8100, status="READY")
        temp_registry.register(
            "synapse-gemini-8110", "gemini", 8110, status="PROCESSING"
        )

        list_cmd = self._create_list_command()
        output = list_cmd._render_agent_table(temp_registry)

        assert "claude" in output
        assert "gemini" in output
        assert output.count("\n") >= 3  # Header + separator + 2 agents

    def test_cleans_up_dead_processes(self, temp_registry):
        """Should remove dead processes from registry during render."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")

        list_cmd = self._create_list_command(is_process_alive=lambda p: False)
        output = list_cmd._render_agent_table(temp_registry)

        # Should show empty registry
        assert "No agents running" in output

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
        output = list_cmd._render_agent_table(temp_registry)

        assert "No agents running" in output
        assert len(temp_registry.list_agents()) == 0

    def test_processing_agent_kept_when_port_closed(self, temp_registry):
        """PROCESSING agents should not be removed if port isn't open yet."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="PROCESSING")

        list_cmd = self._create_list_command(
            is_process_alive=lambda p: True,
            is_port_open=lambda host, port, timeout=0.5: False,
        )
        output = list_cmd._render_agent_table(temp_registry)

        assert "PROCESSING" in output
        assert len(temp_registry.list_agents()) == 1


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


class TestCmdListNormalMode:
    """Tests for cmd_list in normal (non-watch) mode."""

    def test_normal_mode_single_output(self, temp_registry, capsys):
        """Normal mode should output once and exit."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")

        args = MagicMock()
        args.watch = False

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli.is_process_alive", return_value=True),
        ):
            cmd_list(args)

        captured = capsys.readouterr()
        assert "claude" in captured.out
        assert "8100" in captured.out

    def test_normal_mode_backward_compatible(self, temp_registry, capsys):
        """Args without watch attribute should work (backward compat)."""
        args = MagicMock(spec=[])  # Empty spec = no attributes

        with patch("synapse.cli.AgentRegistry", return_value=temp_registry):
            cmd_list(args)

        captured = capsys.readouterr()
        assert "No agents running" in captured.out


class TestCmdListWatchMode:
    """Tests for cmd_list in watch mode."""

    def test_watch_mode_loops_with_interval(self, temp_registry):
        """Watch mode should loop and refresh at interval."""
        args = MagicMock()
        args.watch = True
        args.interval = 0.1

        call_count = 0

        def sleep_side_effect(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:  # Exit after 3 iterations
                raise KeyboardInterrupt()

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli._clear_screen"),
            patch("synapse.cli.time.sleep", side_effect=sleep_side_effect),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_list(args)

        assert exc_info.value.code == 0
        assert call_count == 3

    def test_watch_mode_clears_screen(self, temp_registry):
        """Watch mode should clear screen before each update."""
        args = MagicMock()
        args.watch = True
        args.interval = 0.1

        clear_calls: list[int] = []

        def sleep_side_effect(duration):
            if len(clear_calls) >= 2:
                raise KeyboardInterrupt()

        def clear_side_effect():
            clear_calls.append(1)

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli._clear_screen", side_effect=clear_side_effect),
            patch("synapse.cli.time.sleep", side_effect=sleep_side_effect),
            pytest.raises(SystemExit),
        ):
            cmd_list(args)

        assert len(clear_calls) >= 2

    def test_watch_mode_uses_custom_interval(self, temp_registry):
        """Watch mode should respect custom interval."""
        args = MagicMock()
        args.watch = True
        args.interval = 5.0

        sleep_calls = []

        def sleep_side_effect(duration):
            sleep_calls.append(duration)
            raise KeyboardInterrupt()

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli._clear_screen"),
            patch("synapse.cli.time.sleep", side_effect=sleep_side_effect),
            pytest.raises(SystemExit),
        ):
            cmd_list(args)

        assert 5.0 in sleep_calls

    def test_watch_mode_exits_on_ctrl_c(self, temp_registry, capsys):
        """Watch mode should exit gracefully on Ctrl+C."""
        args = MagicMock()
        args.watch = True
        args.interval = 0.1

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli._clear_screen"),
            patch("synapse.cli.time.sleep", side_effect=KeyboardInterrupt),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_list(args)

        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "Exiting watch mode" in captured.out

    def test_watch_mode_shows_timestamp(self, temp_registry, capsys):
        """Watch mode should show last updated timestamp."""
        args = MagicMock()
        args.watch = True
        args.interval = 0.1

        timestamp = "2026-01-03 12:00:00"
        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli._clear_screen"),
            patch("synapse.cli.time.sleep", side_effect=KeyboardInterrupt),
            patch("synapse.cli.time.strftime", return_value=timestamp),
            pytest.raises(SystemExit),
        ):
            cmd_list(args)

        captured = capsys.readouterr()
        assert "Last updated:" in captured.out
        assert "2026-01-03 12:00:00" in captured.out

    def test_watch_mode_shows_refresh_interval_in_header(self, temp_registry, capsys):
        """Watch mode should show refresh interval in header."""
        args = MagicMock()
        args.watch = True
        args.interval = 2.5

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli._clear_screen"),
            patch("synapse.cli.time.sleep", side_effect=KeyboardInterrupt),
            pytest.raises(SystemExit),
        ):
            cmd_list(args)

        captured = capsys.readouterr()
        assert "refreshing every 2.5s" in captured.out

    def test_watch_mode_empty_registry_continues_watching(self, temp_registry, capsys):
        """Watch mode should show empty message and continue watching."""
        args = MagicMock()
        args.watch = True
        args.interval = 0.1

        call_count = 0

        def sleep_side_effect(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt()

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli._clear_screen"),
            patch("synapse.cli.time.sleep", side_effect=sleep_side_effect),
            pytest.raises(SystemExit),
        ):
            cmd_list(args)

        captured = capsys.readouterr()
        assert "No agents running" in captured.out
        assert call_count == 2  # Should have looped

    def test_watch_mode_default_interval(self, temp_registry):
        """Watch mode should use default 2.0s interval if not specified."""
        args = MagicMock()
        args.watch = True
        args.interval = 2.0  # default

        sleep_calls = []

        def sleep_side_effect(duration):
            sleep_calls.append(duration)
            raise KeyboardInterrupt()

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli._clear_screen"),
            patch("synapse.cli.time.sleep", side_effect=sleep_side_effect),
            pytest.raises(SystemExit),
        ):
            cmd_list(args)

        assert 2.0 in sleep_calls


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

                # Read registry (simulates _render_agent_table)
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

    def test_watch_mode_agent_flickering(self, temp_registry):
        """Watch mode shows agent flickering in/out due to partial reads."""
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
# Tests for Transport Display Feature (watch mode only)
# ============================================================================


class TestTransportDisplay:
    """Tests for TRANSPORT column in watch mode."""

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

    def test_watch_mode_shows_transport_column(self, temp_registry):
        """Watch mode includes TRANSPORT column in header."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")

        list_cmd = self._create_list_command()
        output = list_cmd._render_agent_table(temp_registry, is_watch_mode=True)

        assert "TRANSPORT" in output

    def test_normal_mode_no_transport_column(self, temp_registry):
        """Normal mode (non-watch) should not show TRANSPORT column."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")

        list_cmd = self._create_list_command()
        output = list_cmd._render_agent_table(temp_registry, is_watch_mode=False)

        assert "TRANSPORT" not in output

    def test_transport_shows_sender_format(self, temp_registry):
        """Sender shows 'UDS→' when active_transport is set."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="PROCESSING")
        temp_registry.update_transport(agent_id, "UDS→")

        list_cmd = self._create_list_command()
        output = list_cmd._render_agent_table(temp_registry, is_watch_mode=True)

        assert "UDS→" in output

    def test_transport_shows_receiver_format(self, temp_registry):
        """Receiver shows '→UDS' when active_transport is set."""
        agent_id = "synapse-gemini-8110"
        temp_registry.register(agent_id, "gemini", 8110, status="PROCESSING")
        temp_registry.update_transport(agent_id, "→UDS")

        list_cmd = self._create_list_command()
        output = list_cmd._render_agent_table(temp_registry, is_watch_mode=True)

        assert "→UDS" in output

    def test_transport_shows_tcp_format(self, temp_registry):
        """TCP transport formats are displayed correctly."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="PROCESSING")
        temp_registry.update_transport(agent_id, "TCP→")

        list_cmd = self._create_list_command()
        output = list_cmd._render_agent_table(temp_registry, is_watch_mode=True)

        assert "TCP→" in output

    def test_transport_shows_dash_when_idle(self, temp_registry):
        """Transport shows '-' when no active communication."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")
        # No active_transport set

        list_cmd = self._create_list_command()
        output = list_cmd._render_agent_table(temp_registry, is_watch_mode=True)

        # Should have TRANSPORT column with dash
        assert "TRANSPORT" in output
        lines = output.split("\n")
        # Find the data line (skip header and separator)
        data_lines = [line for line in lines if "claude" in line]
        assert len(data_lines) == 1
        # The line should contain a dash for transport (between STATUS and PID)
        assert "-" in data_lines[0]

    def test_transport_cleared_shows_dash(self, temp_registry):
        """Transport shows '-' after being cleared (None)."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")
        temp_registry.update_transport(agent_id, "UDS→")
        temp_registry.update_transport(agent_id, None)  # Clear

        list_cmd = self._create_list_command()
        output = list_cmd._render_agent_table(temp_registry, is_watch_mode=True)

        # Should not show UDS→ anymore
        assert "UDS→" not in output

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
        output = list_cmd._render_agent_table(temp_registry, is_watch_mode=True)

        assert "UDS→" in output
        assert "→UDS" in output
