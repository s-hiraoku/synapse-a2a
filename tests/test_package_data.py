"""Verify that pyproject.toml includes all non-Python assets needed at runtime."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"


def _read_package_data_line() -> str:
    """Return the raw package-data line from pyproject.toml."""
    text = PYPROJECT.read_text(encoding="utf-8")
    # Match the synapse = [...] line under [tool.setuptools.package-data]
    m = re.search(r"synapse\s*=\s*\[([^\]]+)\]", text)
    assert m, "Could not find synapse package-data in pyproject.toml"
    return m.group(1)


class TestCanvasPackageData:
    """Canvas templates and static files must be included in the package."""

    def test_canvas_templates_glob_present(self):
        line = _read_package_data_line()
        assert "canvas/templates" in line, (
            "pyproject.toml package-data must include canvas/templates/*"
        )

    def test_canvas_static_glob_present(self):
        line = _read_package_data_line()
        assert "canvas/static" in line, (
            "pyproject.toml package-data must include canvas/static/*"
        )

    def test_canvas_template_files_exist(self):
        """The actual template files must exist on disk."""
        templates = list((ROOT / "synapse" / "canvas" / "templates").glob("*.html"))
        assert len(templates) >= 1, "At least index.html must exist"

    def test_canvas_static_files_exist(self):
        """The actual static files must exist on disk."""
        static = list((ROOT / "synapse" / "canvas" / "static").glob("*"))
        assert len(static) >= 3, "canvas.js, canvas.css, palette.css must exist"
