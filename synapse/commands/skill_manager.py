"""Skill Manager command implementation for Synapse CLI.

Provides TUI and non-interactive commands for browsing, deleting,
moving, deploying, importing, and creating skills across scopes.

Commands:
    synapse skills                              Interactive TUI
    synapse skills list [--scope SCOPE]         List skills
    synapse skills show <name>                  Show skill details
    synapse skills delete <name> [--force]      Delete a skill
    synapse skills move <name> --to SCOPE       Move a skill
    synapse skills deploy <name> [--agent ...]  Deploy to agent dirs
    synapse skills import <name>                Import to central store
    synapse skills create                       Create new skill
    synapse skills add <repo>                   Add from repository
    synapse skills set list                     List skill sets
    synapse skills set show <name>              Show skill set details
"""

from __future__ import annotations

from pathlib import Path

from synapse.skills import (
    AGENT_SKILL_DIRS,
    SkillInfo,
    SkillScope,
    create_skill,
    create_skill_set,
    delete_skill,
    delete_skill_set,
    deploy_skill,
    discover_skills,
    edit_skill_set,
    import_skill,
    load_skill_sets,
    move_skill,
)

_SCOPE_LABELS = {
    SkillScope.SYNAPSE: "Synapse (~/.synapse)",
    SkillScope.USER: "User (~)",
    SkillScope.PROJECT: "Project (.)",
    SkillScope.PLUGIN: "Plugin",
}

# Manage Skills list uses descriptive scope headers
_SCOPE_HEADERS = {
    SkillScope.SYNAPSE: "Synapse — Central Store (~/.synapse/skills/)",
    SkillScope.USER: "User — Agent directories in home (~/.claude/skills/ etc.)",
    SkillScope.PROJECT: "Project — Agent directories in project (.claude/skills/ etc.)",
    SkillScope.PLUGIN: "Plugin — Bundled read-only (plugins/synapse-a2a/skills/)",
}


# ──────────────────────────────────────────────────────────
# Non-interactive subcommands
# ──────────────────────────────────────────────────────────


def cmd_skills_list(
    user_dir: Path | None = None,
    project_dir: Path | None = None,
    synapse_dir: Path | None = None,
    scope_filter: str | None = None,
) -> None:
    """List all discovered skills."""
    user_dir = user_dir or Path.home()
    project_dir = project_dir or Path.cwd()
    skills = discover_skills(
        project_dir=project_dir, user_dir=user_dir, synapse_dir=synapse_dir
    )

    if scope_filter:
        try:
            target = SkillScope(scope_filter)
        except ValueError:
            print(f"Unknown scope: {scope_filter}")
            return
        skills = [s for s in skills if s.scope == target]

    if not skills:
        print("No skills found.")
        return

    current_scope: SkillScope | None = None
    for skill in skills:
        if skill.scope != current_scope:
            current_scope = skill.scope
            print(f"\n--- {_SCOPE_LABELS[current_scope]} ---")
        dirs_str = ", ".join(skill.agent_dirs)
        desc = skill.description[:60] if skill.description else ""
        print(f"  {skill.name:<25} {desc}")
        print(f"    Dirs: {dirs_str}")


def cmd_skills_show(
    name: str,
    user_dir: Path | None = None,
    project_dir: Path | None = None,
    synapse_dir: Path | None = None,
    scope: str | None = None,
) -> None:
    """Show details of a specific skill."""
    user_dir = user_dir or Path.home()
    project_dir = project_dir or Path.cwd()
    skills = discover_skills(
        project_dir=project_dir, user_dir=user_dir, synapse_dir=synapse_dir
    )

    matches = [s for s in skills if s.name == name]
    if scope:
        try:
            target = SkillScope(scope)
            matches = [s for s in matches if s.scope == target]
        except ValueError:
            pass

    if not matches:
        print(f"Skill '{name}' not found.")
        return

    for skill in matches:
        print(f"  Name:        {skill.name}")
        print(f"  Scope:       {_SCOPE_LABELS[skill.scope]}")
        print(f"  Path:        {skill.path}")
        print(f"  Agent Dirs:  {', '.join(skill.agent_dirs)}")
        print(f"  Description: {skill.description}")
        if len(matches) > 1:
            print()


