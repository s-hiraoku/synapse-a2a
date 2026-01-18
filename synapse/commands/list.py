"""List command implementation for Synapse CLI."""

from __future__ import annotations

import argparse
import os
import sys
import time as time_module
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from synapse.file_safety import FileSafetyManager
from synapse.port_manager import PORT_RANGES
from synapse.registry import AgentRegistry

if TYPE_CHECKING:
    from rich.console import Console


class _TimeModule(Protocol):
    """Protocol for time module interface."""

    def strftime(self, format: str) -> str: ...
    def sleep(self, seconds: float) -> None: ...
    def time(self) -> float: ...


class ListCommand:
    """List running agents (with optional watch mode)."""

    def __init__(
        self,
        registry_factory: Callable[[], AgentRegistry],
        is_process_alive: Callable[[int], bool],
        is_port_open: Callable[..., bool],
        clear_screen: Callable[[], None],
        time_module: _TimeModule | Any,
        print_func: Callable[[str], None],
    ) -> None:
        self._registry_factory = registry_factory
        self._is_process_alive = is_process_alive
        self._is_port_open = is_port_open
        self._clear_screen = clear_screen
        self._time = time_module
        self._print = print_func

    def _is_agent_alive(
        self, registry: AgentRegistry, agent_id: str, info: dict[str, Any]
    ) -> bool:
        """Check if an agent is alive and unregister if dead.

        Args:
            registry: AgentRegistry instance for cleanup.
            agent_id: Agent identifier.
            info: Agent info dictionary.

        Returns:
            True if agent is alive, False if dead (and unregistered).
        """
        pid = info.get("pid")
        port = info.get("port")
        status = info.get("status", "-")

        # Check 1: PID must be alive
        if pid and not self._is_process_alive(pid):
            registry.unregister(agent_id)
            return False

        # Check 2: Port must be open (agent server responding)
        # Skip port check for PROCESSING agents (server may still be starting)
        if (
            status != "PROCESSING"
            and port
            and not self._is_port_open("localhost", port, timeout=0.5)
        ):
            registry.unregister(agent_id)
            return False

        return True

    def _format_empty_message(self) -> str:
        """Format the 'no agents running' message with port ranges."""
        lines = ["No agents running.", "", "Port ranges:"]
        for agent_type, (start, end) in sorted(PORT_RANGES.items()):
            lines.append(f"  {agent_type}: {start}-{end}")
        return "\n".join(lines)

    def _render_agent_table(
        self, registry: AgentRegistry, is_watch_mode: bool = False
    ) -> str:
        """
        Render the agent table output.

        Args:
            registry: AgentRegistry instance
            is_watch_mode: If True, show TRANSPORT column for real-time status

        Returns:
            str: Formatted table output
        """
        agents = registry.list_agents()

        if not agents:
            return self._format_empty_message()

        file_safety = FileSafetyManager.from_env()
        show_file_safety = file_safety.enabled

        # Build column list based on mode
        columns: list[tuple[str, int]] = [
            ("TYPE", 10),
            ("PORT", 8),
            ("STATUS", 12),
        ]
        if is_watch_mode:
            columns.append(("TRANSPORT", 10))
        columns.extend([("PID", 8), ("WORKING_DIR", 50)])
        if show_file_safety:
            columns.append(("EDITING FILE", 30))
        columns.append(("ENDPOINT", 0))  # 0 means no padding (last column)

        def format_row(values: list[tuple[str, int]]) -> str:
            """Format a row of values with their widths."""
            parts = [
                f"{value:<{width}}" if width > 0 else value for value, width in values
            ]
            return " ".join(parts)

        header = format_row([(col, width) for col, width in columns])

        lines = [header, "-" * len(header)]

        live_agents = False
        for agent_id, info in agents.items():
            if not self._is_agent_alive(registry, agent_id, info):
                continue

            live_agents = True
            pid = info.get("pid")
            status = info.get("status", "-")

            # Build row values matching column order
            row_values = [
                (info.get("agent_type", "unknown"), 10),
                (info.get("port", "-"), 8),
                (status, 12),
            ]
            if is_watch_mode:
                transport = (
                    registry.get_transport_display(agent_id, retention_seconds=3.0)
                    or "-"
                )
                row_values.append((transport, 10))
            row_values.extend(
                [
                    (pid or "-", 8),
                    (os.path.basename(info.get("working_dir", "")) or "-", 50),
                ]
            )

            if show_file_safety:
                agent_type = info.get("agent_type", "")
                if pid:
                    locks = file_safety.list_locks(pid=pid, include_stale=False)
                else:
                    locks = file_safety.list_locks(
                        agent_type=agent_type, include_stale=False
                    )
                editing_file = "-"
                if locks:
                    file_path = locks[0].get("file_path")
                    if file_path:
                        editing_file = os.path.basename(file_path)
                row_values.append((editing_file, 30))

            row_values.append((info.get("endpoint", "-"), 0))

            lines.append(format_row(row_values))

        if not live_agents:
            return self._format_empty_message()

        # Check for stale locks and add warning
        if show_file_safety:
            stale_locks = file_safety.get_stale_locks()
            if stale_locks:
                lines.append("")
                count = len(stale_locks)
                lines.append(f"Warning: {count} stale lock(s) from dead processes.")
                lines.append(
                    "Run 'synapse file-safety cleanup-locks' to clean them up."
                )

        return "\n".join(lines)

    def _get_agent_data_for_rich(
        self,
        registry: AgentRegistry,
        is_watch_mode: bool = False,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        """Get agent data formatted for Rich renderer.

        Args:
            registry: AgentRegistry instance.
            is_watch_mode: If True, include transport information.

        Returns:
            Tuple of (agents_list, stale_locks, show_file_safety).
        """
        agents = registry.list_agents()
        file_safety = FileSafetyManager.from_env()
        show_file_safety = file_safety.enabled

        agents_list: list[dict[str, Any]] = []

        for agent_id, info in agents.items():
            if not self._is_agent_alive(registry, agent_id, info):
                continue

            pid = info.get("pid")
            working_dir_full = info.get("working_dir", "-")
            working_dir_short = (
                os.path.basename(working_dir_full) if working_dir_full != "-" else "-"
            )
            agent_data: dict[str, Any] = {
                "agent_id": agent_id,
                "agent_type": info.get("agent_type", "unknown"),
                "port": info.get("port", "-"),
                "status": info.get("status", "-"),
                "pid": pid or "-",
                "working_dir": working_dir_short,
                "working_dir_full": working_dir_full,
                "endpoint": info.get("endpoint", "-"),
            }

            if is_watch_mode:
                transport = (
                    registry.get_transport_display(agent_id, retention_seconds=3.0)
                    or "-"
                )
                agent_data["transport"] = transport

            if show_file_safety:
                agent_type = info.get("agent_type", "")
                if pid:
                    locks = file_safety.list_locks(pid=pid, include_stale=False)
                else:
                    locks = file_safety.list_locks(
                        agent_type=agent_type, include_stale=False
                    )
                editing_file = "-"
                if locks:
                    file_path = locks[0].get("file_path")
                    if file_path:
                        editing_file = os.path.basename(file_path)
                agent_data["editing_file"] = editing_file

            agents_list.append(agent_data)

        # Get stale locks
        stale_locks: list[dict[str, Any]] = []
        if show_file_safety:
            stale_locks = file_safety.get_stale_locks()

        return agents_list, stale_locks, show_file_safety

    def _setup_nonblocking_input(self) -> tuple[Any, Any] | None:
        """Set up non-blocking keyboard input.

        Returns:
            Tuple of (old_settings, old_flags) for restoration, or None if failed.
        """
        try:
            import termios
            import tty

            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            return (old_settings, fd)
        except Exception:
            return None

    def _restore_terminal(self, saved: tuple[Any, Any] | None) -> None:
        """Restore terminal to original settings.

        Args:
            saved: Tuple returned by _setup_nonblocking_input.
        """
        if saved is None:
            return
        try:
            import termios

            old_settings, fd = saved
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass

    def _read_key_nonblocking(self) -> str | None:
        """Read a single key without blocking.

        Returns:
            Key character or None if no input available.
        """
        import select

        try:
            if select.select([sys.stdin], [], [], 0)[0]:
                return sys.stdin.read(1)
        except Exception:
            pass
        return None

    def _run_watch_mode_rich(
        self,
        registry: AgentRegistry,
        interval: float,
        console: Console,
        pkg_version: str,
    ) -> None:
        """Run watch mode with Rich TUI.

        Args:
            registry: AgentRegistry instance.
            interval: Refresh interval in seconds.
            console: Rich Console instance.
            pkg_version: Package version string.
        """
        from rich.live import Live

        from synapse.commands.renderers.rich_renderer import RichRenderer

        renderer = RichRenderer(console=console)

        # Set up non-blocking input for interactive mode
        saved_terminal = self._setup_nonblocking_input()
        interactive = saved_terminal is not None
        selected_row: int | None = None

        # Import terminal jump functionality
        from synapse.terminal_jump import can_jump, jump_to_terminal

        jump_available = can_jump()

        # Track current agents for jump functionality
        current_agents: list[dict[str, Any]] = []

        try:
            with Live(console=console, refresh_per_second=4) as live:
                last_update = 0.0
                while True:
                    # Check for keyboard input
                    if interactive:
                        key = self._read_key_nonblocking()
                        if key is not None:
                            # ESC key (0x1b) clears selection
                            if key == "\x1b":
                                selected_row = None
                            elif key.isdigit() and key != "0":
                                selected_row = int(key)
                            # Enter or 'j' key triggers terminal jump
                            elif (
                                key in ("\r", "\n", "j", "J")
                                and jump_available
                                and selected_row is not None
                                and 1 <= selected_row <= len(current_agents)
                            ):
                                agent = current_agents[selected_row - 1]
                                jump_to_terminal(agent)

                    # Update display at interval
                    # Use injected time module if it has time(), otherwise fallback
                    current_time = (
                        self._time.time()
                        if hasattr(self._time, "time")
                        else time_module.time()
                    )
                    if current_time - last_update >= interval:
                        agents, stale_locks, show_file_safety = (
                            self._get_agent_data_for_rich(registry, is_watch_mode=True)
                        )

                        # Update current_agents for terminal jump
                        current_agents = agents

                        # Validate selected_row against current agent count
                        if selected_row is not None and selected_row > len(agents):
                            selected_row = None

                        timestamp = self._time.strftime("%Y-%m-%d %H:%M:%S")

                        display = renderer.render_watch_display(
                            agents=agents,
                            version=pkg_version,
                            interval=interval,
                            timestamp=timestamp,
                            show_file_safety=show_file_safety,
                            stale_locks=stale_locks,
                            interactive=interactive,
                            selected_row=selected_row,
                            jump_available=jump_available,
                        )

                        live.update(display)
                        last_update = current_time

                    # Small sleep to prevent CPU spinning
                    self._time.sleep(0.05)
        except KeyboardInterrupt:
            pass
        finally:
            self._restore_terminal(saved_terminal)
            console.print("\n[dim]Exiting watch mode...[/dim]")
            raise SystemExit(0)

    def _run_watch_mode_plain(
        self, registry: AgentRegistry, interval: float, pkg_version: str
    ) -> None:
        """Run watch mode with plain text output.

        Args:
            registry: AgentRegistry instance.
            interval: Refresh interval in seconds.
            pkg_version: Package version string.
        """
        try:
            while True:
                self._clear_screen()
                title = f"Synapse A2A v{pkg_version} - Agent List (every {interval}s)"
                self._print(title)
                now = self._time.strftime("%Y-%m-%d %H:%M:%S")
                self._print(f"Last updated: {now}")
                self._print("")
                self._print(self._render_agent_table(registry, is_watch_mode=True))
                self._time.sleep(interval)
        except KeyboardInterrupt:
            self._print("\n\nExiting watch mode...")
            raise SystemExit(0) from None

    def _should_use_rich(self, args: argparse.Namespace) -> bool:
        """Determine if Rich TUI should be used.

        Args:
            args: Parsed command line arguments.

        Returns:
            True if Rich mode should be used.
        """
        # Check explicit --no-rich flag
        if getattr(args, "no_rich", False):
            return False

        # Auto-detect: use Rich only if stdout is a TTY
        return sys.stdout.isatty()

    def run(self, args: argparse.Namespace) -> None:
        """List running agents (with optional watch mode)."""
        registry = self._registry_factory()
        watch_mode = getattr(args, "watch", False)
        interval = getattr(args, "interval", 2.0)

        if not watch_mode:
            # Normal mode: single output
            self._print(self._render_agent_table(registry))
            return

        # Watch mode: continuous refresh
        # Get version for display
        try:
            from importlib.metadata import version

            pkg_version = version("synapse-a2a")
        except Exception:
            pkg_version = "unknown"

        use_rich = self._should_use_rich(args)

        if use_rich:
            from rich.console import Console

            console = Console()
            self._run_watch_mode_rich(registry, interval, console, pkg_version)
        else:
            self._print("Watch mode: Press Ctrl+C to exit\n")
            self._run_watch_mode_plain(registry, interval, pkg_version)
