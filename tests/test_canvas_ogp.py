"""Tests for synapse.canvas.ogp — OGP metadata fetching."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from synapse.canvas.ogp import _is_private_ip, _parse_ogp_tags, fetch_ogp

# ============================================================
# Unit tests — _is_private_ip
# ============================================================


class TestIsPrivateIP:
    def test_loopback_v4(self) -> None:
        assert _is_private_ip("127.0.0.1") is True

    def test_loopback_v6(self) -> None:
        assert _is_private_ip("::1") is True

    def test_private_10(self) -> None:
        assert _is_private_ip("10.0.0.1") is True

    def test_private_172(self) -> None:
        assert _is_private_ip("172.16.0.1") is True
        assert _is_private_ip("172.31.255.255") is True

    def test_private_192(self) -> None:
        assert _is_private_ip("192.168.1.1") is True

    def test_public(self) -> None:
        assert _is_private_ip("8.8.8.8") is False
        assert _is_private_ip("1.1.1.1") is False

    def test_link_local(self) -> None:
        assert _is_private_ip("169.254.1.1") is True

    def test_non_private_172(self) -> None:
        assert _is_private_ip("172.32.0.1") is False


# ============================================================
# Unit tests — _parse_ogp_tags
# ============================================================


class TestParseOgpTags:
    def test_basic_ogp(self) -> None:
        html = """
        <html><head>
        <meta property="og:title" content="Test Title" />
        <meta property="og:description" content="A description" />
        <meta property="og:image" content="https://example.com/img.jpg" />
        <meta property="og:site_name" content="Example" />
        <meta property="og:url" content="https://example.com/page" />
        <meta property="og:type" content="article" />
        </head><body></body></html>
        """
        result = _parse_ogp_tags(html)
        assert result["og_title"] == "Test Title"
        assert result["og_description"] == "A description"
        assert result["og_image"] == "https://example.com/img.jpg"
        assert result["og_site_name"] == "Example"
        assert result["og_url"] == "https://example.com/page"
        assert result["og_type"] == "article"

    def test_missing_tags_returns_empty(self) -> None:
        html = "<html><head><title>No OGP</title></head><body></body></html>"
        result = _parse_ogp_tags(html)
        assert result.get("og_title") is None
        assert result.get("og_description") is None

    def test_favicon_link(self) -> None:
        html = """
        <html><head>
        <link rel="icon" href="/favicon.ico" />
        </head><body></body></html>
        """
        result = _parse_ogp_tags(html)
        assert result["favicon"] == "/favicon.ico"

    def test_shortcut_icon(self) -> None:
        html = """
        <html><head>
        <link rel="shortcut icon" href="/icon.png" />
        </head><body></body></html>
        """
        result = _parse_ogp_tags(html)
        assert result["favicon"] == "/icon.png"

    def test_title_fallback(self) -> None:
        html = "<html><head><title>Fallback Title</title></head><body></body></html>"
        result = _parse_ogp_tags(html)
        assert result.get("title_fallback") == "Fallback Title"

    def test_description_fallback(self) -> None:
        html = """
        <html><head>
        <meta name="description" content="Meta desc" />
        </head><body></body></html>
        """
        result = _parse_ogp_tags(html)
        assert result.get("description_fallback") == "Meta desc"


# ============================================================
# Integration tests — fetch_ogp (mocked HTTP)
# ============================================================


OGP_HTML = """<!DOCTYPE html>
<html><head>
<meta property="og:title" content="GitHub" />
<meta property="og:description" content="Build software" />
<meta property="og:image" content="https://github.com/og.png" />
<meta property="og:site_name" content="GitHub" />
<link rel="icon" href="https://github.com/favicon.ico" />
<title>GitHub</title>
</head><body></body></html>"""


class MockResponse:
    def __init__(
        self,
        status_code: int = 200,
        text: str = OGP_HTML,
        headers: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.headers = headers or {"content-type": "text/html; charset=utf-8"}
        self.is_redirect = 300 <= status_code < 400

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        yield self.text.encode()

    async def aclose(self) -> None:
        pass


class MockStream:
    """Mock for httpx streaming context manager."""

    def __init__(self, response: MockResponse) -> None:
        self.response = response

    async def __aenter__(self) -> MockResponse:
        return self.response

    async def __aexit__(self, *args: object) -> None:
        pass


class MockAsyncClient:
    def __init__(
        self,
        response: MockResponse | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self.response = response or MockResponse()
        self.raise_error = raise_error

    async def __aenter__(self) -> MockAsyncClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    def stream(self, method: str, url: str, **kwargs: object) -> MockStream:
        if self.raise_error:
            raise self.raise_error
        return MockStream(self.response)


@pytest.mark.asyncio
async def test_fetch_ogp_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful OGP fetch returns enriched metadata."""
    monkeypatch.setattr(
        "synapse.canvas.ogp.httpx.AsyncClient",
        lambda **kw: MockAsyncClient(),
    )
    monkeypatch.setattr("synapse.canvas.ogp._is_private_ip", lambda host: False)

    result = await fetch_ogp("https://github.com")
    assert result["fetched"] is True
    assert result["og_title"] == "GitHub"
    assert result["og_description"] == "Build software"
    assert result["og_image"] == "https://github.com/og.png"
    assert result["domain"] == "github.com"
    assert result["url"] == "https://github.com"


