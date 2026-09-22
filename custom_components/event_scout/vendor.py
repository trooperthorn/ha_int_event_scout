"""Vendor application extraction and heuristics.

Extraction order (highest confidence first): explicit manual fields, JSON-LD
offers on the event's own page, an optional probe of a small set of candidate
paths on the event's host. When nothing explicit is found and no series memory
exists, a heuristic table estimates an open and deadline date from the event
date and category; heuristic dates are always labeled as estimates.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp

from .const import (
    CATEGORY_FAMILY,
    CATEGORY_FESTIVAL,
    VENDOR_AVAILABLE_UNKNOWN,
    VENDOR_AVAILABLE_YES,
    VENDOR_ORIGIN_EXPLICIT,
    VENDOR_ORIGIN_HEURISTIC,
    VENDOR_PROBE_PATHS,
)
from .models import ScoutEvent, VendorInfo

_JURIED_KEYWORDS = ("juried", "jury", "fine art", "fine craft")
_DEADLINE_KEYWORDS = ("deadline", "due", "close", "closes", "closing")
_FEE_KEYWORDS = ("booth", "jury", "fee")
_MONEY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?")
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

# Heuristic table: (is_festival, has_juried_keyword_or_is_community) -> (open_offset, deadline_offset, confidence)
# Offsets are negative days relative to the event date.
_HEURISTIC_TABLE: dict[str, tuple[int, int, float]] = {
    "festival_juried": (-300, -180, 0.4),
    "festival_community": (-150, -60, 0.4),
    "family_community": (-90, -45, 0.3),
    "other": (0, 0, 0.0),
}


class _TextExtractor(HTMLParser):
    """Collect visible text from HTML without pulling in BeautifulSoup."""

    def __init__(self) -> None:
        """Set up the accumulator."""
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Track script and style so their contents are not collected as text."""
        if tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        """Stop skipping when a script or style block ends."""
        if tag in ("script", "style") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        """Collect a chunk of visible text."""
        if self._skip_depth == 0 and data.strip():
            self._chunks.append(data.strip())

    @property
    def text(self) -> str:
        """Return the joined visible text."""
        return "\n".join(self._chunks)


def extract_visible_text(html: str) -> str:
    """Return the visible text of an HTML document."""
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text


def vendor_from_jsonld_offer(offer: dict[str, Any]) -> VendorInfo | None:
    """Build a VendorInfo from a JSON-LD offer whose name mentions vendors."""
    name = str(offer.get("name", "")).lower()
    if not any(word in name for word in ("vendor", "exhibitor", "booth")):
        return None
    open_date = _parse_json_date(offer.get("validFrom"))
    deadline = _parse_json_date(offer.get("validThrough"))
    fee = offer.get("price")
    fee_text = f"${fee}" if fee not in (None, "") else None
    return VendorInfo(
        available=VENDOR_AVAILABLE_YES,
        app_open=open_date,
        app_deadline=deadline,
        app_url=offer.get("url"),
        booth_fee_text=fee_text,
        origin=VENDOR_ORIGIN_EXPLICIT,
        confidence=0.9,
    )


def vendor_from_jsonld_event(node: dict[str, Any]) -> VendorInfo | None:
    """Build a VendorInfo from a JSON-LD Event node whose name is a vendor call."""
    name = str(node.get("name", "")).lower()
    if "vendor application" not in name:
        return None
    return VendorInfo(
        available=VENDOR_AVAILABLE_YES,
        app_open=_parse_json_date(node.get("startDate")),
        app_deadline=_parse_json_date(node.get("endDate")),
        app_url=node.get("url"),
        origin=VENDOR_ORIGIN_EXPLICIT,
        confidence=0.9,
    )


def _parse_json_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    match = _DATE_RE.search(value)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


async def probe_vendor_pages(session: aiohttp.ClientSession, event_url: str, *, timeout: int = 15) -> VendorInfo | None:
    """Probe a small set of candidate vendor paths on the event's own host.

    Honors robots.txt by skipping any candidate path it disallows for all
    user agents. Returns the first candidate with recognizable deadline or
    fee text, confidence 0.7 (lower than explicit JSON-LD, per design section 7).
    """
    parsed = urlparse(event_url)
    if not parsed.scheme or not parsed.netloc:
        return None
    base = f"{parsed.scheme}://{parsed.netloc}"
    disallowed = await _fetch_robots_disallow(session, base, timeout=timeout)

    for path in VENDOR_PROBE_PATHS:
        if path in disallowed:
            continue
        url = urljoin(base, path)
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status != 200:
                    continue
                html = await resp.text()
        except (TimeoutError, aiohttp.ClientError):
            continue
        text = extract_visible_text(html)
        found = _extract_deadline_and_fee(text)
        if found is None:
            continue
        deadline, fee_text = found
        return VendorInfo(
            available=VENDOR_AVAILABLE_YES,
            app_deadline=deadline,
            app_url=url,
            booth_fee_text=fee_text,
            origin=VENDOR_ORIGIN_EXPLICIT,
            confidence=0.7,
        )
    return None


