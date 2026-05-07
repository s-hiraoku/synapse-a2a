"""Project-adaptive Markdown learnings for saved agent definitions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def _learning_path(
    agent_definition_id: str, *, project_root: Path | None = None
) -> Path:
    root = project_root or Path.cwd()
    safe_id = agent_definition_id.strip()
    if not safe_id or "/" in safe_id or "\\" in safe_id:
        raise ValueError("agent_definition_id must be a simple file stem")
    return root / ".synapse" / "learnings" / f"{safe_id}.md"


def load_project_learnings(
    agent_definition_id: str,
    *,
    project_root: Path | None = None,
) -> str:
    """Load Markdown learnings for a saved agent definition ID."""
    path = _learning_path(agent_definition_id, project_root=project_root)
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def append_project_learning(
    agent_definition_id: str,
    learning: str,
    *,
    project_root: Path | None = None,
    max_lines: int = 200,
) -> Path:
    """Append one learning and compact the file to the newest max_lines."""
    path = _learning_path(agent_definition_id, project_root=project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"- {timestamp}: {' '.join(learning.split())}"
    existing = []
    if path.exists():
        existing = path.read_text(encoding="utf-8").splitlines()
    lines = [line for line in existing if line.strip()]
    lines.append(entry)
    if max_lines > 0 and len(lines) > max_lines:
        lines = lines[-max_lines:]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def format_project_learnings_section(agent_definition_id: str) -> str:
    """Return an initial-instruction section for saved-agent learnings."""
    learnings = load_project_learnings(agent_definition_id)
    if not learnings:
        return ""
    return (
        f"\n\n[PROJECT LEARNINGS]\n"
        f"Project learnings for {agent_definition_id}:\n"
        f"{learnings}\n"
    )
