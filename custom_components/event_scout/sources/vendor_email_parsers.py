"""Parsers for vendor deadline digest emails: ZAPP, FestivalNet, and a generic fallback.

Per docs/design-optional-sources.md section 2, no real ZAPP or FestivalNet
email was available at build time; both fixtures are constructed from the
layout described on the vendors' help pages (docs/unverified.md). Every
parser must tolerate a mismatched or unexpected email: return an empty list
rather than raising, so one odd message never breaks the whole fetch.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Protocol

from ..const import SOURCE_KIND_VENDOR_EMAIL, VENDOR_ORIGIN_EXPLICIT
from ..models import ScoutEvent, VendorInfo

_DATE_PATTERNS = (
    "%B %d, %Y",
    "%B %d %Y",
    "%b %d, %Y",
    "%b %d %Y",
    "%m/%d/%Y",
    "%Y-%m-%d",
)


class _TextExtractor(HTMLParser):
    """Extract visible text from an HTML email body, matching vendor.py's approach."""

    def __init__(self) -> None:
        """Set up the extractor."""
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        """Collect visible text chunks."""
        text = data.strip()
        if text:
            self._parts.append(text)

    @property
    def text(self) -> str:
        """Return the collected text, one chunk per line."""
        return "\n".join(self._parts)


def html_to_text(html: str) -> str:
    """Convert an HTML email body to plain text using the standard library only."""
    extractor = _TextExtractor()
    extractor.feed(html)
    return extractor.text


def _parse_date(text: str) -> date | None:
    text = text.strip().rstrip(".,")
    for fmt in _DATE_PATTERNS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


class VendorEmailParser(Protocol):
    """Callable signature every vendor-email parser implements."""

    def __call__(self, body: str, *, from_domain: str, message_id: str, ctx_name: str, category: str) -> list[ScoutEvent]: ...


_ZAPP_BLOCK_RE = re.compile(
    r"(?P<title>[^\n]+)\n"
    r"(?P<city>[A-Za-z .'-]+),\s*(?P<state>[A-Z]{2})\n"
    r".*?Deadline:\s*(?P<deadline>[A-Za-z0-9 ,/-]+?)\n"
    r"(?:.*?Fee:\s*(?P<fee>\$[0-9.,]+))?"
    r".*?(?P<url>https?://(?:www\.)?zapplication\.org/event-info\.php\?ID=\d+)",
    re.IGNORECASE | re.DOTALL,
)


def parse_zapp(body: str, *, from_domain: str, message_id: str, ctx_name: str, category: str) -> list[ScoutEvent]:
    """Parse ZAPP's weekly deadline digest email into ScoutEvents."""
    events: list[ScoutEvent] = []
    for index, match in enumerate(_ZAPP_BLOCK_RE.finditer(body)):
        deadline = _parse_date(match.group("deadline"))
        if deadline is None:
            continue
        fee_text = match.group("fee")
        vendor = VendorInfo(
            available="yes",
            app_deadline=deadline,
            app_url=match.group("url"),
            jury_fee_text=fee_text,
            origin=VENDOR_ORIGIN_EXPLICIT,
            confidence=0.8,
        )
        events.append(
            ScoutEvent(
                uid="",
                series_key="",
                source_kind=SOURCE_KIND_VENDOR_EMAIL,
                source_name=ctx_name,
                source_event_id=f"{message_id}:{index}",
                title=match.group("title").strip(),
                url=match.group("url"),
                start=deadline,
                all_day=True,
                city=match.group("city").strip(),
                state=match.group("state").strip(),
                category=category,  # type: ignore[arg-type]
                vendor=vendor,
            )
        )
    return events


_FESTIVALNET_BLOCK_RE = re.compile(
    r"(?P<title>[^\n]+)\n"
    r"(?P<dates>[A-Za-z0-9 ,-]+)\n"
    r"(?P<city>[A-Za-z .'-]+),\s*(?P<state>[A-Z]{2})\n"
    r".*?Deadline:\s*(?P<deadline>[A-Za-z0-9 ,/-]+?)\n"
    r".*?(?P<url>https?://(?:www\.)?festivalnet\.com/event/[A-Za-z0-9/_-]+)",
    re.IGNORECASE | re.DOTALL,
)


def parse_festivalnet(body: str, *, from_domain: str, message_id: str, ctx_name: str, category: str) -> list[ScoutEvent]:
    """Parse FestivalNet's Calls for Artists / deadline reminder newsletter into ScoutEvents."""
    events: list[ScoutEvent] = []
    for index, match in enumerate(_FESTIVALNET_BLOCK_RE.finditer(body)):
        deadline = _parse_date(match.group("deadline"))
        if deadline is None:
            continue
        vendor = VendorInfo(
            available="yes",
            app_deadline=deadline,
            app_url=match.group("url"),
            origin=VENDOR_ORIGIN_EXPLICIT,
            confidence=0.8,
        )
        events.append(
            ScoutEvent(
                uid="",
                series_key="",
                source_kind=SOURCE_KIND_VENDOR_EMAIL,
                source_name=ctx_name,
                source_event_id=f"{message_id}:{index}",
                title=match.group("title").strip(),
                url=match.group("url"),
                start=deadline,
                all_day=True,
                city=match.group("city").strip(),
                state=match.group("state").strip(),
                category=category,  # type: ignore[arg-type]
                vendor=vendor,
            )
        )
    return events


_GENERIC_TRIGGER_RE = re.compile(r"\b(deadline|due|closes|apply by)\b", re.IGNORECASE)
_GENERIC_DATE_RE = re.compile(r"\b(?:[A-Z][a-z]+ \d{1,2},? \d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})\b")


def parse_generic(body: str, *, from_domain: str, message_id: str, ctx_name: str, category: str) -> list[ScoutEvent]:
    """Find a date within 200 characters of a deadline-shaped keyword and pair it with the nearest preceding line."""
    events: list[ScoutEvent] = []
    lines = [line for line in body.splitlines() if line.strip()]
    index = 0
    for trigger in _GENERIC_TRIGGER_RE.finditer(body):
        window_start = max(0, trigger.start() - 200)
        window_end = min(len(body), trigger.end() + 200)
        window = body[window_start:window_end]
        date_match = _GENERIC_DATE_RE.search(window)
        if date_match is None:
            continue
        deadline = _parse_date(date_match.group(0))
        if deadline is None:
            continue

        preceding_offset = body.rfind("\n", 0, trigger.start())
        title = None
        if preceding_offset != -1:
            candidate_lines = [line.strip() for line in body[:preceding_offset].splitlines() if line.strip()]
            if candidate_lines:
                title = candidate_lines[-1]
        if not title and lines:
            title = lines[0]
        if not title:
            continue

        vendor = VendorInfo(available="yes", app_deadline=deadline, origin=VENDOR_ORIGIN_EXPLICIT, confidence=0.5)
        events.append(
            ScoutEvent(
                uid="",
                series_key="",
                source_kind=SOURCE_KIND_VENDOR_EMAIL,
                source_name=ctx_name,
                source_event_id=f"{message_id}:{index}",
                title=title,
                start=deadline,
                all_day=True,
                category=category,  # type: ignore[arg-type]
                vendor=vendor,
            )
        )
        index += 1
    return events


PARSERS: dict[str, VendorEmailParser] = {
    "zapp": parse_zapp,
    "festivalnet": parse_festivalnet,
    "generic": parse_generic,
}
