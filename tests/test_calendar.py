"""Tests for calendar.py."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from custom_components.event_scout.calendar import EventsCalendar, VendorDeadlinesCalendar
from custom_components.event_scout.models import DeadlineAlert, ScoutData, ScoutEvent


class _FakeCoordinator:
    def __init__(self, data: ScoutData, entry_id: str = "entry1") -> None:
        self.data = data

        class _Entry:
            def __init__(self, entry_id: str) -> None:
                self.entry_id = entry_id
                self.title = "Event Scout"

        self.config_entry = _Entry(entry_id)


def _event(**overrides) -> ScoutEvent:
    base = {
        "uid": "u1",
        "series_key": "s1",
        "source_kind": "ics",
        "source_name": "Test",
        "source_event_id": "1",
        "title": "Fall Festival",
        "start": date(2026, 10, 1),
        "category": "festival",
    }
    base.update(overrides)
    return ScoutEvent(**base)


async def test_events_calendar_get_events_respects_bounds() -> None:
    events = [_event(start=date(2026, 10, 1)), _event(start=date(2026, 12, 1), source_event_id="2")]
    calendar_entity = EventsCalendar(_FakeCoordinator(ScoutData(events=events)))

    start = datetime(2026, 9, 20)
    end = datetime(2026, 10, 15)
    results = await calendar_entity.async_get_events(None, start, end)
    assert len(results) == 1
    assert results[0].summary == "Fall Festival"


async def test_events_calendar_next_event_property() -> None:
    events = [_event(start=date.today() + timedelta(days=5))]
    calendar_entity = EventsCalendar(_FakeCoordinator(ScoutData(events=events)))
    assert calendar_entity.event is not None


async def test_vendor_deadlines_calendar_get_events() -> None:
    event = _event()
    alerts = [DeadlineAlert(event=event, alert_kind="deadline", when=date(2026, 10, 1), days=14)]
    calendar_entity = VendorDeadlinesCalendar(_FakeCoordinator(ScoutData(deadlines=alerts)))

    start = datetime(2026, 9, 20)
    end = datetime(2026, 10, 15)
    results = await calendar_entity.async_get_events(None, start, end)
    assert len(results) == 1
    assert "Apply:" in results[0].summary
