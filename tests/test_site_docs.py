"""Checks for static site-docs assets."""

from __future__ import annotations

from pathlib import Path

from synapse.canvas.protocol import FORMAT_REGISTRY, VALID_TEMPLATES

REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_card_gallery_lists_all_card_types_and_templates() -> None:
    text = _read("site-docs/assets/card-gallery.html")

    for card_type in (
        "mermaid",
        "markdown",
        "html",
        "table",
        "json",
        "diff",
        "chart",
        "image",
        "code",
        "log",
        "status",
        "metric",
        "checklist",
        "timeline",
        "alert",
        "file-preview",
        "trace",
        "progress",
        "terminal",
        "dependency-graph",
        "cost",
    ):
        assert card_type in text

    for template_name in ("briefing", "comparison", "dashboard", "steps", "slides"):
        assert template_name in text


def test_card_gallery_loads_required_cdns_and_supports_dark_theme() -> None:
    text = _read("site-docs/assets/card-gallery.html")

    assert "cdn.jsdelivr.net/npm/mermaid" in text
    assert "cdn.jsdelivr.net/npm/marked" in text
    assert "cdn.jsdelivr.net/npm/chart.js" in text
    assert "cdnjs.cloudflare.com/ajax/libs/highlight.js" in text
    assert "cdn.jsdelivr.net/npm/diff2html" in text
    assert "prefers-color-scheme: dark" in text
    assert "backdrop-filter: blur(" in text


def test_canvas_guide_links_to_card_gallery() -> None:
    text = _read("site-docs/guide/canvas.md")

    assert "../assets/card-gallery.html" in text
    assert "Card Gallery" in text


def test_canvas_guide_documents_block_level_metadata_and_supported_scope() -> None:
    text = _read("site-docs/guide/canvas.md")

    assert "x_title" in text
    assert "x_filename" in text
    assert "block-level metadata" in text
    for fmt in ("mermaid", "json", "code", "log", "checklist", "trace", "tip"):
        assert fmt in text, f"expected format '{fmt}' in block-level metadata docs"


def test_canvas_cli_docs_use_current_post_commands() -> None:
    readme = _read("README.md")
    cli_ref = _read("site-docs/reference/cli.md")
    guide = _read("site-docs/guide/canvas.md")
    cheatsheet = _read("site-docs/reference/cli-cheatsheet.md")

    assert "--no-open" in readme
    assert "--no-open" in cli_ref
    assert 'synapse canvas post <format> "<body>"' in cli_ref
    assert 'synapse canvas <format> "<body>"' not in cli_ref
    assert "synapse canvas post-raw '<Canvas Message JSON>'" in cli_ref
    assert "synapse canvas post '<Canvas Message JSON>'" not in cli_ref
    assert "Other templates can be posted via the `post-raw` command" in guide
    assert "synapse canvas post-raw '<Canvas Message JSON>'" in guide
    assert "synapse canvas post '<Canvas Message JSON>'" not in guide
    assert 'synapse canvas post mermaid "..." --title T' in cheatsheet
    assert "synapse canvas post-raw '{raw JSON}'" in cheatsheet
    assert "synapse canvas post '{raw JSON}'" not in cheatsheet


def test_canvas_guide_documents_block_level_metadata_instead_of_body_envelopes() -> (
    None
):
    text = _read("site-docs/guide/canvas.md")

    assert "x_title" in text
    assert "x_filename" in text
    assert "block-level metadata" in text
    assert "{source, title?, filename?}" not in text
    assert "{data, title?, filename?}" not in text
    assert "{code, title?, filename?, lang?}" not in text


def test_canvas_design_doc_describes_metadata_for_supported_formats() -> None:
    text = _read("docs/design/canvas.md")

    assert "x_title" in text
    assert "x_filename" in text
    assert "mermaid, json, code, log, checklist, trace, tip" in text
    assert "body-embedded metadata pattern" in text


def test_canvas_cli_docs_note_no_open_and_post_raw_for_structured_cards() -> None:
    readme = _read("README.md")
    cli_ref = _read("site-docs/reference/cli.md")

    assert "--no-open" in readme
    assert "--no-open" in cli_ref
    assert "post-raw" in cli_ref
    assert "structured cards" in cli_ref or "structured card" in cli_ref


def test_mcp_bootstrap_design_doc_covers_key_decisions() -> None:
    text = _read("docs/design/mcp-bootstrap.md")

    assert "# MCP Bootstrap Design for Synapse" in text
    assert "## なぜ MCP を使うのか" in text
    assert "## 推奨アーキテクチャ" in text
    assert "## MCP サーバ構成" in text
    assert "## 段階的な導入計画" in text
    assert "CLI 主体" in text
    assert "resources" in text
    assert "tools" in text


def test_overview_links_to_mcp_bootstrap_design_doc() -> None:
    text = _read("guides/overview.md")

    assert "docs/design/mcp-bootstrap.md" in text
    assert "MCP Bootstrap Design" in text