def cmd_skills_delete(
    name: str,
    user_dir: Path | None = None,
    project_dir: Path | None = None,
    synapse_dir: Path | None = None,
    scope: str | None = None,
    force: bool = False,
) -> bool:
    """Delete a skill.

    Returns:
        True if deleted, False otherwise.
    """
    user_dir = user_dir or Path.home()
    project_dir = project_dir or Path.cwd()
    skills = discover_skills(
        project_dir=project_dir, user_dir=user_dir, synapse_dir=synapse_dir
    )

    matches = [s for s in skills if s.name == name]
    if scope:
        try:
            target = SkillScope(scope)
            matches = [s for s in matches if s.scope == target]
        except ValueError:
            pass

    if not matches:
        print(f"Skill '{name}' not found.")
        return False

    skill = matches[0]

    if skill.scope == SkillScope.PLUGIN:
        print(f"Cannot delete plugin skill '{name}' (read-only).")
        return False

    base_dir = _get_base_dir_for_scope(skill.scope, user_dir, project_dir, synapse_dir)

    if not force and not _confirm_action(
        f"Delete skill '{name}' from {_SCOPE_LABELS[skill.scope]}?"
    ):
        return False

    deleted = delete_skill(skill, base_dir)
    if deleted:
        print(f"Deleted '{name}' ({len(deleted)} directories removed).")
        return True

    return False


def _get_base_dir_for_scope(
    scope: SkillScope,
    user_dir: Path,
    project_dir: Path,
    synapse_dir: Path | None,
) -> Path:
    """Get the base directory for a given scope."""
    if scope == SkillScope.SYNAPSE:
        return synapse_dir or (Path.home() / ".synapse")
    if scope == SkillScope.USER:
        return user_dir
    return project_dir


def _confirm_action(prompt: str) -> bool:
    """Prompt for confirmation. Returns True if confirmed."""
    try:
        confirm = input(f"{prompt} [y/N]: ").strip().lower()
        return confirm == "y"
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return False


def cmd_skills_move(
    name: str,
    target_scope: str,
    user_dir: Path | None = None,
    project_dir: Path | None = None,
) -> bool:
    """Move a skill to a different scope.

    Returns:
        True if moved, False otherwise.
    """
    user_dir = user_dir or Path.home()
    project_dir = project_dir or Path.cwd()
    skills = discover_skills(project_dir=project_dir, user_dir=user_dir)

    matches = [s for s in skills if s.name == name]
    if not matches:
        print(f"Skill '{name}' not found.")
        return False

    try:
        scope = SkillScope(target_scope)
    except ValueError:
        print(f"Unknown scope: {target_scope}")
        return False

    try:
        copied, removed = move_skill(
            matches[0],
            target_scope=scope,
            user_dir=user_dir,
            project_dir=project_dir,
        )
        print(f"Moved '{name}': {len(copied)} copied, {len(removed)} removed.")
        return True
    except ValueError as e:
        print(f"Cannot move: {e}")
        return False


def cmd_skills_deploy(
    name: str,
    agents: list[str],
    scope: str,
    user_dir: Path | None = None,
    project_dir: Path | None = None,
    synapse_dir: Path | None = None,
) -> bool:
    """Deploy a skill to agent directories.

    Returns:
        True if at least one skill was deployed.
    """
    user_dir = user_dir or Path.home()
    project_dir = project_dir or Path.cwd()
    skills = discover_skills(
        project_dir=project_dir, user_dir=user_dir, synapse_dir=synapse_dir
    )

    matches = [s for s in skills if s.name == name]
    if not matches:
        print(f"Skill '{name}' not found.")
        return False

    skill = matches[0]
    result = deploy_skill(
        skill,
        agent_types=agents,
        deploy_scope=scope,
        user_dir=user_dir,
        project_dir=project_dir,
    )

    for msg in result.messages:
        print(f"  {msg}")

    return len(result.copied) > 0


