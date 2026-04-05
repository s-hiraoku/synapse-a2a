from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def _make_client(tmp_path: Path, monkeypatch) -> TestClient:
    from synapse.canvas.server import create_app

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SYNAPSE_DIR", str(tmp_path / ".synapse"))
    app = create_app(db_path=str(tmp_path / "canvas.db"))
    return TestClient(app)


def _write_page(tmp_path: Path, name: str, content: str) -> None:
    pages_dir = tmp_path / ".synapse" / "wiki" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    (pages_dir / name).write_text(content, encoding="utf-8")


def test_list_wiki_pages_returns_empty_when_wiki_dir_missing(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    resp = client.get("/api/wiki", params={"scope": "project"})

    assert resp.status_code == 200
    assert resp.json() == {"scope": "project", "pages": [], "exists": False}


def test_list_wiki_pages_returns_parsed_page_metadata(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    _write_page(
        tmp_path,
        "alpha.md",
        """---
title: Alpha
sources:
  - src-1
tags:
  - test
---
# Alpha

First summary line.

Related to [[beta]] and [[gamma]].
""",
    )

    resp = client.get("/api/wiki", params={"scope": "project"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "project"
    assert data["exists"] is True
    assert len(data["pages"]) == 1
    page = data["pages"][0]
    assert page["filename"] == "alpha.md"
    assert page["slug"] == "alpha"
    assert page["title"] == "Alpha"
    assert page["tags"] == ["test"]
    assert page["summary"] == "First summary line."
    assert page["link_count"] == 2
    assert page["source_count"] == 1


def test_get_wiki_page_returns_page_content(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    _write_page(
        tmp_path,
        "overview.md",
        """---
title: Overview
sources:
  - source-1
---
Body paragraph with [[alpha]] and [[beta]].
""",
    )

    resp = client.get("/api/wiki/project/pages/overview")

    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "overview"
    assert data["filename"] == "overview.md"
    assert data["title"] == "Overview"
    assert data["sources"] == ["source-1"]
    assert data["body"] == "Body paragraph with [[alpha]] and [[beta]].\n"
    assert data["links"] == ["alpha", "beta"]


def test_get_wiki_page_returns_404_for_missing_page(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    resp = client.get("/api/wiki/project/pages/missing")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Page not found: missing"


def test_wiki_stats_returns_counts_and_recent_activity(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    wiki_dir = tmp_path / ".synapse" / "wiki"
    _write_page(tmp_path, "alpha.md", "Alpha body\n")
    _write_page(tmp_path, "beta.md", "Beta body\n")

    sources_dir = wiki_dir / "sources"
    sources_dir.mkdir(parents=True)
    (sources_dir / "source-1.md").write_text("source 1", encoding="utf-8")
    (sources_dir / "source-2.md").write_text("source 2", encoding="utf-8")

    (wiki_dir / "log.md").write_text(
        """## [2026-04-05 14:32] ingest | Article One
## [2026-04-05 15:10] update | Article Two
""",
        encoding="utf-8",
    )

    resp = client.get("/api/wiki/stats", params={"scope": "project"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "project"
    assert data["exists"] is True
    assert data["page_count"] == 2
    assert data["source_count"] == 2
    assert data["last_updated"] is not None
    assert data["recent_activity"] == [
        {
            "timestamp": "2026-04-05 15:10",
            "operation": "update",
            "detail": "Article Two",
        },
        {
            "timestamp": "2026-04-05 14:32",
            "operation": "ingest",
            "detail": "Article One",
        },
    ]


def test_get_wiki_page_prevents_path_traversal(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    resp = client.get("/api/wiki/project/pages/..%2F..%2F..%2Fetc%2Fpasswd")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Page not found: ../../../etc/passwd"


def test_parse_frontmatter_handles_valid_missing_and_malformed_content():
    from synapse.wiki import parse_frontmatter as _parse_frontmatter

    valid_fm, valid_body = _parse_frontmatter(
        """---
title: Valid
sources:
  - src
---
Body
"""
    )
    missing_fm, missing_body = _parse_frontmatter("Plain body\n")
    malformed_fm, malformed_body = _parse_frontmatter(
        """---
title: [broken
---
Still body
"""
    )

    assert valid_fm == {"title": "Valid", "sources": ["src"]}
    assert valid_body == "Body\n"
    assert missing_fm == {}
    assert missing_body == "Plain body\n"
    assert malformed_fm == {}
    assert malformed_body == "Still body\n"


def _clear_wiki_enabled_cache():
    from synapse.canvas.routes.wiki import _wiki_enabled_cache

    _wiki_enabled_cache["value"] = None
    _wiki_enabled_cache["ts"] = 0.0


def test_wiki_enabled_endpoint_defaults_to_true(tmp_path, monkeypatch):
    _clear_wiki_enabled_cache()
    client = _make_client(tmp_path, monkeypatch)

    resp = client.get("/api/wiki/enabled")

    assert resp.status_code == 200
    assert resp.json() == {"enabled": True}


def test_wiki_enabled_endpoint_reads_settings_file(tmp_path, monkeypatch):
    _clear_wiki_enabled_cache()
    client = _make_client(tmp_path, monkeypatch)
    settings_dir = tmp_path / ".synapse"
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / "settings.json").write_text(
        '{"wiki": {"enabled": false}}',
        encoding="utf-8",
    )

    resp = client.get("/api/wiki/enabled")

    assert resp.status_code == 200
    assert resp.json() == {"enabled": False}
