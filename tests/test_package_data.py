"""Verify that pyproject.toml includes all non-Python assets needed at runtime."""

from __future__ import annotations

from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"


def _load_package_data_globs() -> list[str]:
    """Return the list of package-data glob patterns from pyproject.toml."""
    with PYPROJECT.open("rb") as f:
        data = tomllib.load(f)
    return data["tool"]["setuptools"]["package-data"]["synapse"]


class TestCanvasPackageData:
    """Canvas templates and static files must be included in the package."""

    def test_canvas_templates_glob_present(self):
        globs = _load_package_data_globs()
        assert any("canvas/templates" in g for g in globs), (
            "pyproject.toml package-data must include canvas/templates/**"
        )

    def test_canvas_static_glob_present(self):
        globs = _load_package_data_globs()
        assert any("canvas/static" in g for g in globs), (
            "pyproject.toml package-data must include canvas/static/**"
        )

    def test_canvas_template_files_exist(self):
        """The actual template files must exist on disk."""
        templates = list((ROOT / "synapse" / "canvas" / "templates").glob("*.html"))
        assert len(templates) >= 1, "At least index.html must exist"

    def test_canvas_static_files_exist(self):
        """The actual static files must exist on disk."""
        static = list((ROOT / "synapse" / "canvas" / "static").glob("*"))
        assert len(static) >= 3, "canvas.js, canvas.css, palette.css must exist"
