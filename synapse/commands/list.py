"""List command implementation for Synapse CLI."""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from collections.abc import Callable
from pathlib import Path
from threading import Event
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
    """List running agents with Rich TUI and event-driven updates."""

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

        # Check 1: PID must be alive
        if pid and not self._is_process_alive(pid):
            registry.unregister(agent_id)
            return False

        # Check 2: Port must be open (agent server responding)
        # Skip port check for PROCESSING agents (server may still be starting)
        is_starting = info.get("status", "-") == "PROCESSING"
        if (
            not is_starting
            and port
            and not self._is_port_open("localhost", port, timeout=0.5)
        ):
            registry.unregister(agent_id)
            return False

        return True

    def _get_agent_data(
        self,
        registry: AgentRegistry,
        working_dir_filter: str | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        """Get agent data formatted for Rich renderer.

        Args:
            registry: AgentRegistry instance.
            working_dir_filter: Optional filter for working directory (partial match,
                case-insensitive).

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
                "name": info.get("name"),
                "role": info.get("role"),
                "port": info.get("port", "-"),
                "status": info.get("status", "-"),
                "pid": pid or "-",
                "working_dir": working_dir_short,
                "working_dir_full": working_dir_full,
                "endpoint": info.get("endpoint", "-"),
                "tty_device": info.get("tty_device"),
                "zellij_pane_id": info.get("zellij_pane_id"),
                "current_task_preview": info.get("current_task_preview"),
            }

            # Include transport info
            transport = (
                registry.get_transport_display(agent_id, retention_seconds=3.0) or "-"
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

        # Apply filter (partial match, case-insensitive) to TYPE, NAME, and WORKING_DIR
        if working_dir_filter:
            filter_lower = working_dir_filter.lower()
            agents_list = [
                a
                for a in agents_list
                if filter_lower in a["working_dir_full"].lower()
                or filter_lower in a.get("agent_type", "").lower()
                or filter_lower in (a.get("name") or "").lower()
            ]

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
        """Read a single key or escape sequence without blocking.

        Uses os.read() for platform-stable nonblocking reads and prefix-matching
        for escape sequences that may arrive in parts.

        Returns:
            Key character, escape sequence (e.g., "UP", "DOWN"), or None.
        """
        import fcntl
        import os
        import select

        # Known escape sequences (bytes)
        KNOWN_SEQUENCES: dict[bytes, str] = {
            b"\x1b[A": "UP",
            b"\x1b[B": "DOWN",
        }

        fd = sys.stdin.fileno()
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)

        try:
            # Check if data is available
            if not select.select([sys.stdin], [], [], 0)[0]:
                return None

            # Set non-blocking mode
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            # Read initial bytes using os.read (platform-stable)
            try:
                buf = os.read(fd, 1)
            except (BlockingIOError, OSError):
                return None

            if not buf:
                return None

            # If not an escape character, return immediately
            if buf[0:1] != b"\x1b":
                fcntl.fcntl(fd, fcntl.F_SETFL, flags)  # Restore before return
                return buf.decode("utf-8", errors="ignore")

            # Accumulate bytes for escape sequence detection
            # Use short timeout to wait for remaining bytes
            max_seq_len = max(len(seq) for seq in KNOWN_SEQUENCES)

            while len(buf) < max_seq_len:
                # Check if current buffer matches a complete sequence
                if buf in KNOWN_SEQUENCES:
                    fcntl.fcntl(fd, fcntl.F_SETFL, flags)
                    return KNOWN_SEQUENCES[buf]

                # Check if buffer is a prefix of any known sequence
                is_prefix = any(
                    seq.startswith(buf) and seq != buf for seq in KNOWN_SEQUENCES
                )
                if not is_prefix:
                    # Not a prefix of any known sequence, stop reading
                    break

                # Wait briefly for more bytes (escape sequences arrive quickly)
                if not select.select([sys.stdin], [], [], 0.05)[0]:
                    # Timeout - no more bytes coming
                    break

                try:
                    next_byte = os.read(fd, 1)
                except (BlockingIOError, OSError):
                    break

                if not next_byte:
                    break

                buf += next_byte

            # Restore flags before returning
            fcntl.fcntl(fd, fcntl.F_SETFL, flags)

            # Check for complete sequence match
            if buf in KNOWN_SEQUENCES:
                return KNOWN_SEQUENCES[buf]

            # Standalone ESC (no sequence matched)
            if buf == b"\x1b":
                return "\x1b"

            # Partial or unknown escape sequence - treat as ESC
            if buf.startswith(b"\x1b"):
                return "\x1b"

            # Return first character
            return buf[0:1].decode("utf-8", errors="ignore") or None

        except Exception:
            pass
        finally:
            # Always restore original flags
            with contextlib.suppress(Exception):
                fcntl.fcntl(fd, fcntl.F_SETFL, flags)

        return None

    def _kill_agent(self, registry: AgentRegistry, agent: dict[str, Any]) -> None:
        """Kill an agent and unregister from registry.

        Args:
            registry: AgentRegistry instance.
            agent: Agent data dictionary.
        """
        import signal

        agent_id = agent.get("agent_id")
        pid = agent.get("pid")

        if not pid or pid == "-":
            return

        try:
            os.kill(int(pid), signal.SIGTERM)
            if agent_id:
                registry.unregister(agent_id)
        except ProcessLookupError:
            # Process already dead, cleanup registry
            if agent_id:
                registry.unregister(agent_id)
        except PermissionError:
            # No permission to kill - do not unregister
            pass
        except OSError:
            # Other OS-level errors - do not unregister
            pass
        except (ValueError, TypeError):
            pass  # Invalid PID

    def _create_file_watcher(
        self, registry_dir: Path, change_event: Event
    ) -> Any | None:
        """Create a file watcher for registry directory.

        Args:
            registry_dir: Path to registry directory.
            change_event: Event to signal when changes detected.

        Returns:
            Observer instance if successful, None otherwise.
        """
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer

            class RegistryChangeHandler(FileSystemEventHandler):
                def __init__(self, event: Event) -> None:
                    self._event = event

                def on_any_event(self, event: Any) -> None:
                    # Only trigger on JSON file changes
                    if event.src_path.endswith(".json"):
                        self._event.set()

            observer = Observer()
            handler = RegistryChangeHandler(change_event)
            observer.schedule(handler, str(registry_dir), recursive=False)
            observer.start()
            return observer
        except ImportError:
            return None
        except Exception:
            return None

    def _run_rich_tui(
        self,
        registry: AgentRegistry,
        console: Console,
        pkg_version: str,
    ) -> None:
        """Run Rich TUI with event-driven updates.

        Args:
            registry: AgentRegistry instance.
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

        # Set up file watcher
        change_event = Event()
        observer = self._create_file_watcher(registry.registry_dir, change_event)

        # Force initial update
        change_event.set()

        # Track if display needs refresh (for selection changes)
        needs_refresh = False

        # Kill confirmation state
        kill_confirm_agent: dict[str, Any] | None = None

        # Filter state
        filter_mode = False
        filter_input = ""  # Text being typed in filter mode
        active_filter = ""  # Applied filter

        # Fallback polling (10 seconds) in case file watcher misses events
        last_poll_time = self._time.time()
        poll_interval = 10.0

        try:
            with Live(
                console=console,
                auto_refresh=False,
                vertical_overflow="crop",
            ) as live:
                while True:
                    # Check for keyboard input
                    if interactive:
                        key = self._read_key_nonblocking()
                        if key is not None:
                            # Handle filter input mode
                            if filter_mode:
                                if key == "\x1b":  # ESC - cancel filter
                                    filter_mode = False
                                    filter_input = ""
                                elif key in ("\r", "\n"):  # Enter - apply filter
                                    filter_mode = False
                                    active_filter = filter_input
                                    filter_input = ""
                                    selected_row = None
                                elif key in ("\x7f", "\b"):  # Backspace
                                    filter_input = filter_input[:-1]
                                elif len(key) == 1 and key.isprintable():
                                    filter_input += key
                                needs_refresh = True

                            # Handle kill confirmation mode
                            elif kill_confirm_agent is not None:
                                if key in ("y", "Y"):
                                    self._kill_agent(registry, kill_confirm_agent)
                                    selected_row = None
                                    kill_confirm_agent = None
                                    change_event.set()
                                    needs_refresh = True
                                elif key in ("n", "N", "\x1b"):
                                    kill_confirm_agent = None
                                    needs_refresh = True

                            # Normal mode - quit
                            elif key in ("q", "Q"):
                                break

                            # Normal mode - enter filter
                            elif key == "/":
                                filter_mode = True
                                filter_input = active_filter
                                needs_refresh = True

                            # Normal mode - ESC clears filter or selection
                            elif key == "\x1b":
                                if active_filter:
                                    active_filter = ""
                                elif selected_row is not None:
                                    selected_row = None
                                needs_refresh = True

                            # Normal mode - number keys for selection
                            elif key.isdigit() and key != "0":
                                selected_row = int(key)
                                needs_refresh = True

                            # Normal mode - arrow navigation
                            elif key == "UP" and current_agents:
                                if selected_row is None:
                                    selected_row = len(current_agents)
                                elif selected_row > 1:
                                    selected_row -= 1
                                needs_refresh = True

                            elif key == "DOWN" and current_agents:
                                if selected_row is None:
                                    selected_row = 1
                                elif selected_row < len(current_agents):
                                    selected_row += 1
                                needs_refresh = True

                            # Normal mode - terminal jump (requires selection)
                            elif (
                                key in ("\r", "\n", "j", "J")
                                and jump_available
                                and selected_row is not None
                                and 1 <= selected_row <= len(current_agents)
                            ):
                                jump_to_terminal(current_agents[selected_row - 1])

                            # Normal mode - kill confirmation (requires selection)
                            elif (
                                key in ("k", "K")
                                and selected_row is not None
                                and 1 <= selected_row <= len(current_agents)
                            ):
                                kill_confirm_agent = current_agents[selected_row - 1]
                                needs_refresh = True

                    # Fallback polling: trigger update every poll_interval seconds
                    current_time = self._time.time()
                    if current_time - last_poll_time >= poll_interval:
                        change_event.set()
                        last_poll_time = current_time

                    # Update display when file changes or selection changes
                    if change_event.is_set() or needs_refresh:
                        change_event.clear()
                        needs_refresh = False

                        # Use active_filter for filtering
                        current_filter = active_filter if active_filter else None
                        agents, stale_locks, show_file_safety = self._get_agent_data(
                            registry, current_filter
                        )

                        # Update current_agents for terminal jump
                        current_agents = agents

                        # Validate selected_row against current agent count
                        if selected_row is not None and selected_row > len(agents):
                            selected_row = None

                        # Clear kill confirmation if agent no longer exists
                        if kill_confirm_agent:
                            agent_ids = [a.get("agent_id") for a in agents]
                            if kill_confirm_agent.get("agent_id") not in agent_ids:
                                kill_confirm_agent = None

                        timestamp = self._time.strftime("%Y-%m-%d %H:%M:%S")

                        # Show filter_input while in filter mode, active_filter otherwise
                        display_filter = filter_input if filter_mode else active_filter

                        display = renderer.render_display(
                            agents=agents,
                            version=pkg_version,
                            timestamp=timestamp,
                            show_file_safety=show_file_safety,
                            stale_locks=stale_locks,
                            interactive=interactive,
                            selected_row=selected_row,
                            jump_available=jump_available,
                            kill_confirm_agent=kill_confirm_agent,
                            filter_mode=filter_mode,
                            filter_text=display_filter,
                        )

                        live.update(display, refresh=True)

                    # Small sleep to prevent CPU spinning
                    self._time.sleep(0.05)
        except KeyboardInterrupt:
            pass
        finally:
            if observer:
                observer.stop()
                observer.join()
            self._restore_terminal(saved_terminal)
            console.print("\n[dim]Exiting...[/dim]")
            raise SystemExit(0)

    def run(self, args: argparse.Namespace) -> None:
        """List running agents with Rich TUI."""
        registry = self._registry_factory()

        # Check if stdout is a TTY
        if not sys.stdout.isatty():
            # Non-interactive mode: single output
            agents, _, _ = self._get_agent_data(registry)
            if not agents:
                lines = ["No agents running.", "", "Port ranges:"]
                for agent_type, (start, end) in sorted(PORT_RANGES.items()):
                    lines.append(f"  {agent_type}: {start}-{end}")
                self._print("\n".join(lines))
            else:
                # Simple table output with NAME, ROLE, ID, CURRENT columns
                header = (
                    f"{'TYPE':<10} {'NAME':<16} {'ROLE':<16} {'ID':<24} "
                    f"{'PORT':<8} {'STATUS':<12} {'CURRENT':<35} {'PID':<8} {'ENDPOINT'}"
                )
                self._print(header)
                self._print("-" * len(header))
                for agent in agents:
                    name = agent.get("name") or "-"
                    role = agent.get("role") or "-"
                    agent_id = agent.get("agent_id", "-")
                    current = agent.get("current_task_preview") or "-"
                    self._print(
                        f"{agent['agent_type']:<10} "
                        f"{name:<16} "
                        f"{role:<16} "
                        f"{agent_id:<24} "
                        f"{agent['port']:<8} "
                        f"{agent['status']:<12} "
                        f"{current:<35} "
                        f"{agent['pid']:<8} "
                        f"{agent['endpoint']}"
                    )
            return

        # Get version for display
        try:
            from importlib.metadata import version

            pkg_version = version("synapse-a2a")
        except Exception:
            pkg_version = "unknown"

        from rich.console import Console

        console = Console()
        self._run_rich_tui(registry, console, pkg_version)