def cmd_skills_import(
    name: str,
    from_scope: str | None = None,
    user_dir: Path | None = None,
    project_dir: Path | None = None,
    synapse_dir: Path | None = None,
) -> bool:
    """Import a skill to the central synapse store.

    Returns:
        True if imported.
    """
    user_dir = user_dir or Path.home()
    project_dir = project_dir or Path.cwd()
    synapse_dir = synapse_dir or (Path.home() / ".synapse")
    skills = discover_skills(
        project_dir=project_dir, user_dir=user_dir, synapse_dir=synapse_dir
    )

    matches = [s for s in skills if s.name == name]
    if from_scope:
        try:
            target = SkillScope(from_scope)
            matches = [s for s in matches if s.scope == target]
        except ValueError:
            pass

    if not matches:
        print(f"Skill '{name}' not found.")
        return False

    skill = matches[0]
    result = import_skill(skill, synapse_dir=synapse_dir)
    print(f"  {result.message}")
    return result.imported


def cmd_skills_create(
    name: str | None = None,
    synapse_dir: Path | None = None,
) -> bool:
    """Create a new skill in the central synapse store.

    Returns:
        True if created.
    """
    synapse_dir = synapse_dir or (Path.home() / ".synapse")

    if name is None:
        try:
            name = input("Skill name: ").strip()
            if not name:
                print("Cancelled.")
                return False
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return False

    result = create_skill(name, synapse_dir=synapse_dir)
    if result is None:
        print(f"Skill '{name}' already exists.")
        return False

    print(f"Created skill '{name}' at {result}")
    return True


def cmd_skills_create_guided() -> None:
    """Show guidance for creating a skill with anthropic-skill-creator."""
    _print_create_guidance()


def _print_create_guidance(indent: str = "") -> None:
    """Print guidance for creating a skill with anthropic-skill-creator."""
    from rich.console import Console
    from rich.text import Text

    console = Console()
    i = indent

    console.print()

    desc = Text(f"{i}Create a new skill using the ")
    desc.append("/anthropic-skill-creator", style="bold cyan")
    desc.append(" skill.\n")
    desc.append(
        f"{i}The skill guides: use-case definition → trigger design → workflow authoring."
    )
    console.print(desc)

    console.print()

    # Step 1
    s1 = Text(f"{i}  ")
    s1.append("Step 1:", style="bold green")
    s1.append(" Deploy anthropic-skill-creator to the agent")
    console.print(s1)
    cmd1 = Text(f"{i}  ")
    cmd1.append(
        "$ synapse skills deploy anthropic-skill-creator --agent claude --scope user",
        style="bold yellow",
    )
    console.print(cmd1)

    console.print()

    # Step 2
    s2 = Text(f"{i}  ")
    s2.append("Step 2:", style="bold green")
    s2.append(" Start the agent and invoke the skill")
    console.print(s2)
    cmd2 = Text(f"{i}  ")
    cmd2.append("$ synapse claude", style="bold yellow")
    console.print(cmd2)
    cmd2b = Text(f"{i}  ")
    cmd2b.append(
        "> /anthropic-skill-creator Create a new skill in ~/.synapse/skills/",
        style="bold cyan",
    )
    console.print(cmd2b)

    console.print()

    # Step 3
    s3 = Text(f"{i}  ")
    s3.append("Step 3:", style="bold green")
    s3.append(" Deploy the finished skill to agent directories")
    console.print(s3)
    cmd3 = Text(f"{i}  ")
    cmd3.append(
        "$ synapse skills deploy <skill-name> --agent claude --scope user",
        style="bold yellow",
    )
    console.print(cmd3)

    console.print()


def cmd_skills_set_list(sets_path: Path | None = None) -> None:
    """List all defined skill sets."""
    sets = load_skill_sets(sets_path)
    if not sets:
        print("No skill sets defined.")
        print("  Create one with: synapse skills set create")
        return

    print("Skill Sets:")
    print("-" * 60)
    for name, ssd in sorted(sets.items()):
        skills_str = ", ".join(ssd.skills) if ssd.skills else "(empty)"
        print(f"  {name}")
        print(f"    Description: {ssd.description or '(none)'}")
        print(f"    Skills: {skills_str}")
        print()


