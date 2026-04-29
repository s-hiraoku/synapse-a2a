"""Regression tests for _format_artifact_text(use_markdown=True) (#685)."""

from synapse.a2a_compat import Artifact, _format_artifact_text


def test_code_artifact_uses_markdown_fence():
    """use_markdown=True wraps code in ``` fences with language."""
    artifact = Artifact(
        type="code",
        data={"content": "x = 1", "metadata": {"language": "python"}},
    )

    output = _format_artifact_text(artifact, use_markdown=True)

    assert output == "```python\nx = 1\n```"


def test_code_artifact_uses_brackets_when_use_markdown_false():
    """Default (use_markdown=False) uses [Code: <lang>] prefix."""
    artifact = Artifact(
        type="code",
        data={"content": "x = 1", "metadata": {"language": "python"}},
    )

    output = _format_artifact_text(artifact, use_markdown=False)

    assert output == "[Code: python]\nx = 1"


def test_use_markdown_path_strips_control_bytes_in_code():
    """use_markdown=True still strips PTY control bytes from content."""
    artifact = Artifact(
        type="code",
        data={
            "content": "print(\x1b[31m'red'\x1b[0m)",
            "metadata": {"language": "python"},
        },
    )

    output = _format_artifact_text(artifact, use_markdown=True)

    assert "\x1b[31m" not in output
    assert "\x1b[0m" not in output
    assert output == "```python\nprint('red')\n```"


def test_text_artifact_unaffected_by_use_markdown_flag():
    """use_markdown is code-only; text artifacts produce the same output."""
    artifact = Artifact(type="text", data="multi\nline\ttext")

    output_false = _format_artifact_text(artifact, use_markdown=False)
    output_true = _format_artifact_text(artifact, use_markdown=True)

    assert output_false == output_true == "multi\nline\ttext"
