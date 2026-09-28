"""Hardened HTTP client (standard library only - no third-party network code).

Security controls
-----------------
* HTTPS only, host allow-list (config.ALLOWED_HOSTS) - also enforced on redirects
* TLS certificate verification is always on (never disabled)
* Timeouts, bounded retries with exponential back-off
* Response size cap (config.MAX_RESPONSE_BYTES)
* Detects Cloudflare / HTML block pages and raises BlockedError with a clear message
"""
from __future__ import annotations

import json
import logging
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config

log = logging.getLogger(__name__)


class FetchError(RuntimeError):
    """Network / HTTP failure after all retries."""


class BlockedError(FetchError):
    """EPPO's firewall (Cloudflare) returned a block / challenge page."""


def _check_url(url: str) -> None:
    p = urllib.parse.urlparse(url)
    if p.scheme != "https":
        raise ValueError(f"Only https:// URLs are allowed: {url}")
    if (p.hostname or "").lower() not in config.ALLOWED_HOSTS:
        raise ValueError(f"Host not in allow-list: {p.hostname}")


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        _check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_ctx = ssl.create_default_context()
_opener = urllib.request.build_opener(
    urllib.request.ProxyHandler(),            # respects HTTPS_PROXY if set
    urllib.request.HTTPSHandler(context=_ctx),
    _SafeRedirect(),
)


def _looks_blocked(body: bytes, content_type: str) -> bool:
    if "html" not in content_type.lower():
        return False
    head = body[:4000].decode("utf-8", "ignore").lower()
    return any(s in head for s in ("attention required", "cf-browser-verification",
                                   "sorry, you have been blocked", "just a moment",
                                   "challenge-platform"))


def get_bytes(url: str, *, accept: str = "*/*", retries: int | None = None) -> tuple[bytes, str]:
    """GET a URL and return (body, content_type). Raises FetchError / BlockedError."""
    _check_url(url)
    retries = retries or config.HTTP_RETRIES
    delay = config.HTTP_BACKOFF
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers={
            "User-Agent": config.USER_AGENT,
            "Accept": accept,
            "Accept-Language": "th,en;q=0.8",
            "Cache-Control": "no-cache",
        })
        try:
            with _opener.open(req, timeout=config.HTTP_TIMEOUT) as resp:
                ctype = resp.headers.get("Content-Type", "")
                body = resp.read(config.MAX_RESPONSE_BYTES + 1)
                if len(body) > config.MAX_RESPONSE_BYTES:
                    raise FetchError(f"Response too large (> {config.MAX_RESPONSE_BYTES} bytes): {url}")
                if _looks_blocked(body, ctype):
                    raise BlockedError(
                        "EPPO firewall (Cloudflare) blocked this request. "
                        "See docs/TROUBLESHOOTING.md -> 'Cloudflare 403'.")
                return body, ctype
        except urllib.error.HTTPError as e:
            body = e.read(20000) if hasattr(e, "read") else b""
            if e.code in (403, 429, 503) and _looks_blocked(body, e.headers.get("Content-Type", "")):
                last_err = BlockedError(f"HTTP {e.code} Cloudflare block for {url}")
            elif 400 <= e.code < 500 and e.code not in (408, 429):
                raise FetchError(f"HTTP {e.code} for {url}") from e     # not retryable
            else:
                last_err = FetchError(f"HTTP {e.code} for {url}")
        except BlockedError as e:
            last_err = e
        except (urllib.error.URLError, TimeoutError, ConnectionError, ssl.SSLError) as e:
            last_err = FetchError(f"Network error for {url}: {e}")
        if attempt < retries:
            log.warning("attempt %d/%d failed (%s) - retry in %ss", attempt, retries, last_err, delay)
            time.sleep(delay)
            delay *= 2
    assert last_err is not None
    raise last_err


def get_json(url: str, params: dict | None = None) -> tuple[object, dict]:
    """GET JSON. Returns (parsed_json, info) where info has the final url."""
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    body, ctype = get_bytes(url, accept="application/json")
    try:
        return json.loads(body.decode("utf-8-sig")), {"url": url, "content_type": ctype}
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise FetchError(f"Response from {url} is not valid JSON ({ctype})") from e