def test_mcp_bootstrap_design_doc_covers_phase2_bootstrap_tool() -> None:
    text = _read("docs/design/mcp-bootstrap.md")

    assert "### Phase 2: bootstrap tool" in text
    assert "`bootstrap_agent()`" in text
    assert "resource は静的" in text
    assert "agent 固有値は tool" in text


def test_mcp_bootstrap_design_doc_marks_phase1_as_transitional() -> None:
    text = _read("docs/design/mcp-bootstrap.md")

    assert "Phase 1" in text
    assert "暫定" in text
    assert "bootstrap_agent" in text
    assert "tools/list" in text


def test_mcp_bootstrap_doc_includes_claude_and_codex_config_examples() -> None:
    text = _read("docs/design/mcp-bootstrap.md")

    assert ".mcp.json" in text
    assert "~/.codex/config.toml" in text
    assert '"command": "/path/to/uv"' in text
    assert '"/path/to/repo"' in text


def test_mcp_bootstrap_doc_includes_manual_test_flow() -> None:
    text = _read("docs/design/mcp-bootstrap.md")

    assert "initialize" in text
    assert "resources/list" in text
    assert "resources/read" in text
    assert "tools/list" in text
    assert "tools/call" in text
    assert "pytest tests/test_mcp_bootstrap.py -q" in text


def test_synapse_reference_mentions_synapse_mcp_serve() -> None:
    """Check that synapse mcp serve is documented in the reference."""
    text = _read("docs/synapse-reference.md")

    assert "synapse mcp serve" in text


def test_mcp_bootstrap_doc_covers_agent_specific_config_locations() -> None:
    text = _read("docs/design/mcp-bootstrap.md")

    assert "Claude Code" in text
    assert "~/.claude.json" in text
    assert ".mcp.json" in text
    assert "Codex" in text
    assert "~/.codex/config.toml" in text
    assert "Gemini CLI" in text
    assert "~/.gemini/settings.json" in text
    assert "OpenCode" in text
    assert "~/.config/opencode/opencode.json" in text


def test_mcp_bootstrap_doc_includes_synapse_examples_for_all_supported_clients() -> (
    None
):
    text = _read("docs/design/mcp-bootstrap.md")

    assert "python -m synapse.mcp" in text
    assert "/path/to/uv" in text
    assert "synapse-user" in text
    assert "synapse-codex-8120" in text
    assert "synapse-gemini-8110" in text
    assert "synapse-opencode-8130" in text


def test_mcp_bootstrap_doc_links_primary_sources_and_notes_runtime_caveats() -> None:
    text = _read("docs/design/mcp-bootstrap.md")

    assert "https://code.claude.com/docs/en/mcp" in text
    assert "https://developers.openai.com/resources/docs-mcp" in text
    assert "https://geminicli.com/docs/tools/mcp-server" in text
    assert "https://opencode.ai/docs/config" in text
    assert "古いグローバル synapse" in text
    assert "repo checkout を直接使う" in text
    assert "/Users/hiraoku.shinichi" not in text
    assert "/Volumes/SSD/ghq/github.com/s-hiraoku/synapse-a2a" not in text


def test_readme_marks_mcp_bootstrap_doc_as_japanese() -> None:
    text = _read("README.md")

    assert "MCP Bootstrap Design (Japanese)" in text


def test_internal_docs_readme_tracks_current_canvas_format_and_template_counts() -> (
    None
):
    text = _read("docs/README.md")

    expected_summary = (
        f"{len(FORMAT_REGISTRY)} コンテンツフォーマット + "
        f"{len(VALID_TEMPLATES)} テンプレート"
    )
    assert expected_summary in text
    for template_name in sorted(VALID_TEMPLATES):
        assert template_name in text


def test_site_index_canvas_section_tracks_current_template_count() -> None:
    text = _read("site-docs/index.md")

    assert f"{len(VALID_TEMPLATES)} layout templates" in text
    assert "Five layout templates" not in text
    for template_name in sorted(VALID_TEMPLATES):
        assert template_name in text


def test_card_gallery_tracks_current_template_count() -> None:
    text = _read("site-docs/assets/card-gallery.html")

    assert f">{len(VALID_TEMPLATES)} templates<" in text
    assert ">5 templates<" not in text


def test_canvas_guide_describes_dashboard_sse_with_polling_fallback() -> None:
    text = _read("site-docs/guide/canvas.md")

    assert "10-second fallback polling interval" in text
    assert "no periodic polling" not in text


def test_canvas_design_phase6_tracks_plan_template_rollout() -> None:
    text = _read("docs/design/canvas.md")

    assert "- [x] 6 templates:" in text
    assert "`plan`" in text
    assert "_validate_plan" in text
    assert "renderPlanTemplate" in text
    assert "CSS styles for all 6 templates" in text
