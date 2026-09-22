"""Tests for vendor.py."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.event_scout.models import ScoutEvent
from custom_components.event_scout.vendor import (
    _extract_deadline_and_fee,
    extract_visible_text,
    heuristic_vendor_info,
    probe_vendor_pages,
    series_offsets_from_explicit,
    vendor_from_jsonld_event,
    vendor_from_jsonld_offer,
    vendor_from_series_offset,
)

from .conftest import load_fixture_text
from .fake_session import FakeResponse, FakeSession


def _event(category: str = "festival", title: str = "Fall Festival", **overrides) -> ScoutEvent:
    base = {
        "uid": "u1",
        "series_key": "s1",
        "source_kind": "ics",
        "source_name": "Test",
        "source_event_id": "1",
        "title": title,
        "start": date(2027, 6, 1),
        "category": category,
    }
    base.update(overrides)
    return ScoutEvent(**base)


def test_heuristic_juried_festival() -> None:
    event = _event(title="Juried Fine Art Festival")
    vendor = heuristic_vendor_info(event)
    assert vendor.origin == "heuristic"
    assert vendor.confidence == 0.4
    assert vendor.juried is True
    assert vendor.app_open == date(2026, 8, 5)
    assert vendor.app_deadline == date(2026, 12, 3)


def test_heuristic_community_festival() -> None:
    event = _event(title="Community Festival")
    vendor = heuristic_vendor_info(event)
    assert vendor.confidence == 0.4
    assert vendor.app_deadline == date(2027, 4, 2)


def test_heuristic_family_event() -> None:
    event = _event(category="family", title="Family Fun Day")
    vendor = heuristic_vendor_info(event)
    assert vendor.confidence == 0.3


def test_heuristic_other_category_has_no_estimate() -> None:
    event = _event(category="other", title="City Council Meeting")
    vendor = heuristic_vendor_info(event)
    assert vendor.confidence == 0.0
    assert vendor.app_open is None
    assert vendor.app_deadline is None


def test_vendor_from_jsonld_offer() -> None:
    offer = {"name": "Vendor booth", "price": "150", "validFrom": "2026-05-01", "validThrough": "2026-08-01", "url": "https://x/vendors"}
    vendor = vendor_from_jsonld_offer(offer)
    assert vendor is not None
    assert vendor.origin == "explicit"
    assert vendor.confidence == 0.9
    assert vendor.app_open == date(2026, 5, 1)
    assert vendor.app_deadline == date(2026, 8, 1)
    assert vendor.booth_fee_text == "$150"


def test_vendor_from_jsonld_offer_ignores_non_vendor_offers() -> None:
    assert vendor_from_jsonld_offer({"name": "General admission", "price": "10"}) is None


def test_vendor_from_jsonld_event_matches_application_name() -> None:
    node = {"name": "Vendor Application", "startDate": "2026-05-01", "endDate": "2026-08-01", "url": "https://x/vendors"}
    vendor = vendor_from_jsonld_event(node)
    assert vendor is not None
    assert vendor.app_deadline == date(2026, 8, 1)


def test_extract_visible_text_skips_script_and_style() -> None:
    html = "<html><head><style>.x{}</style></head><body><script>var x=1;</script><p>Hello world</p></body></html>"
    assert extract_visible_text(html) == "Hello world"


def test_extract_deadline_and_fee() -> None:
    text = extract_visible_text(load_fixture_text("vendors_page.html"))
    result = _extract_deadline_and_fee(text)
    assert result is not None
    deadline, fee = result
    assert deadline == date(2026, 11, 1)
    assert fee == "$200"


def test_extract_deadline_and_fee_returns_none_without_context() -> None:
    assert _extract_deadline_and_fee("Just a normal paragraph with no relevant words.") is None


def test_series_offsets_from_explicit() -> None:
    event = _event(start=date(2026, 6, 1))
    event = event.with_updates(
        vendor=vendor_from_jsonld_offer({"name": "Vendor booth", "validFrom": "2026-01-01", "validThrough": "2026-03-01"})
    )
    deadline_offset, open_offset = series_offsets_from_explicit(event)
    assert deadline_offset == (date(2026, 3, 1) - date(2026, 6, 1)).days
    assert open_offset == (date(2026, 1, 1) - date(2026, 6, 1)).days


def test_series_offsets_from_explicit_none_for_heuristic() -> None:
    event = _event()
    event = event.with_updates(vendor=heuristic_vendor_info(event))
    assert series_offsets_from_explicit(event) == (None, None)


def test_vendor_from_series_offset() -> None:
    event = _event(start=date(2027, 6, 1))
    vendor = vendor_from_series_offset(event, {"deadline_offset_days": -90, "open_offset_days": -200})
    assert vendor is not None
    assert vendor.app_deadline == date(2027, 3, 3)
    assert vendor.app_open == date(2026, 11, 13)


def test_vendor_from_series_offset_empty() -> None:
    event = _event()
    assert vendor_from_series_offset(event, {}) is None


@pytest.mark.asyncio
async def test_probe_vendor_pages_finds_deadline() -> None:
    session = FakeSession()
    session.add("https://example.org/robots.txt", FakeResponse(status=404))
    session.add("https://example.org/vendors", FakeResponse(status=200, _body=load_fixture_text("vendors_page.html")))

    vendor = await probe_vendor_pages(session, "https://example.org/some-event")
    assert vendor is not None
    assert vendor.origin == "explicit"
    assert vendor.confidence == 0.7
    assert vendor.app_deadline == date(2026, 11, 1)


@pytest.mark.asyncio
async def test_probe_vendor_pages_honors_robots_disallow() -> None:
    session = FakeSession()
    session.add("https://example.org/robots.txt", FakeResponse(status=200, _body="User-agent: *\nDisallow: /vendors\n"))
    session.add("https://example.org/vendor-application", FakeResponse(status=404))
    session.add("https://example.org/exhibitors", FakeResponse(status=404))
    session.add("https://example.org/apply", FakeResponse(status=404))

    vendor = await probe_vendor_pages(session, "https://example.org/some-event")
    assert vendor is None
