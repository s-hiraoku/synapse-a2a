"""OGP (Open Graph Protocol) metadata fetcher for link-preview cards.

Fetches a URL, parses og:* meta tags from the HTML <head>, and returns
a dict suitable for storing as a ``link-preview`` card body.

Security: only http/https schemes are allowed; private/loopback IPs
are rejected to prevent SSRF.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

# Maximum bytes to read from a response (only need <head> for OGP tags)
_MAX_READ_BYTES = 65_536  # 64 KB

# Maximum number of HTTP redirects to follow manually (SSRF-safe redirect loop)
_MAX_REDIRECTS = 10

# OGP property -> result dict key mapping
_OGP_KEYS: dict[str, str] = {
    "og:title": "og_title",
    "og:description": "og_description",
    "og:image": "og_image",
    "og:site_name": "og_site_name",
    "og:url": "og_url",
    "og:type": "og_type",
}


# ============================================================
# SSRF protection
# ============================================================


def _is_restricted(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if *addr* is private, loopback, or link-local."""
    return addr.is_private or addr.is_loopback or addr.is_link_local


def _is_private_ip(host: str) -> bool:
    """Return True if *host* resolves to a private/loopback/link-local address."""
    try:
        return _is_restricted(ipaddress.ip_address(host))
    except ValueError:
        pass
    # Not a literal IP — resolve hostname
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return any(
            _is_restricted(ipaddress.ip_address(sockaddr[0]))
            for _, _, _, _, sockaddr in infos
        )
    except (socket.gaierror, OSError):
        # Cannot resolve → treat as private (fail-safe)
        return True


# ============================================================
# HTML parser for OGP meta tags
# ============================================================


class _OGPParser(HTMLParser):
    """Lightweight parser that extracts OGP meta tags and favicon from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.result: dict[str, str] = {}
        self._in_title = False
        self._title_chars: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k: v for k, v in attrs if v is not None}

        if tag == "meta":
            # OGP: <meta property="og:..." content="..." />
            prop = attr_dict.get("property", "")
            content = attr_dict.get("content", "")
            if prop in _OGP_KEYS and content:
                self.result[_OGP_KEYS[prop]] = content

            # Fallback description: <meta name="description" content="..." />
            name = attr_dict.get("name", "")
            if (
                name == "description"
                and content
                and "description_fallback" not in self.result
            ):
                self.result["description_fallback"] = content

        elif tag == "link":
            # Favicon: <link rel="icon" href="..." /> or <link rel="shortcut icon" .../>
            rel = attr_dict.get("rel", "").lower()
            href = attr_dict.get("href", "")
            if ("icon" in rel) and href and "favicon" not in self.result:
                self.result["favicon"] = href

        elif tag == "title":
            self._in_title = True
            self._title_chars = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_chars.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._in_title:
            self._in_title = False
            title_text = "".join(self._title_chars).strip()
            if title_text:
                self.result["title_fallback"] = title_text


def _parse_ogp_tags(html: str) -> dict[str, str]:
    """Parse OGP meta tags from an HTML string."""
    parser = _OGPParser()
    parser.feed(html)
    return parser.result


# ============================================================
# Public API
# ============================================================


def _domain(url: str) -> str:
    """Extract the domain portion from a URL."""
    parsed = urlparse(url)
    return parsed.netloc or parsed.hostname or ""


def _fallback(url: str) -> dict:
    """Return a minimal fallback result when OGP fetch fails."""
    return {"url": url, "domain": _domain(url), "fetched": False}


async def fetch_ogp(url: str, *, timeout: float = 5.0) -> dict:
    """Fetch OGP metadata from *url*.

    Returns a dict with OGP fields on success, or a fallback dict on failure.
    Only http/https URLs are allowed; private IPs are rejected.
    """
    parsed = urlparse(url)

    # Scheme check
    if parsed.scheme not in ("http", "https"):
        logger.debug("Rejected non-http(s) URL: %s", url)
        return _fallback(url)

    hostname = parsed.hostname or ""

    # SSRF: reject private/loopback addresses
    if not hostname or _is_private_ip(hostname):
        logger.debug("Rejected private/loopback URL: %s", url)
        return _fallback(url)

    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            headers={
                "User-Agent": "Synapse-Canvas/1.0 (OGP link-preview)",
                "Accept": "text/html, */*;q=0.1",
            },
        ) as client:
            target = url
            for _ in range(_MAX_REDIRECTS):
                async with client.stream("GET", target) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location", "")
                        if not location:
                            return _fallback(url)
                        target = urljoin(target, location)
                        redir_parsed = urlparse(target)
                        redir_host = redir_parsed.hostname or ""
                        if redir_parsed.scheme not in ("http", "https"):
                            logger.debug("Redirect to non-http(s): %s", target)
                            return _fallback(url)
                        if not redir_host or _is_private_ip(redir_host):
                            logger.debug("Redirect to private IP: %s", target)
                            return _fallback(url)
                        continue

                    # Check status
                    if resp.status_code != 200:
                        logger.debug("HTTP %d for %s", resp.status_code, url)
                        return _fallback(url)

                    # Check content type
                    ct = resp.headers.get("content-type", "")
                    if "html" not in ct.lower():
                        logger.debug("Non-HTML content-type for %s: %s", url, ct)
                        return _fallback(url)

                    # Stream limited bytes
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in resp.aiter_bytes():
                        remain = _MAX_READ_BYTES - total
                        if remain <= 0:
                            break
                        chunks.append(chunk[:remain])
                        total += len(chunks[-1])
                    html_text = b"".join(chunks).decode("utf-8", errors="replace")
                    break
            else:
                logger.debug("Too many redirects for %s", url)
                return _fallback(url)

    except (
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.HTTPError,
        OSError,
    ) as exc:
        logger.debug("Failed to fetch %s: %s", url, exc)
        return _fallback(url)

    # Parse OGP tags
    tags = _parse_ogp_tags(html_text)

    result: dict = {
        "url": url,
        "domain": _domain(url),
        "fetched": True,
    }

    # Map OGP fields
    result.update({k: tags[k] for k in _OGP_KEYS.values() if k in tags})

    # Fallback: use <title> / <meta name="description"> when OGP equivalents are missing
    if "og_title" not in result and "title_fallback" in tags:
        result["og_title"] = tags["title_fallback"]
    if "og_description" not in result and "description_fallback" in tags:
        result["og_description"] = tags["description_fallback"]

    # Favicon: resolve relative URLs to absolute
    if "favicon" in tags:
        favicon = tags["favicon"]
        if not favicon.startswith(("http://", "https://")):
            favicon = urljoin(url, favicon)
        result["favicon"] = favicon

    return result
