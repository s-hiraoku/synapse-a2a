"""Tests for output parser module."""

from synapse.output_parser import (
    ParsedSegment,
    extract_code_blocks,
    extract_errors,
    extract_file_references,
    parse_output,
    segments_to_artifacts,
)


class TestExtractCodeBlocks:
    """Tests for code block extraction."""

    def test_extract_python_code_block(self):
        output = """Here's the code:
```python
def hello():
    print("Hello, World!")
```
That's it."""
        segments = extract_code_blocks(output)

        assert len(segments) == 1
        assert segments[0].type == "code"
        assert segments[0].metadata["language"] == "python"
        assert "def hello():" in segments[0].content

    def test_extract_multiple_code_blocks(self):
        output = """First:
```javascript
console.log("JS");
```
Second:
```python
print("Python")
```
Done."""
        segments = extract_code_blocks(output)

        assert len(segments) == 2
        assert segments[0].metadata["language"] == "javascript"
        assert segments[1].metadata["language"] == "python"

    def test_extract_code_block_no_language(self):
        output = """Code:
```
plain text code
```
"""
        segments = extract_code_blocks(output)

        assert len(segments) == 1
        assert segments[0].metadata["language"] == "text"

    def test_no_code_blocks(self):
        output = "Just plain text without any code blocks."
        segments = extract_code_blocks(output)

        assert len(segments) == 0

    def test_multiline_code_block(self):
        output = """```rust
fn main() {
    println!("Hello");
    println!("World");
}
```"""
        segments = extract_code_blocks(output)

        assert len(segments) == 1
        assert "fn main()" in segments[0].content
        assert 'println!("World")' in segments[0].content


class TestExtractFileReferences:
    """Tests for file reference extraction."""

    def test_extract_created_file_quoted(self):
        output = "I created file 'src/main.py' for you."
        segments = extract_file_references(output)

        assert len(segments) == 1
        assert segments[0].type == "file"
        assert segments[0].content == "src/main.py"
        assert segments[0].metadata["action"] == "created"

    def test_extract_created_file_backticks(self):
        output = "Created `config.json` in the project root."
        segments = extract_file_references(output)

        assert len(segments) == 1
        assert segments[0].content == "config.json"

    def test_extract_modified_file(self):
        output = 'Modified file "tests/test_app.py" with new tests.'
        segments = extract_file_references(output)

        assert len(segments) == 1
        assert segments[0].metadata["action"] == "modified"

    def test_extract_wrote_file_extension(self):
        output = "I wrote src/utils/helper.ts with the implementation."
        segments = extract_file_references(output)

        assert len(segments) == 1
        assert segments[0].content == "src/utils/helper.ts"
        assert segments[0].metadata["action"] == "created"

    def test_extract_multiple_files(self):
        output = """Created 'app.py' and modified 'config.yaml'."""
        segments = extract_file_references(output)

        assert len(segments) == 2

    def test_no_duplicates(self):
        output = "Created 'app.py' and then saved 'app.py' again."
        segments = extract_file_references(output)

        assert len(segments) == 1

    def test_no_file_references(self):
        output = "Just some text without file operations."
        segments = extract_file_references(output)

        assert len(segments) == 0


class TestExtractErrors:
    """Tests for error extraction."""

    def test_extract_simple_error(self):
        output = "error: cannot find module 'foo'"
        segments = extract_errors(output)

        assert len(segments) == 1
        assert segments[0].type == "error"

    def test_extract_python_traceback(self):
        output = """Running script...
Traceback (most recent call last):
  File "app.py", line 10, in <module>
    foo()
NameError: name 'foo' is not defined

Done."""
        segments = extract_errors(output)

        assert len(segments) >= 1
        traceback_seg = [
            s for s in segments if s.metadata.get("error_type") == "traceback"
        ]
        assert len(traceback_seg) == 1
        assert "NameError" in traceback_seg[0].content

    def test_extract_command_not_found(self):
        output = "bash: nonexistent: command not found"
        segments = extract_errors(output)

        assert len(segments) == 1
        assert segments[0].metadata["error_type"] == "command_not_found"

    def test_extract_permission_denied(self):
        output = "/usr/bin/secret: Permission denied"
        segments = extract_errors(output)

        assert len(segments) == 1
        assert segments[0].metadata["error_type"] == "permission_denied"

    def test_extract_fatal_error(self):
        output = "fatal: not a git repository"
        segments = extract_errors(output)

        assert len(segments) == 1
        assert segments[0].metadata["error_type"] == "fatal"

    def test_no_errors(self):
        output = "All tests passed successfully!"
        segments = extract_errors(output)

        assert len(segments) == 0