def cmd_skills_set_show(name: str, sets_path: Path | None = None) -> None:
    """Show details of a specific skill set."""
    sets = load_skill_sets(sets_path)
    if name not in sets:
        print(f"Skill set '{name}' not found.")
        return

    ssd = sets[name]
    print(f"Name:        {ssd.name}")
    print(f"Description: {ssd.description or '(none)'}")
    print(f"Skills ({len(ssd.skills)}):")
    for s in ssd.skills:
        print(f"  - {s}")


# ──────────────────────────────────────────────────────────
# Interactive TUI
# ──────────────────────────────────────────────────────────


class SkillManagerCommand:
    """Interactive TUI for browsing and managing skills."""

    def __init__(
        self,
        user_dir: Path | None = None,
        project_dir: Path | None = None,
        synapse_dir: Path | None = None,
    ) -> None:
        self._user_dir = user_dir or Path.home()
        self._project_dir = project_dir or Path.cwd()
        self._synapse_dir = synapse_dir or (Path.home() / ".synapse")

    # ── Shared menu helper ───────────────────────────────────

    def _show_menu(self, items: list[str], title: str) -> int | None:
        """Display a *simple_term_menu* menu with unified Synapse styles.

        Returns the selected index, or ``None`` on ESC / Ctrl-C.
        """
        from simple_term_menu import TerminalMenu

        from synapse.styles import TERM_MENU_STYLES

        menu = TerminalMenu(items, title=title, **TERM_MENU_STYLES)
        result = menu.show()
        return int(result) if result is not None else None

    # ── Run loop ─────────────────────────────────────────────

    def run(self) -> None:
        """Run the interactive skill manager."""
        try:
            from simple_term_menu import TerminalMenu  # noqa: F401
        except ImportError:
            print("Error: simple_term_menu is required for interactive mode.")
            print("Install it: pip install simple-term-menu")
            return

        while True:
            choice = self._top_menu()
            if choice is None or choice == "exit":
                break
            elif choice == "manage":
                self._manage_skills()
            elif choice == "sets":
                self._skill_set_menu()
            elif choice == "install":
                self._install_menu()
            elif choice == "deploy":
                self._deploy_flow()
            elif choice == "create":
                self._create_guided_flow()

    def _top_menu(self) -> str | None:
        """Show top-level menu."""
        from synapse.styles import build_numbered_items

        skills = discover_skills(
            project_dir=self._project_dir,
            user_dir=self._user_dir,
            synapse_dir=self._synapse_dir,
        )

        header = (
            f"\n  SYNAPSE SKILL MANAGER\n"
            f"  Found {len(skills)} skills  |  Central store: ~/.synapse/skills/\n"
        )

        items = build_numbered_items(
            [
                "Manage Skills        Browse, delete, move, deploy",
                "Skill Sets           Create and manage named groups",
                "Install Skill        Import or create in ~/.synapse/skills",
                "Deploy Skills        Push from ~/.synapse/skills to agents",
                "Create Skill         Scaffold with Anthropic methodology",
            ],
            [("q", "Exit")],
        )

        choice = self._show_menu(items, header)
        if choice is None:
            return None
        mapping = ["manage", "sets", "install", "deploy", "create"]
        if choice < len(mapping):
            return mapping[choice]
        # separator or [q] Exit
        return "exit"

    def _manage_skills(self) -> None:
        """Browse and manage skills (existing behavior + synapse scope)."""
        while True:
            skills = discover_skills(
                project_dir=self._project_dir,
                user_dir=self._user_dir,
                synapse_dir=self._synapse_dir,
            )
            if not skills:
                print("No skills found.")
                return

            choice = self._skills_menu(skills)
            if choice is None:
                break
            if choice == "quit":
                break
            if isinstance(choice, int) and 0 <= choice < len(skills):
                self._skill_detail(skills[choice])

    def _skills_menu(self, skills: list[SkillInfo]) -> int | str | None:
        """Show skills list menu with scope headers and numbered items."""
        from synapse.styles import MENU_SEPARATOR

        header = (
            f"\n  SYNAPSE SKILL MANAGER\n"
            f"  Found {len(skills)} skills  |  Central store: ~/.synapse/skills/\n"
        )

        # Build skill labels grouped by scope
        labels: list[str] = []
        skill_indices: list[int] = []
        current_scope: SkillScope | None = None

        for i, skill in enumerate(skills):
            if skill.scope != current_scope:
                current_scope = skill.scope
                # Scope header line (non-selectable)
                labels.append(f"--- {_SCOPE_HEADERS[current_scope]} ---")
                skill_indices.append(-1)

            desc = skill.description[:50] if skill.description else ""
            labels.append(f"  {skill.name:<25} {desc}")
            skill_indices.append(i)

        # Number only selectable skill rows
        numbered: list[str] = []
        num = 1
        for label, idx in zip(labels, skill_indices, strict=True):
            if idx == -1:
                # Scope header — pass through unnumbered
                numbered.append(label)
            else:
                width = len(str(len(skills)))
                numbered.append(f"[{num:>{width}}] {label.strip()}")
                num += 1

        numbered.append(MENU_SEPARATOR)
        skill_indices.append(-1)
        numbered.append("[q] Quit")
        skill_indices.append(-2)

        choice = self._show_menu(numbered, header)
        if choice is None:
            return None

        idx = skill_indices[int(choice)]
        if idx == -2:
            return "quit"
        if idx == -1:
            return None  # Non-selectable item
        return idx

    def _skill_detail(self, skill: SkillInfo) -> None:
        """Show skill detail view with actions."""
        from synapse.styles import build_numbered_items

        scope_label = _SCOPE_LABELS[skill.scope]
        header = (
            f"\n  Name:        {skill.name}\n"
            f"  Scope:       {scope_label}\n"
            f"  Path:        {skill.path}\n"
            f"  Agent Dirs:  {', '.join(skill.agent_dirs)}\n"
            f"  Description: {skill.description}\n"
        )

        # Build action labels (variable depending on scope)
        action_labels: list[str] = []
        action_keys: list[str] = []  # action identifier per label

        if skill.scope != SkillScope.PLUGIN:
            action_labels.append("Delete skill")
            action_keys.append("delete")
            if skill.scope == SkillScope.USER:
                action_labels.append("Move to Project scope")
                action_keys.append("move")
            elif skill.scope == SkillScope.PROJECT:
                action_labels.append("Move to User scope")
                action_keys.append("move")
        if skill.scope != SkillScope.SYNAPSE:
            action_labels.append("Import to ~/.synapse/skills")
            action_keys.append("import")
        if skill.scope == SkillScope.SYNAPSE:
            action_labels.append("Deploy to agent directories")
            action_keys.append("deploy")

        items = build_numbered_items(action_labels, [("0", "Back")])

        result = self._show_menu(items, header)
        if result is None or result >= len(action_labels):
            return

        action = action_keys[result]
        if action == "delete":
            self._confirm_delete(skill)
        elif action == "move":
            target = (
                SkillScope.PROJECT
                if skill.scope == SkillScope.USER
                else SkillScope.USER
            )
            self._confirm_move(skill, target)
        elif action == "import":
            self._do_import(skill)
        elif action == "deploy":
            self._do_deploy(skill)

    def _confirm_delete(self, skill: SkillInfo) -> None:
        """Confirm and delete a skill."""
        base_dir = _get_base_dir_for_scope(
            skill.scope,
            self._user_dir,
            self._project_dir,
            self._synapse_dir,
        )

        if _confirm_action(
            f"\n  Delete '{skill.name}' from {_SCOPE_LABELS[skill.scope]}?"
        ):
            deleted = delete_skill(skill, base_dir)
            print(f"  Deleted ({len(deleted)} directories).")
        else:
            print("  Cancelled.")

        input("  Press Enter to continue...")

    def _confirm_move(self, skill: SkillInfo, target: SkillScope) -> None:
        """Confirm and move a skill."""
        if not _confirm_action(f"\n  Move '{skill.name}' to {_SCOPE_LABELS[target]}?"):
            print("  Cancelled.")
            input("  Press Enter to continue...")
            return

        try:
            copied, removed = move_skill(
                skill,
                target_scope=target,
                user_dir=self._user_dir,
                project_dir=self._project_dir,
            )
            print(f"  Moved ({len(copied)} copied, {len(removed)} removed).")
        except ValueError as e:
            print(f"\n  Error: {e}")

        input("  Press Enter to continue...")

    def _do_import(self, skill: SkillInfo) -> None:
        """Import a skill to central store."""
        result = import_skill(skill, synapse_dir=self._synapse_dir)
        print(f"\n  {result.message}")
        input("  Press Enter to continue...")

    def _do_deploy(self, skill: SkillInfo) -> None:
        """Deploy a skill to agent directories."""
        try:
            agents = self._prompt_for_agents()
            scope = input("  Deploy scope (user/project) [user]: ").strip() or "user"

            result = deploy_skill(
                skill,
                agent_types=agents,
                deploy_scope=scope,
                user_dir=self._user_dir,
                project_dir=self._project_dir,
            )
            for msg in result.messages:
                print(f"  {msg}")
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")

        input("  Press Enter to continue...")

    def _prompt_for_agents(self) -> list[str]:
        """Prompt user for target agents."""
        agents_str = input(
            "\n  Target agents (comma-separated, e.g. claude,codex) [all]: "
        ).strip()

        if not agents_str or agents_str == "all":
            return list(AGENT_SKILL_DIRS.keys())

        return [a.strip() for a in agents_str.split(",") if a.strip()]

    def _install_menu(self) -> None:
        """Install skill submenu."""
        from synapse.styles import build_numbered_items

        items = build_numbered_items(
            [
                "Import from agent directories",
                "Create new skill",
            ],
            [("0", "Back")],
        )

        result = self._show_menu(items, "\n  Install Skill\n")
        if result is None or result >= 2:
            return
        if result == 0:
            self._import_flow()
        elif result == 1:
            self._create_flow()

    def _import_flow(self) -> None:
        """Interactive import flow."""
        from synapse.styles import build_numbered_items

        skills = discover_skills(
            project_dir=self._project_dir,
            user_dir=self._user_dir,
        )
        importable = [
            s for s in skills if s.scope in (SkillScope.USER, SkillScope.PROJECT)
        ]
        if not importable:
            print("\n  No importable skills found.")
            input("  Press Enter to continue...")
            return

        labels = [f"{s.name} ({_SCOPE_LABELS[s.scope]})" for s in importable]
        items = build_numbered_items(labels, [("0", "Cancel")])

        idx = self._show_menu(items, "\n  Select skill to import:\n")
        if idx is None or idx >= len(importable):
            return

        result = import_skill(importable[idx], synapse_dir=self._synapse_dir)
        print(f"\n  {result.message}")
        input("  Press Enter to continue...")

    def _create_flow(self) -> None:
        """Interactive skill creation flow."""
        try:
            name = input("\n  Skill name: ").strip()
            if not name:
                print("  Cancelled.")
                return
            result = create_skill(name, synapse_dir=self._synapse_dir)
            if result is None:
                print(f"  Skill '{name}' already exists.")
            else:
                print(f"  Created skill '{name}' at {result}")
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
        input("  Press Enter to continue...")

    def _create_guided_flow(self) -> None:
        """Show guidance for creating a skill with anthropic-skill-creator."""
        _print_create_guidance(indent="  ")
        input("  Press Enter to continue...")

    def _deploy_flow(self) -> None:
        """Interactive deploy flow."""
        from synapse.styles import build_numbered_items

        synapse_skills = discover_skills(synapse_dir=self._synapse_dir)
        synapse_only = [s for s in synapse_skills if s.scope == SkillScope.SYNAPSE]
        if not synapse_only:
            print("\n  No skills in ~/.synapse/skills/ to deploy.")
            input("  Press Enter to continue...")
            return

        labels = [f"{s.name} - {s.description[:40]}" for s in synapse_only]
        items = build_numbered_items(labels, [("0", "Cancel")])

        idx = self._show_menu(items, "\n  Select skill to deploy:\n")
        if idx is None or idx >= len(synapse_only):
            return

        self._do_deploy(synapse_only[idx])

    # ──────────────────────────────────────────────────────────
    # Skill Set TUI (absorbed from skill_sets.py)
    # ──────────────────────────────────────────────────────────

    def _skill_set_menu(self) -> None:
        """Skill set management menu."""
        while True:
            choice = self._skill_set_main_menu()
            if choice is None or choice == "exit":
                break
            elif choice == "list":
                cmd_skills_set_list()
                input("\nPress Enter to continue...")
            elif choice == "create":
                self._interactive_create_set()
            elif choice == "edit":
                self._interactive_edit_set()
            elif choice == "delete":
                self._interactive_delete_set()

    def _skill_set_main_menu(self) -> str | None:
        """Show skill set main menu."""
        try:
            from simple_term_menu import TerminalMenu  # noqa: F401
        except ImportError:
            print("Error: simple_term_menu is required for interactive mode.")
            return None

        from synapse.styles import build_numbered_items

        items = build_numbered_items(
            [
                "List skill sets",
                "Create new skill set",
                "Edit skill set",
                "Delete skill set",
            ],
            [("q", "Exit")],
        )

        choice = self._show_menu(items, "\n  SYNAPSE SKILL SETS\n")
        if choice is None:
            return None
        mapping = ["list", "create", "edit", "delete"]
        if choice < len(mapping):
            return mapping[choice]
        return "exit"

    def _interactive_create_set(self) -> None:
        """Interactive skill set creation flow."""
        print("\n  Create New Skill Set")
        print("  " + "=" * 40)
        try:
            name = input("  Name: ").strip()
            if not name:
                print("  Cancelled.")
                return
            desc = input("  Description: ").strip()

            all_skills = discover_skills(
                project_dir=self._project_dir,
                user_dir=self._user_dir,
                synapse_dir=self._synapse_dir,
            )
            if not all_skills:
                print("  No skills found to add.")
                return

            print(f"\n  Available skills ({len(all_skills)}):")
            for i, s in enumerate(all_skills, 1):
                scope_label = s.scope.value[0].upper()
                print(f"  [{i}] [{scope_label}] {s.name} - {s.description[:50]}")

            selection = input("\n  Select skills (comma-separated numbers): ").strip()
            if not selection:
                print("  Cancelled.")
                return

            selected_skills: list[str] = []
            for part in selection.split(","):
                part = part.strip()
                if part.isdigit():
                    idx = int(part) - 1
                    if 0 <= idx < len(all_skills):
                        selected_skills.append(all_skills[idx].name)

            if not selected_skills:
                print("  No valid skills selected.")
                return

            create_skill_set(name, desc, selected_skills)
            print(f"\n  Created skill set '{name}' with {len(selected_skills)} skills.")

        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")

    def _select_skill_set(self, action: str) -> str | None:
        """Show set selection menu. Returns set name or None."""
        from synapse.styles import build_numbered_items

        sets = load_skill_sets()
        if not sets:
            print(f"\n  No skill sets to {action}.")
            input("  Press Enter to continue...")
            return None

        try:
            from simple_term_menu import TerminalMenu  # noqa: F401
        except ImportError:
            return None

        labels = [f"{name} - {ssd.description}" for name, ssd in sorted(sets.items())]
        items = build_numbered_items(labels, [("0", "Cancel")])

        choice = self._show_menu(items, f"\n  Select skill set to {action}:\n")
        if choice is None or choice >= len(sets):
            return None
        return sorted(sets.keys())[choice]

    def _interactive_edit_set(self) -> None:
        """Interactive edit flow."""
        name = self._select_skill_set("edit")
        if not name:
            return

        sets = load_skill_sets()
        ssd = sets[name]

        print(f"\n  Editing: {name}")
        print(f"  Current description: {ssd.description}")
        print(f"  Current skills: {', '.join(ssd.skills)}")
        print()

        try:
            new_desc = input(f"  New description [{ssd.description}]: ").strip()
            new_skills_str = input(
                f"  New skills (comma-separated) [{', '.join(ssd.skills)}]: "
            ).strip()

            edit_skill_set(
                name,
                description=new_desc if new_desc else None,
                skills=[s.strip() for s in new_skills_str.split(",") if s.strip()]
                if new_skills_str
                else None,
            )
            print(f"\n  Updated skill set '{name}'.")
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")

    def _interactive_delete_set(self) -> None:
        """Interactive delete flow."""
        name = self._select_skill_set("delete")
        if not name:
            return

        if _confirm_action(f"\n  Delete skill set '{name}'?"):
            delete_skill_set(name)
            print(f"  Deleted skill set '{name}'.")
        else:
            print("  Cancelled.")
