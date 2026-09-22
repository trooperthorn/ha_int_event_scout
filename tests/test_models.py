"""Tests for models.py."""

from __future__ import annotations

from datetime import date, datetime

from custom_components.event_scout.models import ScoutEvent, VendorInfo


def test_vendor_info_round_trips_through_dict() -> None:
    vendor = VendorInfo(
        available="yes",
        app_open=date(2026, 1, 1),
        app_deadline=date(2026, 3, 1),
        app_url="https://example.com",
        categories=("fine art",),
        juried=True,
        origin="explicit",
        confidence=0.9,
    )
    restored = VendorInfo.from_dict(vendor.as_dict())
    assert restored == vendor


def test_vendor_info_is_estimated() -> None:
    assert VendorInfo(origin="heuristic").is_estimated
    assert not VendorInfo(origin="explicit").is_estimated


def test_scout_event_start_date_for_datetime() -> None:
    event = ScoutEvent(
        uid="u1",
        series_key="s1",
        source_kind="ics",
        source_name="Test",
        source_event_id="1",
        title="Event",
        start=datetime(2026, 9, 23, 10, 0),
    )
    assert event.start_date == date(2026, 9, 23)


def test_scout_event_with_updates_returns_copy() -> None:
    event = ScoutEvent(
        uid="u1",
        series_key="s1",
        source_kind="ics",
        source_name="Test",
        source_event_id="1",
        title="Event",
        start=date(2026, 9, 23),
    )
    updated = event.with_updates(title="New title")
    assert updated.title == "New title"
    assert event.title == "Event"
