"""Tests for the source plugins."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.event_scout.sources import SourceContext, SourceValidationError, get_source
from custom_components.event_scout.sources.jsonld import events_from_jsonld_payload
from custom_components.event_scout.sources.manual import ManualSource

from .conftest import load_fixture_text
from .fake_session import FakeResponse, FakeSession


def _ctx(**overrides) -> SourceContext:
    base = {"subentry_id": "sub1", "name": "Test source", "category": "festival", "horizon_days": 90}
    base.update(overrides)
    return SourceContext(**base)


@pytest.mark.asyncio
async def test_ics_source_fetches_and_parses() -> None:
    session = FakeSession()
    session.add("https://example.com/cal.ics", FakeResponse(status=200, _body=load_fixture_text("sample.ics")))
    source = get_source("ics", {"url": "https://example.com/cal.ics"})
    events = await source.async_fetch(session, _ctx())
    assert len(events) == 1
    assert events[0].title == "Winter Market Festival"
    assert events[0].start == date(2026, 12, 15)


@pytest.mark.asyncio
async def test_ics_source_rewrites_webcal() -> None:
    session = FakeSession()
    session.add("https://example.com/cal.ics", FakeResponse(status=200, _body=load_fixture_text("sample.ics")))
    source = get_source("ics", {"url": "webcal://example.com/cal.ics"})
    events = await source.async_fetch(session, _ctx())
    assert len(events) == 1


@pytest.mark.asyncio
async def test_ics_source_raises_on_http_error() -> None:
    session = FakeSession()
    session.add("https://example.com/cal.ics", FakeResponse(status=500))
    source = get_source("ics", {"url": "https://example.com/cal.ics"})
    with pytest.raises(SourceValidationError):
        await source.async_fetch(session, _ctx())


def test_events_from_jsonld_payload_with_vendor() -> None:
    html = load_fixture_text("jsonld_with_vendor.html")
    events = events_from_jsonld_payload(html, url="https://example.org/event", source_name="Test", category="festival")
    assert len(events) == 1
    event = events[0]
    assert event.title == "Hill Country Fall Festival"
    assert event.vendor is not None
    assert event.vendor.origin == "explicit"
    assert event.vendor.app_deadline == date(2026, 8, 1)


def test_events_from_jsonld_payload_without_vendor() -> None:
    html = load_fixture_text("jsonld_without_vendor.html")
    events = events_from_jsonld_payload(html, url="https://example.org/event", source_name="Test", category="community")
    assert len(events) == 1
    assert events[0].vendor is None


@pytest.mark.asyncio
async def test_jsonld_source_raises_without_events() -> None:
    session = FakeSession()
    session.add("https://example.org/no-events", FakeResponse(status=200, _body="<html><body>Nothing here</body></html>"))
    source = get_source("jsonld", {"url": "https://example.org/no-events"})
    with pytest.raises(SourceValidationError):
        await source.async_fetch(session, _ctx())


@pytest.mark.asyncio
async def test_socrata_source_maps_fields() -> None:
    session = FakeSession()
    session.add_prefix(
        "https://data.austintexas.gov/resource/p9ma-z6y9.json",
        FakeResponse(status=200, _body=load_fixture_text("socrata_response.json")),
    )
    source = get_source(
        "socrata",
        {
            "domain": "data.austintexas.gov",
            "dataset_id": "p9ma-z6y9",
            "field_title": "event_name",
            "field_start": "start_date",
            "field_end": "end_date",
            "field_url": "website",
            "field_venue": "venue",
        },
    )
    events = await source.async_fetch(session, _ctx())
    assert len(events) == 2
    assert events[0].title == "Convention Center Trade Show"
    assert events[0].venue_name == "Austin Convention Center"


@pytest.mark.asyncio
async def test_ticketmaster_source_maps_family_event() -> None:
    session = FakeSession()
    session.add_prefix(
        "https://app.ticketmaster.com/discovery/v2/events.json",
        FakeResponse(status=200, _body=load_fixture_text("ticketmaster_response.json")),
    )
    source = get_source("ticketmaster", {"api_key": "key", "segments": ["Family"]})
    events = await source.async_fetch(session, _ctx(latitude=30.0, longitude=-97.0, radius_miles=50))
    assert len(events) == 1
    assert events[0].category == "family"
    assert events[0].cost_text == "$10-$25"


@pytest.mark.asyncio
async def test_ticketmaster_source_requires_coordinates() -> None:
    source = get_source("ticketmaster", {"api_key": "key"})
    with pytest.raises(SourceValidationError):
        await source.async_fetch(FakeSession(), _ctx(latitude=None, longitude=None))


@pytest.mark.asyncio
async def test_eventbrite_source_maps_events() -> None:
    session = FakeSession()
    session.add_prefix(
        "https://www.eventbriteapi.com/v3/organizations/12345/events/",
        FakeResponse(status=200, _body=load_fixture_text("eventbrite_response.json")),
    )
    source = get_source("eventbrite", {"token": "tok", "organization_ids": "12345"})
    events = await source.async_fetch(session, _ctx())
    assert len(events) == 1
    assert events[0].title == "Downtown Night Market"
    assert events[0].is_free is True
    assert events[0].address == "123 Main St, Exampletown, TX"


@pytest.mark.asyncio
async def test_eventbrite_source_requires_organization_ids() -> None:
    source = get_source("eventbrite", {"token": "tok", "organization_ids": ""})
    with pytest.raises(SourceValidationError):
        await source.async_fetch(FakeSession(), _ctx())


@pytest.mark.asyncio
async def test_eventbrite_source_filters_by_venue() -> None:
    session = FakeSession()
    session.add_prefix(
        "https://www.eventbriteapi.com/v3/organizations/12345/events/",
        FakeResponse(status=200, _body=load_fixture_text("eventbrite_response.json")),
    )
    source = get_source("eventbrite", {"token": "tok", "organization_ids": "12345", "venue_ids": "other-venue"})
    events = await source.async_fetch(session, _ctx())
    assert events == []


@pytest.mark.asyncio
async def test_manual_source_month_day() -> None:
    source = ManualSource({"title": "Founders Day", "month": 12, "day": 27, "city": "Austin"})
    events = await source.async_fetch(FakeSession(), _ctx(horizon_days=120))
    assert len(events) == 1
    assert events[0].start.month == 12
    assert events[0].start.day == 27


@pytest.mark.asyncio
async def test_manual_source_nth_weekday() -> None:
    source = ManualSource({"title": "Market Day", "month": 10, "weekday": 5, "nth": 1})
    events = await source.async_fetch(FakeSession(), _ctx(horizon_days=60))
    assert len(events) == 1
    assert events[0].start.weekday() == 5


@pytest.mark.asyncio
async def test_manual_source_validate_requires_recurrence() -> None:
    source = ManualSource({"title": "Bad"})
    with pytest.raises(SourceValidationError):
        await source.async_validate(FakeSession(), _ctx())


@pytest.mark.asyncio
async def test_manual_source_with_vendor_fields() -> None:
    source = ManualSource(
        {
            "title": "Founders Day",
            "month": 12,
            "day": 27,
            "vendor_deadline": "2026-11-01",
            "vendor_open": "2026-08-01",
            "vendor_url": "https://example.com/apply",
        }
    )
    events = await source.async_fetch(FakeSession(), _ctx(horizon_days=120))
    assert events[0].vendor is not None
    assert events[0].vendor.origin == "manual"
    assert events[0].vendor.app_deadline == date(2026, 11, 1)
