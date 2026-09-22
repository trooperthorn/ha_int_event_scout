"""Tests for dedup.py."""

from __future__ import annotations

from datetime import date

from custom_components.event_scout.dedup import (
    alias_key,
    deduplicate,
    normalize_title,
    series_key,
    similarity_score,
    slugify,
)
from custom_components.event_scout.models import ScoutEvent


def _event(**overrides) -> ScoutEvent:
    base = {
        "uid": "u1",
        "series_key": "",
        "source_kind": "ics",
        "source_name": "Test",
        "source_event_id": "1",
        "title": "The Annual Fall Festival",
        "start": date(2026, 10, 10),
        "venue_name": "Main Park",
        "city": "Exampletown",
        "url": "https://example.com/fall-festival",
    }
    base.update(overrides)
    return ScoutEvent(**base)


def test_normalize_title_strips_stopwords_and_ordinals() -> None:
    # "annual" and "festival" are both in the stopword list (dedup.py), so
    # they, "the", and the ordinal "3rd" are all dropped, leaving "3 fall".
    assert normalize_title("The 3rd Annual Fall Festival") == "3 fall"


def test_normalize_title_strips_year() -> None:
    assert normalize_title("2026 Fall Festival") == normalize_title("2027 Fall Festival")


def test_slugify() -> None:
    assert slugify("Exampletown, TX!") == "exampletown-tx"


def test_series_key_excludes_year() -> None:
    key1 = series_key("2026 Fall Festival", "Exampletown")
    key2 = series_key("2027 Fall Festival", "Exampletown")
    assert key1 == key2


def test_similarity_score_matches_close_titles() -> None:
    a = _event(title="Fall Festival")
    b = _event(title="The Annual Fall Festival", source_event_id="2")
    assert similarity_score(a, b) >= 0.5


def test_deduplicate_merges_same_event_across_sources() -> None:
    a = _event(source_kind="jsonld", source_event_id="a")
    b = _event(source_kind="ics", source_event_id="b", title="Annual Fall Festival")
    winners, alias_map = deduplicate([a, b])
    assert len(winners) == 1
    assert winners[0].source_kind == "jsonld"
    assert alias_map[alias_key(b)] == alias_key(a)


def test_deduplicate_keeps_distinct_events_separate() -> None:
    a = _event(title="Fall Festival", start=date(2026, 10, 10))
    b = _event(title="Winter Market", start=date(2026, 12, 1), source_event_id="2")
    winners, alias_map = deduplicate([a, b])
    assert len(winners) == 2
    assert alias_map == {}


def test_deduplicate_precedence_prefers_manual() -> None:
    a = _event(source_kind="ics", source_event_id="a")
    b = _event(source_kind="manual", source_event_id="b", title="Annual Fall Festival")
    winners, _ = deduplicate([a, b])
    assert winners[0].source_kind == "manual"
