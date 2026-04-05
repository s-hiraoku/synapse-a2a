"""Tests for wiki CLI helpers and MCP resource wiring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    source_files: list[str] | None = None,
    source_commit: str | None = None,
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
        ]
    )
    if source_files is not None:
        lines.append("source_files:")
        for sf in source_files:
            lines.append(f"  - {sf}")
    if source_commit is not None:
        lines.append(f"source_commit: {source_commit}")
    lines.append("links:")
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


# --- Unit A: Stale detection + refresh ---


def test_detect_stale_pages_returns_empty_when_no_source_files(tmp_path: Path) -> None:
    from synapse.wiki import detect_stale_pages, ensure_wiki_dir

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        wiki_dir = ensure_wiki_dir("project")

    (wiki_dir / "pages" / "concept-nosource.md").write_text(
        _page("No Source"),
        encoding="utf-8",
    )

    result = detect_stale_pages(wiki_dir)
    assert result == []


def test_detect_stale_pages_detects_changed_source(tmp_path: Path) -> None:
    from synapse.wiki import detect_stale_pages, ensure_wiki_dir

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        wiki_dir = ensure_wiki_dir("project")

    (wiki_dir / "pages" / "concept-tracked.md").write_text(
        _page("Tracked", source_files=["src/foo.py"], source_commit="abc1234"),
        encoding="utf-8",
    )

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "src/foo.py\n"
    mock_result.stderr = ""

    with patch("synapse.wiki.subprocess.run", return_value=mock_result):
        result = detect_stale_pages(wiki_dir)

    assert len(result) == 1
    assert result[0][0].name == "concept-tracked.md"
    assert "src/foo.py" in result[0][1]


def test_detect_stale_pages_skips_unchanged_source(tmp_path: Path) -> None:
    from synapse.wiki import detect_stale_pages, ensure_wiki_dir

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        wiki_dir = ensure_wiki_dir("project")

    (wiki_dir / "pages" / "concept-clean.md").write_text(
        _page("Clean", source_files=["src/bar.py"], source_commit="abc1234"),
        encoding="utf-8",
    )

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    with patch("synapse.wiki.subprocess.run", return_value=mock_result):
        result = detect_stale_pages(wiki_dir)

    assert result == []


def test_detect_stale_pages_handles_git_failure_gracefully(tmp_path: Path) -> None:
    from synapse.wiki import detect_stale_pages, ensure_wiki_dir

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        wiki_dir = ensure_wiki_dir("project")

    (wiki_dir / "pages" / "concept-fail.md").write_text(
        _page("Fail", source_files=["src/baz.py"], source_commit="abc1234"),
        encoding="utf-8",
    )

    with patch("synapse.wiki.subprocess.run", side_effect=OSError("git not found")):
        result = detect_stale_pages(wiki_dir)

    assert result == []


def test_cmd_wiki_status_includes_stale_count(tmp_path: Path, capsys) -> None:
    from synapse.wiki import cmd_wiki_status, ensure_wiki_dir

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        wiki_dir = ensure_wiki_dir("project")

    (wiki_dir / "pages" / "concept-stale.md").write_text(
        _page("Stale", source_files=["src/foo.py"], source_commit="abc1234"),
        encoding="utf-8",
    )

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "src/foo.py\n"
    mock_result.stderr = ""

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        with patch("synapse.wiki.subprocess.run", return_value=mock_result):
            cmd_wiki_status(_args())

    out = capsys.readouterr().out
    assert "Stale pages: 1" in out


def test_cmd_wiki_lint_shows_stale_warnings(tmp_path: Path, capsys) -> None:
    from synapse.wiki import cmd_wiki_lint, ensure_wiki_dir

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        wiki_dir = ensure_wiki_dir("project")

    (wiki_dir / "pages" / "concept-stalepage.md").write_text(
        _page("Stale Page", source_files=["src/foo.py"], source_commit="abc1234"),
        encoding="utf-8",
    )

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "src/foo.py\n"
    mock_result.stderr = ""

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        with patch("synapse.wiki.subprocess.run", return_value=mock_result):
            cmd_wiki_lint(_args())

    out = capsys.readouterr().out
    assert "stale" in out.lower()
    assert "src/foo.py" in out


def test_cmd_wiki_refresh_lists_stale_pages(tmp_path: Path, capsys) -> None:
    from synapse.wiki import cmd_wiki_refresh, ensure_wiki_dir

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        wiki_dir = ensure_wiki_dir("project")

    (wiki_dir / "pages" / "concept-old.md").write_text(
        _page("Old Page", source_files=["src/foo.py"], source_commit="abc1234"),
        encoding="utf-8",
    )

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "src/foo.py\n"
    mock_result.stderr = ""

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        with patch("synapse.wiki.subprocess.run", return_value=mock_result):
            cmd_wiki_refresh(argparse.Namespace(scope="project", apply=False))

    out = capsys.readouterr().out
    assert "STALE:" in out
    assert "concept-old.md" in out


def test_cmd_wiki_refresh_apply_updates_source_commit(tmp_path: Path, capsys) -> None:
    from synapse.wiki import cmd_wiki_refresh, ensure_wiki_dir, parse_frontmatter

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        wiki_dir = ensure_wiki_dir("project")

    page_path = wiki_dir / "pages" / "concept-update.md"
    page_path.write_text(
        _page("Update Page", source_files=["src/foo.py"], source_commit="abc1234"),
        encoding="utf-8",
    )

    mock_diff = MagicMock()
    mock_diff.returncode = 0
    mock_diff.stdout = "src/foo.py\n"
    mock_diff.stderr = ""

    mock_head = MagicMock()
    mock_head.returncode = 0
    mock_head.stdout = "def5678\n"
    mock_head.stderr = ""

    def mock_run(cmd, **kwargs):
        if "rev-parse" in cmd:
            return mock_head
        return mock_diff

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        with patch("synapse.wiki.subprocess.run", side_effect=mock_run):
            cmd_wiki_refresh(argparse.Namespace(scope="project", apply=True))

    out = capsys.readouterr().out
    assert "Updated source_commit to def5678" in out

    content = page_path.read_text(encoding="utf-8")
    fm, _ = parse_frontmatter(content)
    assert fm["source_commit"] == "def5678"


def test_cmd_wiki_refresh_no_stale_pages(tmp_path: Path, capsys) -> None:
    from synapse.wiki import cmd_wiki_refresh, ensure_wiki_dir

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        ensure_wiki_dir("project")

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        cmd_wiki_refresh(argparse.Namespace(scope="project", apply=False))

    out = capsys.readouterr().out
    assert "All pages are up to date." in out


# --- Unit B: Learning page type + wiki init ---


def test_learning_page_type_is_valid():
    from synapse.wiki import WIKI_PAGE_TYPES

    assert "learning" in WIKI_PAGE_TYPES


def test_cmd_wiki_lint_accepts_learning_type(tmp_path, capsys):
    from synapse.wiki import cmd_wiki_lint, ensure_wiki_dir

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        wiki_dir = ensure_wiki_dir("project")
    pages_dir = wiki_dir / "pages"
    (pages_dir / "learning-test.md").write_text(
        _page("Test Learning", page_type="learning"),
        encoding="utf-8",
    )
    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        cmd_wiki_lint(_args())
    out = capsys.readouterr().out
    assert "invalid type" not in out.lower()


def test_cmd_wiki_init_creates_skeleton_pages(tmp_path, capsys):
    from synapse.wiki import cmd_wiki_init

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        cmd_wiki_init(_args())
    wiki_dir = tmp_path / ".synapse" / "wiki"
    arch = wiki_dir / "pages" / "synthesis-architecture.md"
    patterns = wiki_dir / "pages" / "synthesis-patterns.md"
    index = wiki_dir / "index.md"
    assert arch.exists()
    assert patterns.exists()
    # Check frontmatter
    from synapse.wiki import parse_frontmatter

    fm, body = parse_frontmatter(arch.read_text(encoding="utf-8"))
    assert fm["type"] == "synthesis"
    assert fm["title"] == "Architecture Overview"
    assert "TODO" in body
    # Check index entries
    index_text = index.read_text(encoding="utf-8")
    assert "synthesis-architecture" in index_text
    assert "synthesis-patterns" in index_text
    # Check output
    out = capsys.readouterr().out
    assert "Created synthesis-architecture.md" in out
    assert "Created synthesis-patterns.md" in out


def test_cmd_wiki_init_skips_existing_pages(tmp_path, capsys):
    from synapse.wiki import cmd_wiki_init, ensure_wiki_dir

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        wiki_dir = ensure_wiki_dir("project")
    # Pre-create one page with custom content
    pages_dir = wiki_dir / "pages"
    custom = "---\ntitle: Custom\n---\nMy custom content.\n"
    (pages_dir / "synthesis-architecture.md").write_text(custom, encoding="utf-8")
    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        cmd_wiki_init(_args())
    # Existing file should be unchanged
    assert (pages_dir / "synthesis-architecture.md").read_text(
        encoding="utf-8"
    ) == custom
    # Other file should be created
    assert (pages_dir / "synthesis-patterns.md").exists()
    out = capsys.readouterr().out
    assert "Skipped synthesis-architecture.md" in out
    assert "Created synthesis-patterns.md" in out


def test_cmd_wiki_init_is_idempotent(tmp_path, capsys):
    from synapse.wiki import cmd_wiki_init

    with patch("synapse.wiki.Path.cwd", return_value=tmp_path):
        cmd_wiki_init(_args())
        capsys.readouterr()  # clear first run output
        cmd_wiki_init(_args())
    out = capsys.readouterr().out
    # Second run should skip both
    assert "Skipped" in out
    # No duplicate index entries — each skeleton produces one line containing the slug
    index_text = (tmp_path / ".synapse" / "wiki" / "index.md").read_text(
        encoding="utf-8"
    )
    lines_with_slug = [
        line for line in index_text.splitlines() if "synthesis-architecture" in line
    ]
    assert len(lines_with_slug) == 1
