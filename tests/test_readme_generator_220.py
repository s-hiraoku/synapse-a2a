"""Tests for template-based README generation (#220)."""

from __future__ import annotations

from pathlib import Path


def test_generate_readmes_from_template_and_translations(tmp_path: Path) -> None:
    """The generator should render one README per translation file."""
    from docs.generate_readmes import generate_readmes

    template = tmp_path / "readme-template.md"
    translations = tmp_path / "translations"
    output = tmp_path / "out"
    translations.mkdir()
    template.write_text("# {{ title }}\n\n{{ install_heading }}\n", encoding="utf-8")
    (translations / "en.yaml").write_text(
        "output: README.md\ntitle: Synapse A2A\ninstall_heading: Installation\n",
        encoding="utf-8",
    )
    (translations / "ja.yaml").write_text(
        "output: README.ja.md\ntitle: Synapse A2A\ninstall_heading: インストール\n",
        encoding="utf-8",
    )

    written = generate_readmes(template, translations, output_dir=output)

    assert [path.name for path in written] == ["README.md", "README.ja.md"]
    assert (output / "README.md").read_text(encoding="utf-8") == (
        "# Synapse A2A\n\nInstallation\n"
    )
    assert "インストール" in (output / "README.ja.md").read_text(encoding="utf-8")


def test_check_readmes_reports_stale_generated_files(tmp_path: Path) -> None:
    """CI checks should detect when generated README files are not up to date."""
    from docs.generate_readmes import check_readmes, generate_readmes

    template = tmp_path / "readme-template.md"
    translations = tmp_path / "translations"
    output = tmp_path / "out"
    translations.mkdir()
    template.write_text("# {{ title }}\n", encoding="utf-8")
    (translations / "en.yaml").write_text(
        "output: README.md\ntitle: Synapse A2A\n",
        encoding="utf-8",
    )
    generate_readmes(template, translations, output_dir=output)
    (output / "README.md").write_text("# stale\n", encoding="utf-8")

    stale = check_readmes(template, translations, output_dir=output)

    assert stale == [output / "README.md"]
