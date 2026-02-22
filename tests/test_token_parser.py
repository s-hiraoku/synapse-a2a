"""Tests for synapse.token_parser (#5 Token/Cost Tracking skeleton)."""


class TestTokenUsageDataclass:
    """Tests for TokenUsage dataclass."""

    def test_token_usage_defaults(self):
        """All fields should default to None."""
        from synapse.token_parser import TokenUsage

        usage = TokenUsage()
        assert usage.input_tokens is None
        assert usage.output_tokens is None
        assert usage.cost_usd is None
        assert usage.model is None

    def test_token_usage_with_values(self):
        """Fields should accept explicit values."""
        from synapse.token_parser import TokenUsage

        usage = TokenUsage(
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.03,
            model="claude-sonnet-4-20250514",
        )
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 500
        assert usage.cost_usd == 0.03
        assert usage.model == "claude-sonnet-4-20250514"

    def test_token_usage_to_dict(self):
        """to_dict() should return a serializable dictionary."""
        from synapse.token_parser import TokenUsage

        usage = TokenUsage(input_tokens=100, output_tokens=50, cost_usd=0.01)
        d = usage.to_dict()
        assert isinstance(d, dict)
        assert d["input_tokens"] == 100
        assert d["output_tokens"] == 50
        assert d["cost_usd"] == 0.01
        assert d["model"] is None

    def test_token_usage_to_dict_roundtrip(self):
        """to_dict() output should be reconstructable via TokenUsage(**d)."""
        from synapse.token_parser import TokenUsage

        original = TokenUsage(
            input_tokens=200, output_tokens=100, cost_usd=0.05, model="gpt-4"
        )
        d = original.to_dict()
        restored = TokenUsage(**d)
        assert restored == original


class TestParseTokens:
    """Tests for parse_tokens() function."""

    def test_parse_tokens_unknown_agent_returns_none(self):
        """Unknown agent type should return None (no parser registered)."""
        from synapse.token_parser import parse_tokens

        result = parse_tokens("unknown-agent", "some output text")
        assert result is None

    def test_parse_tokens_empty_output_returns_none(self):
        """Empty output should return None."""
        from synapse.token_parser import parse_tokens

        result = parse_tokens("claude", "")
        assert result is None

    def test_parse_tokens_never_raises(self):
        """parse_tokens should never raise — always return None on error."""
        from synapse.token_parser import parse_tokens

        # Even with bizarre inputs, no exception should escape
        for agent in ["claude", "gemini", "codex", "", None]:
            for output in ["", None, 123, {"bad": "input"}, [1, 2, 3]]:
                result = parse_tokens(agent, output)
                assert result is None or hasattr(result, "input_tokens")

    def test_parse_tokens_with_registered_parser(self):
        """If a parser is registered, parse_tokens should use it."""
        from synapse.token_parser import _PARSERS, TokenUsage, parse_tokens

        # Register a test parser
        def fake_parser(output: str) -> TokenUsage | None:
            if "tokens:" in output:
                return TokenUsage(input_tokens=42, output_tokens=10)
            return None

        _PARSERS["test-agent"] = fake_parser
        try:
            result = parse_tokens("test-agent", "tokens: 42")
            assert result is not None
            assert result.input_tokens == 42
            assert result.output_tokens == 10
        finally:
            del _PARSERS["test-agent"]

    def test_parse_tokens_parser_exception_returns_none(self):
        """If a registered parser raises, parse_tokens should catch and return None."""
        from synapse.token_parser import _PARSERS, parse_tokens

        def broken_parser(output: str) -> None:
            raise ValueError("parser broke")

        _PARSERS["broken-agent"] = broken_parser
        try:
            result = parse_tokens("broken-agent", "any output")
            assert result is None
        finally:
            del _PARSERS["broken-agent"]


class TestTokenMetadataRoundtrip:
    """Test that token data survives metadata serialization."""

    def test_token_metadata_roundtrip(self):
        """TokenUsage should survive JSON serialization via metadata dict."""
        import json

        from synapse.token_parser import TokenUsage

        usage = TokenUsage(
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.02,
            model="claude-sonnet-4-20250514",
        )
        metadata = {"tokens": usage.to_dict()}

        # Simulate JSON round-trip (as done by history.save_observation)
        serialized = json.dumps(metadata)
        deserialized = json.loads(serialized)

        restored = TokenUsage(**deserialized["tokens"])
        assert restored == usage
