"""Tests for wiki CLI helpers and MCP resource wiring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from synapse.mcp.server import SynapseMCPServer
from synapse.settings import SynapseSettings


def _args(**kwargs: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "scope": "project",
        "source": "",
        "question": "",
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _page(
    title: str,
    *,
    page_type: str = "concept",
    created: str = "2026-04-05",
    updated: str = "2026-04-05",
    links: list[str] | None = None,
    summary: str = "Summary text.",
    include_title: bool = True,
) -> str:
    lines = [
        "---",
        f"type: {page_type}",
    ]
    if include_title:
        lines.append(f"title: {title}")
    lines.extend(
        [
            f"created: {created}",
            f"updated: {updated}",
            "sources:",
            "  - note.txt",
            "links:",
        ]
    )
    for link in links or []:
        lines.append(f"  - {link}")
    lines.extend(
        [
            "confidence: high",
            "author: tester",
            "---",
            f"# {title}",
            summary,
        ]
    )
    return "\n".join(lines) + "\n"


def _create_settings(root: Path) -> SynapseSettings:
    synapse_dir = root / ".synapse"
    synapse_dir.mkdir(parents=True, exist_ok=True)
    (synapse_dir / "default.md").write_text("Base bootstrap text.", encoding="utf-8")
    (synapse_dir / "settings.json").write_text(
        json.dumps({"instructions": {"default": "default.md"}}),
        encoding="utf-8",
    )
    return SynapseSettings.load(
        user_path=synapse_dir / "settings.json",
        project_path=synapse_dir / "settings.json",
        local_path=synapse_dir / "settings.local.json",
    )


def _create_server(root: Path) -> SynapseMCPServer:
    settings = _create_settings(root)
    return SynapseMCPServer(
        settings_factory=lambda: settings,
        agent_type="codex",
        agent_id="synapse-codex-8120",
        port=8120,
    )


def test_get_wiki_dir_returns_project_and_global_paths(tmp_path: Path) -> None:
    from synapse.wiki import get_wiki_dir

    home = tmp_path / "home"

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        with patch("synapse.wiki.Path.home", return_value=home):
            assert get_wiki_dir("project") == tmp_path / ".synapse" / "wiki"
            assert get_wiki_dir("global") == home / ".synapse" / "wiki"


def test_ensure_wiki_dir_creates_structure(tmp_path: Path) -> None:
    from synapse.wiki import ensure_wiki_dir

    home = tmp_path / "home"

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        with patch("synapse.wiki.Path.home", return_value=home):
            wiki_dir = ensure_wiki_dir("project")

    assert wiki_dir == tmp_path / ".synapse" / "wiki"
    assert (wiki_dir / "sources").is_dir()
    assert (wiki_dir / "pages").is_dir()
    assert (wiki_dir / "index.md").is_file()
    assert (wiki_dir / "log.md").is_file()
    assert (wiki_dir / "schema.md").is_file()
    assert "wikilink" in (wiki_dir / "schema.md").read_text(encoding="utf-8").lower()


def test_cmd_wiki_ingest_copies_file_and_logs(tmp_path: Path, capsys) -> None:
    from synapse.wiki import cmd_wiki_ingest

    source = tmp_path / "design-notes.md"
    source.write_text("# Notes\n", encoding="utf-8")

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        cmd_wiki_ingest(_args(source=str(source)))

    out = capsys.readouterr().out
    copied = tmp_path / ".synapse" / "wiki" / "sources" / source.name
    log_text = (tmp_path / ".synapse" / "wiki" / "log.md").read_text(encoding="utf-8")

    assert "Ingested" in out
    assert copied.read_text(encoding="utf-8") == "# Notes\n"
    assert "ingest" in log_text.lower()
    assert source.name in log_text


def test_cmd_wiki_query_returns_matching_pages(tmp_path: Path, capsys) -> None:
    from synapse.wiki import cmd_wiki_query, ensure_wiki_dir

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        wiki_dir = ensure_wiki_dir("project")

    (wiki_dir / "index.md").write_text(
        "\n".join(
            [
                "# Wiki Index",
                "",
                "- [concept-auth-flow](pages/concept-auth-flow.md): OAuth token refresh flow and auth boundaries.",
                "- [entity-terminal-controller](pages/entity-terminal-controller.md): Terminal controller responsibilities.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        cmd_wiki_query(_args(question="token auth"))

    out = capsys.readouterr().out
    assert "concept-auth-flow" in out
    assert "OAuth token refresh flow" in out


def test_cmd_wiki_lint_detects_frontmatter_links_and_orphans(
    tmp_path: Path, capsys
) -> None:
    from synapse.wiki import cmd_wiki_lint, ensure_wiki_dir

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        wiki_dir = ensure_wiki_dir("project")

    pages_dir = wiki_dir / "pages"
    (pages_dir / "concept-good.md").write_text(
        _page(
            "Good Page",
            links=["concept-orphan"],
            summary="See [[concept-orphan]] and [[concept-missing]].",
        ),
        encoding="utf-8",
    )
    (pages_dir / "concept-orphan.md").write_text(
        _page("Orphan Page"),
        encoding="utf-8",
    )
    (pages_dir / "concept-invalid.md").write_text(
        _page("Invalid Page", include_title=False),
        encoding="utf-8",
    )

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        cmd_wiki_lint(_args())

    out = capsys.readouterr().out
    assert "missing required fields" in out.lower()
    assert "concept-invalid.md" in out
    assert "broken" in out.lower()
    assert "concept-missing" in out
    assert "orphan" in out.lower()
    assert "concept-good.md" in out


def test_cmd_wiki_status_reports_counts_and_last_updated(
    tmp_path: Path, capsys
) -> None:
    from synapse.wiki import cmd_wiki_status, ensure_wiki_dir

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        wiki_dir = ensure_wiki_dir("project")

    (wiki_dir / "sources" / "one.md").write_text("source", encoding="utf-8")
    (wiki_dir / "sources" / "two.md").write_text("source", encoding="utf-8")
    (wiki_dir / "pages" / "concept-a.md").write_text(
        _page("A", updated="2026-04-01"),
        encoding="utf-8",
    )
    (wiki_dir / "pages" / "concept-b.md").write_text(
        _page("B", updated="2026-04-07"),
        encoding="utf-8",
    )

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        cmd_wiki_status(_args())

    out = capsys.readouterr().out
    assert "Pages: 2" in out
    assert "Sources: 2" in out
    assert "2026-04-07" in out


def test_settings_and_mcp_server_expose_wiki_instruction_resource(
    tmp_path: Path,
) -> None:
    server = _create_server(tmp_path)
    (tmp_path / ".synapse" / "wiki.md").write_text(
        "Wiki instructions here.",
        encoding="utf-8",
    )

    with patch("synapse.settings.Path.cwd", return_value=tmp_path):
        with patch("synapse.mcp.server.Path.cwd", return_value=tmp_path):
            resources = {resource.uri for resource in server.list_resources()}
            text = server.read_resource("synapse://instructions/wiki")

    assert "synapse://instructions/wiki" in resources
    assert "Wiki instructions here." in text
