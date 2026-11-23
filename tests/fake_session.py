"""A minimal fake aiohttp ClientSession for source-plugin tests.

aioresponses does not track current aiohttp/HA pins reliably across
releases, so source tests fake just the surface area this integration's
sources actually call: session.get(url, ...) as an async context manager
returning an object with .status, .raise_for_status(), .text(), and .json().
"""

from __future__ import annotations

import json as json_module
from dataclasses import dataclass, field
from typing import Any

import aiohttp


@dataclass
class FakeResponse:
    """A minimal stand-in for aiohttp.ClientResponse."""

    status: int = 200
    _body: str = ""
    _json: Any = None

    def raise_for_status(self) -> None:
        """Raise like aiohttp does for a 4xx/5xx status."""
        if self.status >= 400:
            request_info = aiohttp.RequestInfo(
                url=aiohttp.client.URL("https://example.com"), method="GET", headers={}, real_url=aiohttp.client.URL("https://example.com")
            )
            raise aiohttp.ClientResponseError(request_info, (), status=self.status, message="error")

    async def text(self) -> str:
        """Return the body as text."""
        return self._body

    async def json(self) -> Any:
        """Return the body parsed as JSON."""
        if self._json is not None:
            return self._json
        return json_module.loads(self._body)

    async def __aenter__(self) -> FakeResponse:
        """Support `async with session.get(...) as resp`."""
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """No cleanup needed."""
        return None


@dataclass
class FakeSession:
    """A minimal stand-in for aiohttp.ClientSession keyed by exact or prefix URL match."""

    responses: dict[str, FakeResponse] = field(default_factory=dict)
    prefix_responses: dict[str, list[FakeResponse]] = field(default_factory=dict)

    def add(self, url: str, response: FakeResponse) -> None:
        """Register an exact-match response for a URL."""
        self.responses[url] = response

    def add_prefix(self, prefix: str, response: FakeResponse) -> None:
        """Register a response for any URL starting with a prefix, consumed in order."""
        self.prefix_responses.setdefault(prefix, []).append(response)

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        """Return the registered response for this URL."""
        url_str = str(url)
        if url_str in self.responses:
            return self.responses[url_str]
        for prefix, queue in self.prefix_responses.items():
            if url_str.startswith(prefix) and queue:
                return queue.pop(0)
        raise AssertionError(f"No fake response registered for {url_str}")

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        """Return the registered response for this URL; POST reuses the same registry as GET."""
        return self.get(url, **kwargs)
