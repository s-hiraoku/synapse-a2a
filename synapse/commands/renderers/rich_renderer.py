"""Rich TUI renderer for synapse list."""

from __future__ import annotations

import time
from typing import Any

from rich import box
from rich.console import Console, Group, RenderableType
from rich.markup import escape as rich_escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from synapse.port_manager import PORT_RANGES
from synapse.status import STATUS_STYLES
from synapse.utils import get_role_display


def format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as human-readable string.

    Args:
        seconds: Elapsed time in seconds.

    Returns:
        Formatted string like "5s", "2m 15s", or "1h 3m".
    """
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    return f"{s // 3600}h {(s % 3600) // 60}m"


class RichRenderer:
    """Rich TUI renderer for agent list display."""

    def __init__(self, console: Console | None = None) -> None:
        """Initialize renderer with optional console.

        Args:
            console: Rich console instance. If None, creates a new one.
        """
        self._console = console or Console()

    @property
    def console(self) -> Console:
        """Get the console instance."""
        return self._console

    def _format_status(self, status: str) -> Text:
        """Format status with appropriate color.

        Args:
            status: Agent status string (WAITING, PROCESSING, DONE, etc.)

        Returns:
            Rich Text object with styled status.
        """
        style = STATUS_STYLES.get(status, "")
        return Text(status, style=style)

    def _build_empty_table(self) -> Table:
        """Build a table showing 'No agents running' with port ranges.

        Returns:
            Rich Table with empty state message.
        """
        table = Table(box=box.ROUNDED, show_header=False)
        table.add_column("Message")

        table.add_row(Text("No agents running.", style="dim"))
        table.add_row("")
        table.add_row(Text("Port ranges:", style="bold"))

        for agent_type, (start, end) in sorted(PORT_RANGES.items()):
            table.add_row(f"  {agent_type}: {start}-{end}")

        return table

    # Column definitions: name -> (style, min_width, max_width, fixed_width, data_key)
    # When fixed_width is set, min_width/max_width are ignored and the column
    # gets an exact width — this prevents layout shifts when content changes.
    COLUMN_DEFS: dict[str, tuple[str | None, int, int | None, int | None, str]] = {
        "ID": ("dim", 20, 24, None, "agent_id"),
        "NAME": ("magenta", 10, 16, None, "name"),
        "TYPE": ("cyan", 8, 12, None, "agent_type"),
        "ROLE": (None, 10, 20, None, "role"),
        "SKILL_SET": ("blue", 10, 16, None, "skill_set"),
        "STATUS": (None, 12, None, 13, "status"),
        "CURRENT": (None, 20, 20, 20, "current_task_preview"),
        "TRANSPORT": (None, 10, None, 10, "transport"),
        "WORKING_DIR": (None, 20, 30, None, "working_dir"),
        "SUMMARY": (None, 20, 40, None, "summary"),
        "EDITING_FILE": (None, 15, 25, None, "editing_file"),
    }

    DEFAULT_COLUMNS = [
        "ID",
        "NAME",
        "STATUS",
        "CURRENT",
        "TRANSPORT",
        "WORKING_DIR",
        "EDITING_FILE",
    ]

    def _resolve_columns(
        self,
        candidates: list[str],
        show_file_safety: bool,
    ) -> list[str]:
        """Filter column names to valid, displayable columns.

        Args:
            candidates: Column name candidates (case-insensitive).
            show_file_safety: Whether the EDITING_FILE column is allowed.

        Returns:
            List of valid column names (uppercased).
        """
        result: list[str] = []
        for col in candidates:
            col_upper = col.upper()
            if col_upper not in self.COLUMN_DEFS:
                continue
            if col_upper == "EDITING_FILE" and not show_file_safety:
                continue
            result.append(col_upper)
        return result

    def build_table(
        self,
        agents: list[dict[str, Any]],
        show_file_safety: bool = False,
        show_row_numbers: bool = False,
        selected_row: int | None = None,
        columns: list[str] | None = None,
    ) -> Table:
        """Build a Rich table from agent data.

        Args:
            agents: List of agent dictionaries with keys:
                - agent_type, port, status, pid, working_dir, endpoint
                - transport (always included)
                - editing_file (optional, for file safety)
            show_file_safety: If True, allow EDITING_FILE column.
            show_row_numbers: If True, add row numbers for selection.
            selected_row: If set, highlight this row (1-indexed).
            columns: List of column names to display. If None or empty,
                uses DEFAULT_COLUMNS.

        Returns:
            Rich Table object.
        """
        if not agents:
            return self._build_empty_table()

        # Determine which columns to show
        display_columns = columns or self.DEFAULT_COLUMNS

        # Filter to valid columns only
        valid_columns = self._resolve_columns(display_columns, show_file_safety)

        # Fallback to defaults if no valid columns remain
        if not valid_columns:
            valid_columns = self._resolve_columns(
                self.DEFAULT_COLUMNS, show_file_safety
            )

        table = Table(
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
            padding=(0, 0),
        )

        # Add row number column if enabled
        if show_row_numbers:
            table.add_column("#", justify="right", style="dim", width=2)

        # Add configured columns
        for col_name in valid_columns:
            style, min_width, max_width, fixed_width, _ = self.COLUMN_DEFS[col_name]
            kwargs: dict[str, Any] = {}
            if fixed_width is not None:
                # Fixed width prevents layout shifts for volatile columns
                kwargs["width"] = fixed_width
                kwargs["no_wrap"] = True
                kwargs["overflow"] = "ellipsis"
            else:
                kwargs["min_width"] = min_width
                if max_width:
                    kwargs["max_width"] = max_width
            if style:
                kwargs["style"] = style
            table.add_column(col_name, **kwargs)

        # Add rows
        for idx, agent in enumerate(agents, start=1):
            row: list[str | Text] = []

            # Add row number if enabled
            if show_row_numbers:
                num_style = "bold yellow" if idx == selected_row else "dim"
                row.append(Text(str(idx), style=num_style))

            # Determine row style based on selection
            is_selected = idx == selected_row

            # Add data for each column
            for col_name in valid_columns:
                _, _, _, _, data_key = self.COLUMN_DEFS[col_name]
                if col_name == "STATUS":
                    row.append(self._format_status(agent.get(data_key, "-")))
                elif col_name == "ROLE":
                    # Show filename only for file references
                    row.append(get_role_display(agent.get(data_key)) or "-")
                elif col_name == "CURRENT":
                    preview = agent.get("current_task_preview")
                    received_at = agent.get("task_received_at")
                    if preview and isinstance(received_at, (int, float)):
                        elapsed = time.time() - received_at
                        suffix = f" ({format_elapsed(elapsed)})"
                        # Pre-truncate preview so preview + suffix fits in
                        # the fixed column width.
                        _, _, _, col_width, _ = self.COLUMN_DEFS["CURRENT"]
                        content_width = max(0, col_width or 0)
                        if content_width and len(preview) + len(suffix) > content_width:
                            max_preview = max(
                                0,
                                content_width - len(suffix) - 1,
                            )
                            preview = preview[:max_preview] + "\u2026"
                        row.append(f"{preview}{suffix}")
                    else:
                        row.append(preview or "-")
                else:
                    row.append(agent.get(data_key) or "-")

            # Highlight selected row
            row_style = "on grey23" if is_selected else None
            table.add_row(*row, style=row_style)

        return table

    def build_detail_panel(self, agent: dict[str, Any]) -> Panel:
        """Build a detail panel for the selected agent.

        Args:
            agent: Agent dictionary with full details.

        Returns:
            Rich Panel with agent details.
        """
        detail_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        detail_table.add_column("Field", style="bold cyan")
        detail_table.add_column("Value")

        # Add all fields with full values (no truncation)
        fields = [
            ("Agent ID", agent.get("agent_id", "-")),
            ("Name", agent.get("name") or "-"),
            ("Type", agent.get("agent_type", "-")),
            ("Role", get_role_display(agent.get("role")) or "-"),
            ("Skill Set", agent.get("skill_set") or "-"),
            ("Port", str(agent.get("port", "-"))),
            ("Status", agent.get("status", "-")),
            ("PID", str(agent.get("pid", "-"))),
            (
                "Working Dir",
                agent.get("working_dir_full", agent.get("working_dir", "-")),
            ),
            ("Endpoint", agent.get("endpoint", "-")),
        ]

        # Add optional fields
        if agent.get("current_task_preview"):
            fields.append(("Current Task", agent.get("current_task_preview", "-")))
        if "transport" in agent:
            fields.append(("Transport", agent.get("transport", "-")))
        if "editing_file" in agent:
            fields.append(("Editing File", agent.get("editing_file", "-")))

        for field, value in fields:
            detail_table.add_row(field, value)

        return Panel(
            detail_table,
            title="[bold]Agent Details[/bold]",
            border_style="green",
            padding=(0, 1),
        )

    def build_panel(
        self,
        table: Table,
        title: str,
        subtitle: str,
    ) -> Panel:
        """Build a panel containing the table with header/footer.

        Args:
            table: Rich Table to display.
            title: Panel title (e.g., "Synapse A2A v0.2.26").
            subtitle: Panel subtitle (e.g., "Last updated: 2026-01-18 12:00:00").

        Returns:
            Rich Panel containing the table.
        """
        return Panel(
            table,
            title=title,
            subtitle=subtitle,
            border_style="blue",
        )

    def build_footer(
        self,
        interactive: bool = False,
        agent_count: int = 0,
        jump_available: bool = False,
        has_selection: bool = False,
        kill_confirm_agent: dict[str, Any] | None = None,
        filter_mode: bool = False,
        filter_text: str = "",
    ) -> Text:
        """Build footer text with control hints.

        Args:
            interactive: If True, show number key hints for selection.
            agent_count: Number of agents (for showing valid key range).
            jump_available: If True, show terminal jump hint.
            has_selection: If True, a row is currently selected.
            kill_confirm_agent: If set, show kill confirmation for this agent.
            filter_mode: If True, show filter input mode.
            filter_text: Current filter text (shown when not empty).

        Returns:
            Rich Text with control instructions.
        """
        footer = Text()

        # Kill confirmation mode
        if kill_confirm_agent:
            agent_id = kill_confirm_agent.get("agent_id", "unknown")
            pid = kill_confirm_agent.get("pid", "-")
            footer.append("⚠ ", style="bold yellow")
            footer.append(f"Kill {agent_id} (PID: {pid})? ", style="yellow")
            footer.append("[", style="dim")
            footer.append("y", style="bold green")
            footer.append("]=Yes  [", style="dim")
            footer.append("n", style="bold red")
            footer.append("/", style="dim")
            footer.append("ESC", style="bold red")
            footer.append("]=Cancel", style="dim")
            return footer

        # Filter input mode
        if filter_mode:
            footer.append("Filter (TYPE/DIR): ", style="bold yellow")
            footer.append(rich_escape(filter_text), style="bold white")
            footer.append("▌", style="bold white blink")
            footer.append("  [", style="dim")
            footer.append("Enter", style="bold green")
            footer.append("]=Apply  [", style="dim")
            footer.append("ESC", style="bold red")
            footer.append("]=Cancel", style="dim")
            return footer

        if interactive and agent_count > 0:
            # Clamp display max to 9 since only single-digit keys are supported
            display_max = min(agent_count, 9)
            footer.append(f"1-{display_max}", style="bold cyan")
            footer.append("/", style="dim")
            footer.append("↑↓", style="bold cyan")
            footer.append("/", style="dim")
            footer.append("hjkl", style="bold cyan")
            footer.append(":select ", style="dim")

            # Show action hints when row is selected
            if has_selection:
                if jump_available:
                    footer.append("Enter", style="bold green")
                    footer.append(":jump ", style="dim")
                footer.append("K", style="bold red")
                footer.append(":kill ", style="dim")

        footer.append("/", style="bold yellow")
        footer.append(":filter ", style="dim")

        # Show ESC hint for clearing filter or selection
        if filter_text:
            footer.append("ESC", style="bold cyan")
            footer.append(":clear filter ", style="dim")
        elif has_selection:
            footer.append("ESC", style="bold cyan")
            footer.append(":clear ", style="dim")

        footer.append("q", style="bold")
        footer.append(":exit", style="dim")

        return footer

    def build_stale_locks_warning(
        self, stale_locks: list[dict[str, Any]]
    ) -> Text | None:
        """Build stale locks warning message.

        Args:
            stale_locks: List of stale lock dictionaries.

        Returns:
            Rich Text warning, or None if no stale locks.
        """
        if not stale_locks:
            return None

        count = len(stale_locks)
        warning = Text()
        warning.append(f"\nWarning: {count} stale lock(s) ", style="bold yellow")
        warning.append("from dead processes.\n", style="yellow")
        warning.append(
            "Run 'synapse file-safety cleanup-locks' to clean them up.",
            style="dim",
        )
        return warning

    def render_display(
        self,
        agents: list[dict[str, Any]],
        version: str,
        timestamp: str,
        show_file_safety: bool = False,
        stale_locks: list[dict[str, Any]] | None = None,
        interactive: bool = False,
        selected_row: int | None = None,
        jump_available: bool = False,
        kill_confirm_agent: dict[str, Any] | None = None,
        filter_mode: bool = False,
        filter_text: str = "",
        columns: list[str] | None = None,
    ) -> RenderableType:
        """Build the complete display.

        Args:
            agents: List of agent dictionaries.
            version: Package version string.
            timestamp: Current timestamp string.
            show_file_safety: If True, allow EDITING_FILE column.
            stale_locks: List of stale lock dictionaries (optional).
            interactive: If True, enable number key selection.
            selected_row: Currently selected row (1-indexed), or None.
            jump_available: If True, terminal jump feature is available.
            kill_confirm_agent: If set, show kill confirmation for this agent.
            filter_mode: If True, show filter input mode.
            filter_text: Current filter text.
            columns: List of column names to display. If None, uses defaults.

        Returns:
            Rich renderable for the complete display.
        """
        table = self.build_table(
            agents,
            show_file_safety=show_file_safety,
            show_row_numbers=interactive,
            selected_row=selected_row,
            columns=columns,
        )

        # Build title with filter indicator
        title = f"Synapse A2A v{version} - Agent List"
        if filter_text and not filter_mode:
            escaped_filter = rich_escape(filter_text)
            title += f" [bold magenta](Filter: {escaped_filter})[/bold magenta]"
        subtitle = f"Last updated: {timestamp}"

        panel = self.build_panel(table, title=title, subtitle=subtitle)

        elements: list[RenderableType] = [panel]

        # Add detail panel if an agent is selected
        if selected_row is not None and 1 <= selected_row <= len(agents):
            selected_agent = agents[selected_row - 1]
            detail_panel = self.build_detail_panel(selected_agent)
            elements.append(detail_panel)

        # Add stale locks warning if present
        warning = self.build_stale_locks_warning(stale_locks or [])
        if warning:
            elements.append(warning)

        footer = self.build_footer(
            interactive=interactive,
            agent_count=len(agents),
            jump_available=jump_available,
            has_selection=selected_row is not None,
            kill_confirm_agent=kill_confirm_agent,
            filter_mode=filter_mode,
            filter_text=filter_text,
        )
        elements.append(footer)

        return Group(*elements)

    # Keep old method for backward compatibility with tests
    def render_watch_display(
        self,
        agents: list[dict[str, Any]],
        version: str,
        interval: float,
        timestamp: str,
        show_file_safety: bool = False,
        stale_locks: list[dict[str, Any]] | None = None,
        interactive: bool = False,
        selected_row: int | None = None,
        jump_available: bool = False,
    ) -> RenderableType:
        """Build the complete display (deprecated, use render_display).

        Args:
            agents: List of agent dictionaries.
            version: Package version string.
            interval: Refresh interval in seconds (ignored).
            timestamp: Current timestamp string.
            show_file_safety: If True, include EDITING FILE column.
            stale_locks: List of stale lock dictionaries (optional).
            interactive: If True, enable number key selection.
            selected_row: Currently selected row (1-indexed), or None.
            jump_available: If True, terminal jump feature is available.

        Returns:
            Rich renderable for the complete display.
        """
        return self.render_display(
            agents=agents,
            version=version,
            timestamp=timestamp,
            show_file_safety=show_file_safety,
            stale_locks=stale_locks,
            interactive=interactive,
            selected_row=selected_row,
            jump_available=jump_available,
        )
