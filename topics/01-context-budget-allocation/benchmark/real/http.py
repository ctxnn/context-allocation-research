from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from benchmark.real.artifacts import canonical_json, sha256_text, utc_now
from benchmark.real.constants import ALLOWED_HOSTS


@dataclass(frozen=True)
class HTTPResult:
    url: str
    status: int
    body: Any
    captured_at: str
    sha256: str


class PublicAPIClient:
    """Small allow-listed client for public GitHub, raw GitHub, and PyPI data."""

    def __init__(self, timeout: float = 30.0, max_bytes: int = 8_000_000):
        self.timeout = timeout
        self.max_bytes = max_bytes

    def get(
        self, url: str, *, accept: str = "application/vnd.github+json"
    ) -> HTTPResult:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            raise ValueError(f"URL is outside the public-source allowlist: {url}")
        headers = {"Accept": accept, "User-Agent": "context-budget-benchmark/2"}
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if token and parsed.hostname == "api.github.com":
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(self.max_bytes + 1)
                if len(raw) > self.max_bytes:
                    raise ValueError(f"response exceeded {self.max_bytes} bytes: {url}")
                text = raw.decode("utf-8", errors="replace")
                content_type = response.headers.get("Content-Type", "")
                body = json.loads(text) if "json" in content_type else text
                stable = canonical_json(body) if not isinstance(body, str) else body
                return HTTPResult(
                    url, response.status, body, utc_now(), sha256_text(stable)
                )
        except urllib.error.HTTPError as exc:
            safe = exc.read(2048).decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} from {url}: {safe}") from exc


def github_url(path: str, **query: Any) -> str:
    base = "https://api.github.com/" + path.lstrip("/")
    if query:
        base += "?" + urllib.parse.urlencode(query)
    return base


def pypi_url(project: str) -> str:
    safe = urllib.parse.quote(project, safe="")
    return f"https://pypi.org/pypi/{safe}/json"