@pytest.mark.asyncio
async def test_fetch_ogp_non_html(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-HTML content returns fallback."""
    resp = MockResponse(headers={"content-type": "application/json"})
    monkeypatch.setattr(
        "synapse.canvas.ogp.httpx.AsyncClient",
        lambda **kw: MockAsyncClient(response=resp),
    )

    result = await fetch_ogp("https://api.example.com/data")
    assert result["fetched"] is False
    assert result["domain"] == "api.example.com"


@pytest.mark.asyncio
async def test_fetch_ogp_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP errors return fallback."""
    resp = MockResponse(status_code=404)
    monkeypatch.setattr(
        "synapse.canvas.ogp.httpx.AsyncClient",
        lambda **kw: MockAsyncClient(response=resp),
    )

    result = await fetch_ogp("https://example.com/404")
    assert result["fetched"] is False


@pytest.mark.asyncio
async def test_fetch_ogp_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Timeout returns fallback."""
    monkeypatch.setattr(
        "synapse.canvas.ogp.httpx.AsyncClient",
        lambda **kw: MockAsyncClient(raise_error=httpx.TimeoutException("timeout")),
    )

    result = await fetch_ogp("https://slow.example.com")
    assert result["fetched"] is False
    assert result["domain"] == "slow.example.com"


@pytest.mark.asyncio
async def test_fetch_ogp_ssrf_private_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Private IPs are rejected (SSRF protection)."""
    result = await fetch_ogp("http://192.168.1.1/admin")
    assert result["fetched"] is False


@pytest.mark.asyncio
async def test_fetch_ogp_ssrf_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    """localhost is rejected (SSRF protection)."""
    result = await fetch_ogp("http://localhost:8080/secret")
    assert result["fetched"] is False


@pytest.mark.asyncio
async def test_fetch_ogp_invalid_scheme() -> None:
    """Non-http(s) schemes are rejected."""
    result = await fetch_ogp("ftp://example.com/file")
    assert result["fetched"] is False

    result = await fetch_ogp("file:///etc/passwd")
    assert result["fetched"] is False


@pytest.mark.asyncio
async def test_fetch_ogp_fallback_title(monkeypatch: pytest.MonkeyPatch) -> None:
    """When og:title is missing, falls back to <title> tag."""
    html = "<html><head><title>Fallback</title></head><body></body></html>"
    monkeypatch.setattr(
        "synapse.canvas.ogp.httpx.AsyncClient",
        lambda **kw: MockAsyncClient(response=MockResponse(text=html)),
    )
    monkeypatch.setattr("synapse.canvas.ogp._is_private_ip", lambda host: False)

    result = await fetch_ogp("https://example.com")
    assert result["fetched"] is True
    assert result["og_title"] == "Fallback"


@pytest.mark.asyncio
async def test_fetch_ogp_favicon_absolute(monkeypatch: pytest.MonkeyPatch) -> None:
    """Relative favicon paths are resolved to absolute URLs."""
    html = '<html><head><link rel="icon" href="/fav.ico" /></head></html>'
    monkeypatch.setattr(
        "synapse.canvas.ogp.httpx.AsyncClient",
        lambda **kw: MockAsyncClient(response=MockResponse(text=html)),
    )
    monkeypatch.setattr("synapse.canvas.ogp._is_private_ip", lambda host: False)

    result = await fetch_ogp("https://example.com/page")
    assert result["favicon"] == "https://example.com/fav.ico"
