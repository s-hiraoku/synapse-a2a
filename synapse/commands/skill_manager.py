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

    def _top_menu(self) -> str | None:
        """Show top-level menu."""
        from simple_term_menu import TerminalMenu

        skills = discover_skills(
            project_dir=self._project_dir,
            user_dir=self._user_dir,
            synapse_dir=self._synapse_dir,
        )

        header = (
            f"\n  SYNAPSE SKILL MANAGER\n  Found {len(skills)} skills across scopes\n"
        )

        items = [
            "Manage Skills        Browse, delete, move, deploy",
            "Skill Sets           Create and manage named groups",
            "Install Skill        Import or create in ~/.synapse/skills",
            "Deploy Skills        Push from ~/.synapse/skills to agents",
            "Exit",
        ]

        menu = TerminalMenu(
            items,
            title=header,
            menu_cursor="> ",
            menu_cursor_style=("fg_yellow", "bold"),
            menu_highlight_style=("fg_yellow", "bold"),
            cycle_cursor=True,
            clear_screen=True,
        )
        choice = menu.show()
        if choice is None:
            return None
        return ["manage", "sets", "install", "deploy", "exit"][int(choice)]

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
        """Show skills list menu."""
        from simple_term_menu import TerminalMenu

        header = f"\n  SYNAPSE SKILL MANAGER\n  Found {len(skills)} skills\n"

        items: list[str] = []
        current_scope: SkillScope | None = None
        skill_indices: list[int] = []

        for i, skill in enumerate(skills):
            if skill.scope != current_scope:
                current_scope = skill.scope
                # Add scope separator (non-selectable via preview)
                items.append(f"--- {_SCOPE_LABELS[current_scope]} ---")
                skill_indices.append(-1)

            desc = skill.description[:50] if skill.description else ""
            items.append(f"  {skill.name:<25} {desc}")
            skill_indices.append(i)

        items.append("─────────────────")
        skill_indices.append(-1)
        items.append("[q] Quit")
        skill_indices.append(-2)

        menu = TerminalMenu(
            items,
            title=header,
            menu_cursor="> ",
            menu_cursor_style=("fg_yellow", "bold"),
            menu_highlight_style=("fg_yellow", "bold"),
            cycle_cursor=True,
            clear_screen=True,
        )
        choice = menu.show()
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
        from simple_term_menu import TerminalMenu

        scope_label = _SCOPE_LABELS[skill.scope]
        header = (
            f"\n  Name:        {skill.name}\n"
            f"  Scope:       {scope_label}\n"
            f"  Path:        {skill.path}\n"
            f"  Agent Dirs:  {', '.join(skill.agent_dirs)}\n"
            f"  Description: {skill.description}\n"
        )

        items = []
        if skill.scope != SkillScope.PLUGIN:
            items.append("[d] Delete skill")
            if skill.scope == SkillScope.USER:
                items.append("[m] Move to Project scope")
            elif skill.scope == SkillScope.PROJECT:
                items.append("[m] Move to User scope")
        if skill.scope != SkillScope.SYNAPSE:
            items.append("[i] Import to ~/.synapse/skills")
        if skill.scope == SkillScope.SYNAPSE:
            items.append("[p] Deploy to agent directories")
        items.append("[0] Back")

        menu = TerminalMenu(
            items,
            title=header,
            menu_cursor="> ",
            cycle_cursor=True,
            clear_screen=True,
        )
        result = menu.show()
        if result is None:
            return

        selected = items[result]
        if selected.startswith("[d]"):
            self._confirm_delete(skill)
        elif selected.startswith("[m]"):
            target = (
                SkillScope.PROJECT
                if skill.scope == SkillScope.USER
                else SkillScope.USER
            )
            self._confirm_move(skill, target)
        elif selected.startswith("[i]"):
            self._do_import(skill)
        elif selected.startswith("[p]"):
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
        from simple_term_menu import TerminalMenu

        items = [
            "Import from agent directories",
            "Create new skill",
            "Back",
        ]
        menu = TerminalMenu(
            items,
            title="\n  Install Skill\n",
            menu_cursor="> ",
            cycle_cursor=True,
            clear_screen=True,
        )
        result = menu.show()
        if result is None or result == 2:
            return
        if result == 0:
            self._import_flow()
        elif result == 1:
            self._create_flow()

    def _import_flow(self) -> None:
        """Interactive import flow."""
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

        from simple_term_menu import TerminalMenu

        items = [f"{s.name} ({_SCOPE_LABELS[s.scope]})" for s in importable]
        items.append("Cancel")
        menu = TerminalMenu(
            items,
            title="\n  Select skill to import:\n",
            menu_cursor="> ",
            cycle_cursor=True,
            clear_screen=True,
        )
        idx = menu.show()
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

    def _deploy_flow(self) -> None:
        """Interactive deploy flow."""
        synapse_skills = discover_skills(synapse_dir=self._synapse_dir)
        synapse_only = [s for s in synapse_skills if s.scope == SkillScope.SYNAPSE]
        if not synapse_only:
            print("\n  No skills in ~/.synapse/skills/ to deploy.")
            input("  Press Enter to continue...")
            return

        from simple_term_menu import TerminalMenu

        items = [f"{s.name} - {s.description[:40]}" for s in synapse_only]
        items.append("Cancel")
        menu = TerminalMenu(
            items,
            title="\n  Select skill to deploy:\n",
            menu_cursor="> ",
            cycle_cursor=True,
            clear_screen=True,
        )
        idx = menu.show()
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
            from simple_term_menu import TerminalMenu
        except ImportError:
            print("Error: simple_term_menu is required for interactive mode.")
            return None

        items = [
            "List skill sets",
            "Create new skill set",
            "Edit skill set",
            "Delete skill set",
            "Exit",
        ]
        menu = TerminalMenu(
            items,
            title="\n  SYNAPSE SKILL SETS\n",
            menu_cursor="> ",
            menu_cursor_style=("fg_yellow", "bold"),
            menu_highlight_style=("fg_yellow", "bold"),
            cycle_cursor=True,
            clear_screen=True,
        )
        choice = menu.show()
        if choice is None:
            return None
        return ["list", "create", "edit", "delete", "exit"][int(choice)]

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
        sets = load_skill_sets()
        if not sets:
            print(f"\n  No skill sets to {action}.")
            input("  Press Enter to continue...")
            return None

        try:
            from simple_term_menu import TerminalMenu
        except ImportError:
            return None

        items = [f"{name} - {ssd.description}" for name, ssd in sorted(sets.items())]
        items.append("Cancel")
        menu = TerminalMenu(
            items,
            title=f"\n  Select skill set to {action}:\n",
            menu_cursor="> ",
            cycle_cursor=True,
            clear_screen=True,
        )
        choice = menu.show()
        if choice is None or int(choice) >= len(sets):
            return None
        return sorted(sets.keys())[int(choice)]

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
