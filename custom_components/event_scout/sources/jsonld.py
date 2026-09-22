"""schema.org Event JSON-LD source.

Fetches a page and parses every application/ld+json block, picking out
nodes whose @type is Event (or a list containing Event), per design.md
section 2. No BeautifulSoup is used; script blocks are collected with the
standard library html.parser, matching docs/decisions.md.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any

import aiohttp

from ..const import SOURCE_KIND_JSONLD
from ..models import ScoutEvent
from ..vendor import vendor_from_jsonld_event, vendor_from_jsonld_offer
from .base import Source, SourceContext, SourceValidationError


class _JsonLdCollector(HTMLParser):
    """Collect the text content of every application/ld+json script block."""

    def __init__(self) -> None:
        """Set up the collector."""
        super().__init__()
        self._in_target = False
        self.blocks: list[str] = []
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Enter a target script block when its type matches."""
        if tag == "script" and dict(attrs).get("type") == "application/ld+json":
            self._in_target = True
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        """Close a target script block and record its content."""
        if tag == "script" and self._in_target:
            self.blocks.append("".join(self._buffer))
            self._in_target = False

    def handle_data(self, data: str) -> None:
        """Buffer text inside a target script block."""
        if self._in_target:
            self._buffer.append(data)


def _iter_event_nodes(payload: Any) -> list[dict]:
    nodes: list[dict] = []
    if isinstance(payload, dict):
        graph = payload.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                nodes.extend(_iter_event_nodes(item))
        types = payload.get("@type")
        type_list = types if isinstance(types, list) else [types]
        if any(t == "Event" for t in type_list):
            nodes.append(payload)
    elif isinstance(payload, list):
        for item in payload:
            nodes.extend(_iter_event_nodes(item))
    return nodes


def _parse_datetime(value: Any) -> date | datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def _location_fields(node: dict) -> tuple[str | None, str | None, str | None]:
    location = node.get("location")
    if isinstance(location, list):
        location = location[0] if location else None
    if not isinstance(location, dict):
        return None, None, None
    venue_name = location.get("name")
    address = location.get("address")
    if isinstance(address, dict):
        address_text = address.get("streetAddress")
        city = address.get("addressLocality")
    else:
        address_text = address if isinstance(address, str) else None
        city = None
    return venue_name, address_text, city


def events_from_jsonld_payload(html: str, *, url: str, source_name: str, category: str) -> list[ScoutEvent]:
    """Parse JSON-LD Event nodes out of an HTML document."""
    collector = _JsonLdCollector()
    collector.feed(html)

    events: list[ScoutEvent] = []
    for block in collector.blocks:
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue
        for node in _iter_event_nodes(payload):
            start = _parse_datetime(node.get("startDate"))
            if start is None:
                continue
            venue_name, address, city = _location_fields(node)
            vendor = None
            offers = node.get("offers")
            offer_list = offers if isinstance(offers, list) else ([offers] if isinstance(offers, dict) else [])
            for offer in offer_list:
                if isinstance(offer, dict):
                    vendor = vendor_from_jsonld_offer(offer)
                    if vendor:
                        break
            if vendor is None:
                vendor = vendor_from_jsonld_event(node)

            event_id = str(node.get("url") or node.get("@id") or node.get("name") or url)
            events.append(
                ScoutEvent(
                    uid="",
                    series_key="",
                    source_kind=SOURCE_KIND_JSONLD,
                    source_name=source_name,
                    source_event_id=event_id,
                    title=str(node.get("name") or "Untitled event"),
                    description=node.get("description"),
                    url=node.get("url") or url,
                    start=start,
                    end=_parse_datetime(node.get("endDate")),
                    all_day=isinstance(start, date) and not isinstance(start, datetime),
                    venue_name=venue_name,
                    address=address,
                    city=city,
                    category=category,  # type: ignore[arg-type]
                    vendor=vendor,
                )
            )
    return events


class JsonLdSource(Source):
    """Generic schema.org Event JSON-LD source."""

    kind = SOURCE_KIND_JSONLD

    async def async_fetch(self, session: aiohttp.ClientSession, ctx: SourceContext) -> list[ScoutEvent]:
        """Fetch the configured page and parse its JSON-LD Event nodes."""
        url = self.data["url"]
        headers = {"User-Agent": "EventScoutHomeAssistant/1.0 (+https://github.com/trooperthorn/ha_int_event_scout)"}
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                html = await resp.text()
        except aiohttp.ClientError as err:
            raise SourceValidationError(f"Could not fetch JSON-LD page: {err}") from err

        events = events_from_jsonld_payload(html, url=url, source_name=ctx.name, category=ctx.category)
        if not events:
            raise SourceValidationError("No schema.org Event blocks were found on that page")
        return events
