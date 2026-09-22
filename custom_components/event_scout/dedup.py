"""Deduplication of events collected from several sources.

Blocking groups candidate duplicates by start date and rough location, then
title similarity (plus URL host and venue token bonuses) decides whether two
events in the same block are merged. No third-party fuzzy-matching library is
used; the standard library's difflib.SequenceMatcher is sufficient at this
scale and keeps the dependency list short (see docs/decisions.md).
"""

from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from urllib.parse import urlparse

from .const import (
    SOURCE_KIND_EVENTBRITE,
    SOURCE_KIND_ICS,
    SOURCE_KIND_JSONLD,
    SOURCE_KIND_MANUAL,
    SOURCE_KIND_SOCRATA,
    SOURCE_KIND_TICKETMASTER,
)
from .models import ScoutEvent

MERGE_THRESHOLD = 0.85
GEO_CELL_DEGREES = 0.05

_STOPWORDS = {"annual", "festival", "fest", "the", "a", "an", "of", "and"}
_ORDINAL_RE = re.compile(r"\b(\d+)(st|nd|rd|th)\b", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^\w\s]")
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")

_SOURCE_PRECEDENCE = {
    SOURCE_KIND_MANUAL: 0,
    SOURCE_KIND_JSONLD: 1,
    SOURCE_KIND_SOCRATA: 2,
    SOURCE_KIND_TICKETMASTER: 3,
    SOURCE_KIND_EVENTBRITE: 4,
    SOURCE_KIND_ICS: 5,
}


def normalize_title(title: str) -> str:
    """Return a normalized, token-sorted form of a title for comparison.

    Strips a leading/trailing four-digit year along with ordinal suffixes and
    a small stopword list, so "2026 Fall Festival" and "2027 Fall Festival"
    normalize to the same value: series_key deliberately excludes the year
    (design.md section 6).
    """
    text = _ORDINAL_RE.sub(r"\1", title.lower())
    text = _PUNCT_RE.sub(" ", text)
    tokens = [t for t in text.split() if t and t not in _STOPWORDS and not _YEAR_RE.match(t)]
    return " ".join(sorted(tokens))


def slugify(text: str) -> str:
    """Return a filesystem/id-safe slug for a piece of text."""
    text = _PUNCT_RE.sub(" ", text.lower())
    return "-".join(text.split())


def series_key(title: str, city_or_venue: str | None) -> str:
    """Compute a series key that stays stable across years."""
    return f"{slugify(normalize_title(title))}|{slugify(city_or_venue or '')}"


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _blocking_key(event: ScoutEvent) -> tuple:
    day = event.start_date
    if event.latitude is not None and event.longitude is not None:
        cell = (round(event.latitude / GEO_CELL_DEGREES), round(event.longitude / GEO_CELL_DEGREES))
        return (day, cell)
    return (day, (event.city or "").strip().lower())


def _host(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return None


def _venue_tokens(event: ScoutEvent) -> set[str]:
    if not event.venue_name:
        return set()
    return set(normalize_title(event.venue_name).split())


def similarity_score(a: ScoutEvent, b: ScoutEvent) -> float:
    """Return a 0..1 similarity score used to decide whether to merge two events."""
    ratio = SequenceMatcher(None, normalize_title(a.title), normalize_title(b.title)).ratio()
    score = ratio
    if _host(a.url) and _host(a.url) == _host(b.url):
        score += 0.1
    if _venue_tokens(a) and _venue_tokens(a) & _venue_tokens(b):
        score += 0.1
    return min(score, 1.0)


def _precedence(event: ScoutEvent) -> int:
    return _SOURCE_PRECEDENCE.get(event.source_kind, len(_SOURCE_PRECEDENCE))


def deduplicate(events: list[ScoutEvent]) -> tuple[list[ScoutEvent], dict[str, str]]:
    """Merge duplicate events.

    Returns the deduplicated, winner-only event list plus a mapping of each
    loser's alias key to the winner's alias key, for uid-alias persistence.
    """
    blocks: dict[tuple, list[ScoutEvent]] = {}
    for event in events:
        blocks.setdefault(_blocking_key(event), []).append(event)

    winners: list[ScoutEvent] = []
    alias_map: dict[str, str] = {}

    for block in blocks.values():
        remaining = list(block)
        groups: list[list[ScoutEvent]] = []
        while remaining:
            seed = remaining.pop(0)
            group = [seed]
            still_remaining = []
            for candidate in remaining:
                if similarity_score(seed, candidate) >= MERGE_THRESHOLD:
                    group.append(candidate)
                else:
                    still_remaining.append(candidate)
            remaining = still_remaining
            groups.append(group)

        for group in groups:
            group.sort(key=_precedence)
            winner = group[0]
            winners.append(winner)
            for loser in group[1:]:
                alias_map[alias_key(loser)] = alias_key(winner)

    return winners, alias_map


def alias_key(event: ScoutEvent) -> str:
    """Return a stable key identifying an event's origin, for alias tracking."""
    return f"{event.source_kind}:{event.source_name}:{event.source_event_id}"