async def _fetch_robots_disallow(session: aiohttp.ClientSession, base: str, *, timeout: int) -> set[str]:
    disallowed: set[str] = set()
    try:
        async with session.get(f"{base}/robots.txt", timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return disallowed
            body = await resp.text()
    except (TimeoutError, aiohttp.ClientError):
        return disallowed

    applies = False
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("user-agent:"):
            applies = line.split(":", 1)[1].strip() == "*"
            continue
        if applies and line.lower().startswith("disallow:"):
            value = line.split(":", 1)[1].strip()
            if value:
                disallowed.add(value)
    return disallowed


def _extract_deadline_and_fee(text: str) -> tuple[date | None, str | None] | None:
    lower = text.lower()
    has_deadline_context = any(kw in lower for kw in _DEADLINE_KEYWORDS)
    has_fee_context = any(kw in lower for kw in _FEE_KEYWORDS)
    if not has_deadline_context and not has_fee_context:
        return None

    deadline = None
    date_match = _DATE_RE.search(text)
    if date_match:
        try:
            deadline = date.fromisoformat(date_match.group(1))
        except ValueError:
            deadline = None

    fee_text = None
    money_match = _MONEY_RE.search(text)
    if money_match:
        fee_text = money_match.group(0)

    if deadline is None and fee_text is None:
        return None
    return deadline, fee_text


def heuristic_vendor_info(event: ScoutEvent) -> VendorInfo:
    """Return a heuristic VendorInfo estimate for an event with no explicit data."""
    text = f"{event.title} {event.description or ''}".lower()
    is_juried = any(kw in text for kw in _JURIED_KEYWORDS)

    if event.category == CATEGORY_FESTIVAL:
        key = "festival_juried" if is_juried else "festival_community"
    elif event.category == CATEGORY_FAMILY:
        key = "family_community"
    else:
        key = "other"

    open_offset, deadline_offset, confidence = _HEURISTIC_TABLE[key]
    if confidence == 0.0:
        return VendorInfo(available=VENDOR_AVAILABLE_UNKNOWN, origin=VENDOR_ORIGIN_HEURISTIC, confidence=0.0)

    start = event.start_date
    return VendorInfo(
        available=VENDOR_AVAILABLE_UNKNOWN,
        app_open=start + timedelta(days=open_offset),
        app_deadline=start + timedelta(days=deadline_offset),
        origin=VENDOR_ORIGIN_HEURISTIC,
        confidence=confidence,
        juried=is_juried if key == "festival_juried" else None,
    )


def vendor_from_series_offset(event: ScoutEvent, offset: dict[str, Any]) -> VendorInfo | None:
    """Build a VendorInfo from remembered series offsets, when available."""
    deadline_offset = offset.get("deadline_offset_days")
    open_offset = offset.get("open_offset_days")
    if deadline_offset is None and open_offset is None:
        return None
    start = event.start_date
    return VendorInfo(
        available=VENDOR_AVAILABLE_UNKNOWN,
        app_open=start + timedelta(days=open_offset) if open_offset is not None else None,
        app_deadline=start + timedelta(days=deadline_offset) if deadline_offset is not None else None,
        origin=VENDOR_ORIGIN_HEURISTIC,
        confidence=0.5,
    )


def series_offsets_from_explicit(event: ScoutEvent) -> tuple[int | None, int | None]:
    """Compute day offsets from an explicit VendorInfo, for series memory."""
    if event.vendor is None or event.vendor.origin != VENDOR_ORIGIN_EXPLICIT:
        return None, None
    start = event.start_date
    deadline_offset = (event.vendor.app_deadline - start).days if event.vendor.app_deadline else None
    open_offset = (event.vendor.app_open - start).days if event.vendor.app_open else None
    return deadline_offset, open_offset
