# Input Routing Specification

## Overview

Synapseでラップされたエージェントにおいて、人間の入力を監視し、`@Agent` パターンを検知して自動的に他のエージェントにルーティングする機能。

## Goals

1. **透明性**: 人間はSynapseの存在を意識しない
2. **シームレス**: 通常のエージェント操作と `@Agent` 送信が自然に共存
3. **リアルタイム**: 入力中もエコーバックが正常に動作

## Quick Start

```bash
# Terminal 1: Claudeを起動
synapse claude

# Terminal 2: Geminiを起動
synapse gemini --port 8102

# Claudeのターミナルで:
claude> @gemini 明日の天気は？                      # デフォルトで回答を待つ
claude> @gemini --non-response 'ログを記録して'     # 回答を待たずに送信
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Human Input                              │
│                        ↓                                    │
│              ┌─────────────────┐                            │
│              │  Input Monitor  │                            │
│              │  (PTY stdin)    │                            │
│              └────────┬────────┘                            │
│                       ↓                                     │
│              ┌─────────────────┐                            │
│              │  Line Buffer    │                            │
│              │  (accumulate)   │                            │
│              └────────┬────────┘                            │
│                       ↓                                     │
│              ┌─────────────────┐                            │
│              │  Pattern Check  │                            │
│              │  on Enter key   │                            │
│              └────────┬────────┘                            │
│                       ↓                                     │
│         ┌─────────────┴─────────────┐                       │
│         ↓                           ↓                       │
│  ┌─────────────┐           ┌─────────────┐                  │
│  │ @Agent      │           │ Normal      │                  │
│  │ Detected    │           │ Input       │                  │
│  └──────┬──────┘           └──────┬──────┘                  │
│         ↓                         ↓                         │
│  ┌─────────────┐           ┌─────────────┐                  │
│  │ A2A Send    │           │ Pass to     │                  │
│  │ to Target   │           │ Agent PTY   │                  │
│  └─────────────┘           └─────────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

## Input Flow

### Step 1: Character-by-Character Input

人間がキーを押すたびに、1文字ずつPTYに送られる。

```
Input: "@Gemini hello"
Stream: '@' → 'G' → 'e' → 'm' → 'i' → 'n' → 'i' → ' ' → 'h' → ...
```

### Step 2: Line Buffering

入力をバッファに蓄積し、Enterキー（`\r` or `\n`）で行を確定。

```python
class InputRouter:
    def __init__(self):
        self.line_buffer = ""

    def process_char(self, char: str) -> tuple[str, bool]:
        """
        Returns: (output_to_pty, should_send_a2a)
        """
        if char in ('\r', '\n'):
            # Line complete - check pattern
            line = self.line_buffer
            self.line_buffer = ""

            if self.is_a2a_command(line):
                return ("", True)  # Don't pass to PTY, send via A2A
            else:
                return (line + char, False)  # Normal input
        else:
            self.line_buffer += char
            return (char, False)  # Echo back normally
```

### Step 3: Pattern Detection

```python
import re

A2A_PATTERN = re.compile(r'^@(\w+)\s+(.+)$')

def is_a2a_command(self, line: str) -> bool:
    return bool(A2A_PATTERN.match(line))

def parse_a2a_command(self, line: str) -> tuple[str, str]:
    match = A2A_PATTERN.match(line)
    if match:
        return match.group(1), match.group(2)  # agent, message
    return None, None
```

### Step 4: Routing Decision

| パターン | 動作 |
|---------|------|
| `@Gemini hello` | Geminiに "hello" を送信、ローカルエージェントには渡さない |
| `@Gemini --here hello` | Geminiに送信し、回答をこのターミナルに表示 |
| `hello world` | 通常通りローカルエージェントに渡す |
| `email@example.com` | 通常入力（@の後にスペースがない） |

## Edge Cases

### 1. Backspace Handling

バッファからも文字を削除する必要がある。

```python
def process_char(self, char: str) -> tuple[str, bool]:
    if char == '\x7f':  # Backspace
        if self.line_buffer:
            self.line_buffer = self.line_buffer[:-1]
        return (char, False)
    # ...
```

### 2. Control Characters

Ctrl+C, Ctrl+D などはそのまま通す。

```python
CONTROL_CHARS = {'\x03', '\x04', '\x1a'}  # Ctrl+C, D, Z

def process_char(self, char: str):
    if char in CONTROL_CHARS:
        self.line_buffer = ""  # Clear buffer
        return (char, False)
```

### 3. Paste (Multi-character Input)

貼り付け時は複数文字が一度に来る可能性がある。

```python
def process_input(self, data: str):
    for char in data:
        self.process_char(char)
```

### 4. Arrow Keys / Escape Sequences

矢印キーなどはエスケープシーケンス。バッファには含めない。

```python
def is_escape_sequence(self, data: str) -> bool:
    return data.startswith('\x1b')
```

## Visual Feedback

### Option A: Silent (Default)

`@Agent` 入力は表示されるが、送信後にクリア。

```
claude> @Gemini hello
[Sent to Gemini]
claude>
```

### Option B: Inline Notification

```
claude> @Gemini hello
→ Gemini: Sending...
→ Gemini: Delivered
claude>
```

## Configuration

```yaml
# ~/.synapse/config.yaml
input_routing:
  enabled: true
  pattern: "^@(\\w+)\\s+(.+)$"
  feedback: "silent"  # or "inline"
  passthrough_on_fail: true  # If agent not found, pass to local
```

## API Changes

### TerminalController

```python
class TerminalController:
    def __init__(self, ...):
        self.input_router = InputRouter(registry=self.registry)

    def handle_stdin(self, data: bytes):
        """Called when human types something."""
        text = data.decode('utf-8', errors='replace')

        for char in text:
            output, is_a2a = self.input_router.process_char(char)

            if is_a2a:
                agent, message = self.input_router.get_a2a_command()
                self.send_to_agent(agent, message)
                self.write_feedback(f"[Sent to {agent}]\n")
            elif output:
                os.write(self.master_fd, output.encode())
```

### Server Integration

サーバー側でstdin入力をフックする必要がある。現在の実装では、`/message` APIでのみ入力を受け付けているが、PTYのstdin側も監視する。

## Implementation Phases

### Phase 1: Basic Routing
- [ ] InputRouter class
- [ ] Line buffering
- [ ] Pattern detection
- [ ] A2A send integration

### Phase 2: Edge Cases
- [ ] Backspace handling
- [ ] Control characters
- [ ] Escape sequences

### Phase 3: Feedback
- [ ] Visual feedback
- [ ] Error handling (agent not found)

### Phase 4: Configuration
- [ ] Config file support
- [ ] Custom patterns
