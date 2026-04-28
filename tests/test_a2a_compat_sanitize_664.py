"""Regression tests for artifact text sanitization (#664)."""

from synapse.a2a_compat import Artifact, _format_artifact_text


def test_text_artifact_strips_csi():
    artifact = Artifact(type="text", data="hello\x1b[Kworld")

    output = _format_artifact_text(artifact)

    assert "\x1b[K" not in output
    assert output == "helloworld"


def test_text_artifact_dict_strips_control():
    artifact = Artifact(type="text", data={"content": "ok\x07bell"})

    output = _format_artifact_text(artifact)

    assert "\x07" not in output
    assert output == "okbell"


def test_code_artifact_strips_within_content():
    artifact = Artifact(
        type="code",
        data={
            "content": "print(\x1b[31m'red'\x1b[0m)",
            "metadata": {"language": "python"},
        },
    )

    output = _format_artifact_text(artifact)

    assert "\x1b[31m" not in output
    assert "\x1b[0m" not in output
    assert output == "[Code: python]\nprint('red')"


def test_unknown_artifact_strips_control():
    artifact = Artifact(type="unknown_type", data="raw\x1b]1337;foo\x07payload")

    output = _format_artifact_text(artifact)

    assert "\x1b]1337;foo\x07" not in output
    assert output == "[unknown_type] rawpayload"


def test_plain_text_unchanged():
    artifact = Artifact(type="text", data="multi\nline\ttab content")

    output = _format_artifact_text(artifact)

    assert output == "multi\nline\ttab content"
