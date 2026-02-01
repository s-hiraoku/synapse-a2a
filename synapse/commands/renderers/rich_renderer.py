"""Rich TUI renderer for synapse list."""

from __future__ import annotations

from typing import Any

from rich import box
from rich.console import Console, Group, RenderableType
from rich.markup import escape as rich_escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from synapse.port_manager import PORT_RANGES
from synapse.status import STATUS_STYLES


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

    def build_table(
        self,
        agents: list[dict[str, Any]],
        show_file_safety: bool = False,
        show_row_numbers: bool = False,
        selected_row: int | None = None,
    ) -> Table:
        """Build a Rich table from agent data.

        Args:
            agents: List of agent dictionaries with keys:
                - agent_type, port, status, pid, working_dir, endpoint
                - transport (always included)
                - editing_file (optional, for file safety)
            show_file_safety: If True, include EDITING FILE column.
            show_row_numbers: If True, add row numbers for selection.
            selected_row: If set, highlight this row (1-indexed).

        Returns:
            Rich Table object.
        """
        if not agents:
            return self._build_empty_table()

        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")

        # Add row number column if enabled
        if show_row_numbers:
            table.add_column("#", justify="right", style="dim", width=2)

        # Add columns in order with fixed widths to prevent table resizing
        table.add_column("TYPE", style="cyan", width=12)
        table.add_column("NAME", style="magenta", min_width=10, max_width=16)
        table.add_column("ID", style="dim", min_width=20, max_width=24)
        table.add_column("ROLE", min_width=10, max_width=20)
        table.add_column("STATUS", min_width=12)
        table.add_column("CURRENT", min_width=20, max_width=35)
        table.add_column("TRANSPORT", min_width=10)
        table.add_column("WORKING_DIR", min_width=20, max_width=30)

        if show_file_safety:
            table.add_column("EDITING FILE", min_width=15, max_width=25)

        # Add rows
        for idx, agent in enumerate(agents, start=1):
            row: list[str | Text] = []

            # Add row number if enabled
            if show_row_numbers:
                num_style = "bold yellow" if idx == selected_row else "dim"
                row.append(Text(str(idx), style=num_style))

            # Determine row style based on selection
            is_selected = idx == selected_row
            type_style = "bold cyan" if is_selected else "cyan"

            row.extend(
                [
                    Text(agent.get("agent_type", "unknown"), style=type_style),
                    agent.get("name") or "-",
                    agent.get("agent_id") or "-",
                    agent.get("role") or "-",
                    self._format_status(agent.get("status", "-")),
                    agent.get("current_task_preview") or "-",
                    agent.get("transport", "-"),
                    agent.get("working_dir", "-"),
                ]
            )

            if show_file_safety:
                row.append(agent.get("editing_file", "-"))

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
            ("Role", agent.get("role") or "-"),
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
            footer.append(":select ", style="dim")

            # Show action hints when row is selected
            if has_selection:
                if jump_available:
                    footer.append("Enter/j", style="bold green")
                    footer.append(":jump ", style="dim")
                footer.append("k", style="bold red")
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
    ) -> RenderableType:
        """Build the complete display.

        Args:
            agents: List of agent dictionaries.
            version: Package version string.
            timestamp: Current timestamp string.
            show_file_safety: If True, include EDITING FILE column.
            stale_locks: List of stale lock dictionaries (optional).
            interactive: If True, enable number key selection.
            selected_row: Currently selected row (1-indexed), or None.
            jump_available: If True, terminal jump feature is available.
            kill_confirm_agent: If set, show kill confirmation for this agent.
            filter_mode: If True, show filter input mode.
            filter_text: Current filter text.

        Returns:
            Rich renderable for the complete display.
        """
        table = self.build_table(
            agents,
            show_file_safety=show_file_safety,
            show_row_numbers=interactive,
            selected_row=selected_row,
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