class TestParseOutput:
    """Tests for full output parsing."""

    def test_parse_mixed_output(self):
        output = """I'll create the file for you.

```python
def greet(name):
    return f"Hello, {name}!"
```

Created file 'greet.py' successfully.
"""
        segments = parse_output(output)

        types = [s.type for s in segments]
        assert "text" in types
        assert "code" in types
        assert "file" in types

    def test_parse_empty_output(self):
        segments = parse_output("")
        assert len(segments) == 0

    def test_parse_whitespace_only(self):
        segments = parse_output("   \n\n  ")
        assert len(segments) == 0

    def test_parse_plain_text_only(self):
        output = "Just a simple response with no special content."
        segments = parse_output(output)

        assert len(segments) == 1
        assert segments[0].type == "text"
        assert segments[0].content == output

    def test_parse_error_with_text(self):
        output = """Running tests...
error: test_foo failed
Please check the implementation."""
        segments = parse_output(output)

        types = [s.type for s in segments]
        assert "error" in types
        assert "text" in types

    def test_parse_multiple_code_blocks(self):
        output = """First implementation:
```python
def foo():
    pass
```

Updated version:
```python
def foo():
    return 42
```
"""
        segments = parse_output(output)

        code_segments = [s for s in segments if s.type == "code"]
        assert len(code_segments) == 2

    def test_parse_preserves_order(self):
        output = """Text before
```python
code
```
Text after"""
        segments = parse_output(output)

        assert segments[0].type == "text"
        assert segments[1].type == "code"
        assert segments[2].type == "text"

    def test_parse_complex_output(self):
        output = """I'll implement the feature for you.

```typescript
export function calculate(x: number): number {
    return x * 2;
}
```

Created file 'src/utils.ts'.

Running tests...
error: test_calculate failed

Let me fix that:

```typescript
export function calculate(x: number): number {
    if (x < 0) throw new Error("negative");
    return x * 2;
}
```

Modified 'src/utils.ts' with the fix.
All tests passing now!"""
        segments = parse_output(output)

        types = [s.type for s in segments]
        assert types.count("code") == 2
        assert types.count("file") == 2
        assert "error" in types
        assert "text" in types


class TestSegmentsToArtifacts:
    """Tests for artifact conversion."""

    def test_convert_text_segment(self):
        segments = [ParsedSegment(type="text", content="Hello")]
        artifacts = segments_to_artifacts(segments)

        assert len(artifacts) == 1
        assert artifacts[0]["index"] == 0
        assert artifacts[0]["parts"][0]["type"] == "text"
        assert artifacts[0]["parts"][0]["text"] == "Hello"

    def test_convert_code_segment(self):
        segments = [
            ParsedSegment(
                type="code", content="print('hi')", metadata={"language": "python"}
            )
        ]
        artifacts = segments_to_artifacts(segments)

        assert artifacts[0]["parts"][0]["type"] == "code"
        assert artifacts[0]["parts"][0]["code"] == "print('hi')"
        assert artifacts[0]["parts"][0]["language"] == "python"

    def test_convert_file_segment(self):
        segments = [
            ParsedSegment(
                type="file", content="src/app.py", metadata={"action": "created"}
            )
        ]
        artifacts = segments_to_artifacts(segments)

        assert artifacts[0]["parts"][0]["type"] == "file"
        assert artifacts[0]["parts"][0]["file"]["path"] == "src/app.py"
        assert artifacts[0]["parts"][0]["file"]["action"] == "created"

    def test_convert_error_segment(self):
        segments = [
            ParsedSegment(
                type="error",
                content="NameError: name 'x' is not defined",
                metadata={"error_type": "traceback"},
            )
        ]
        artifacts = segments_to_artifacts(segments)

        assert artifacts[0]["parts"][0]["type"] == "error"
        assert artifacts[0]["parts"][0]["error"]["type"] == "traceback"
        assert "NameError" in artifacts[0]["parts"][0]["error"]["message"]

    def test_convert_multiple_segments(self):
        segments = [
            ParsedSegment(type="text", content="Intro"),
            ParsedSegment(
                type="code", content="x = 1", metadata={"language": "python"}
            ),
            ParsedSegment(
                type="file", content="test.py", metadata={"action": "created"}
            ),
        ]
        artifacts = segments_to_artifacts(segments)

        assert len(artifacts) == 3
        assert artifacts[0]["index"] == 0
        assert artifacts[1]["index"] == 1
        assert artifacts[2]["index"] == 2

    def test_convert_empty_list(self):
        artifacts = segments_to_artifacts([])
        assert artifacts == []


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_nested_code_blocks_in_text(self):
        # Code block inside explanation
        output = """To use:
```bash
echo "hello"
```
"""
        segments = parse_output(output)
        code_seg = [s for s in segments if s.type == "code"][0]
        assert code_seg.metadata["language"] == "bash"

    def test_file_path_with_spaces(self):
        output = "Created 'My Documents/file.txt' successfully."
        segments = extract_file_references(output)

        assert len(segments) == 1
        assert segments[0].content == "My Documents/file.txt"

    def test_error_in_code_block(self):
        # Error pattern inside code block should be recognized as code, not error
        output = """Example error handling:
```python
try:
    foo()
except Exception as e:
    print(f"error: {e}")
```
"""
        segments = parse_output(output)

        # Should only have code segment (and surrounding text)
        code_segs = [s for s in segments if s.type == "code"]
        assert len(code_segs) == 1

    def test_unicode_content(self):
        output = """日本語のテキスト

```python
message = "こんにちは"
print(message)
```

Created 'greeting_日本語.py'."""
        segments = parse_output(output)

        assert len(segments) >= 2
        code_seg = [s for s in segments if s.type == "code"][0]
        assert "こんにちは" in code_seg.content

    def test_very_long_output(self):
        # Generate long output
        long_text = "A" * 10000
        output = f"""Start
```python
{long_text}
```
End"""
        segments = parse_output(output)

        code_seg = [s for s in segments if s.type == "code"][0]
        assert len(code_seg.content) == 10000

    def test_consecutive_code_blocks(self):
        output = """```python
a = 1
```
```javascript
const b = 2;
```"""
        segments = parse_output(output)

        code_segs = [s for s in segments if s.type == "code"]
        assert len(code_segs) == 2
        assert code_segs[0].metadata["language"] == "python"
        assert code_segs[1].metadata["language"] == "javascript"
