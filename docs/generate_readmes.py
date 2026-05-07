"""Generate localized README files from one template and YAML translations."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

_PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z0-9_.-]+)\s*}}")


def _load_translation(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"translation must be a mapping: {path}")
    return data


def _render(template: str, values: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"missing translation key: {key}")
        return str(values[key])

    return _PLACEHOLDER_RE.sub(replace, template)


def _target_path(
    translation_path: Path, values: dict[str, Any], output_dir: Path
) -> Path:
    output = values.get("output")
    if isinstance(output, str) and output.strip():
        return output_dir / output
    suffix = "" if translation_path.stem == "en" else f".{translation_path.stem}"
    return output_dir / f"README{suffix}.md"


def render_readmes(
    template_path: Path,
    translations_dir: Path,
    *,
    output_dir: Path,
) -> list[tuple[Path, str]]:
    """Render README contents without writing them."""
    template = template_path.read_text(encoding="utf-8")
    rendered: list[tuple[Path, str]] = []
    for translation_path in sorted(translations_dir.glob("*.yaml")):
        values = _load_translation(translation_path)
        target = _target_path(translation_path, values, output_dir)
        rendered.append((target, _render(template, values)))
    return rendered


def generate_readmes(
    template_path: Path,
    translations_dir: Path,
    *,
    output_dir: Path = Path("."),
) -> list[Path]:
    """Write generated README files and return the touched paths."""
    written: list[Path] = []
    for target, content in render_readmes(
        template_path,
        translations_dir,
        output_dir=output_dir,
    ):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(target)
    return written


def check_readmes(
    template_path: Path,
    translations_dir: Path,
    *,
    output_dir: Path = Path("."),
) -> list[Path]:
    """Return generated README paths whose on-disk content is stale."""
    stale: list[Path] = []
    for target, expected in render_readmes(
        template_path,
        translations_dir,
        output_dir=output_dir,
    ):
        try:
            actual = target.read_text(encoding="utf-8")
        except OSError:
            stale.append(target)
            continue
        if actual != expected:
            stale.append(target)
    return stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("docs/readme-template.md"),
        help="README template path",
    )
    parser.add_argument(
        "--translations",
        type=Path,
        default=Path("docs/translations"),
        help="Directory containing *.yaml translations",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory where README files are written",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if generated files are stale",
    )
    args = parser.parse_args(argv)

    try:
        if args.check:
            stale = check_readmes(
                args.template,
                args.translations,
                output_dir=args.output_dir,
            )
            if stale:
                for path in stale:
                    print(f"stale: {path}", file=sys.stderr)
                return 1
            return 0

        for path in generate_readmes(
            args.template,
            args.translations,
            output_dir=args.output_dir,
        ):
            print(path)
        return 0
    except (KeyError, OSError, ValueError, yaml.YAMLError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
