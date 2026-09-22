"""Tests for sensor.py and binary_sensor.py entity logic."""

from __future__ import annotations

from datetime import date

from custom_components.event_scout.binary_sensor import VendorWindowOpenBinarySensor
from custom_components.event_scout.models import ScoutData, ScoutEvent, VendorInfo
from custom_components.event_scout.sensor import (
    NextVendorDeadlineSensor,
    UpcomingEventsSensor,
    VendorApplicationsOpenSensor,
)


class _Entry:
    def __init__(self) -> None:
        self.entry_id = "entry1"
        self.title = "Event Scout"


class _FakeCoordinator:
    def __init__(self, data: ScoutData) -> None:
        self.data = data
        self.config_entry = _Entry()


def _event(**overrides) -> ScoutEvent:
    base = {
        "uid": "u1",
        "series_key": "s1",
        "source_kind": "manual",
        "source_name": "Test",
        "source_event_id": "1",
        "title": "Fall Festival",
        "start": date(2026, 10, 1),
        "category": "festival",
    }
    base.update(overrides)
    return ScoutEvent(**base)


def test_upcoming_events_sensor_counts_by_category() -> None:
    events = [_event(category="festival"), _event(category="family", source_event_id="2")]
    sensor = UpcomingEventsSensor(_FakeCoordinator(ScoutData(events=events)))
    assert sensor.native_value == 2
    assert sensor.extra_state_attributes["by_category"] == {"festival": 1, "family": 1}


def test_next_vendor_deadline_sensor() -> None:
    from custom_components.event_scout.models import DeadlineAlert

    event = _event(vendor=VendorInfo(app_deadline=date(2026, 11, 1), app_url="https://x", origin="explicit", confidence=0.9))
    alerts = [DeadlineAlert(event=event, alert_kind="deadline", when=date(2026, 11, 1), days=14)]
    sensor = NextVendorDeadlineSensor(_FakeCoordinator(ScoutData(deadlines=alerts)))
    assert sensor.native_value is not None
    assert sensor.extra_state_attributes["title"] == "Fall Festival"


def test_vendor_applications_open_sensor() -> None:
    event = _event(vendor=VendorInfo(available="yes", app_deadline=date(2026, 11, 1), origin="explicit", confidence=0.9))
    sensor = VendorApplicationsOpenSensor(_FakeCoordinator(ScoutData(events=[event])))
    assert sensor.native_value == 1
    assert sensor.extra_state_attributes["items"][0]["title"] == "Fall Festival"


def test_vendor_window_open_binary_sensor() -> None:
    event = _event(vendor=VendorInfo(available="yes", origin="explicit", confidence=0.9))
    sensor = VendorWindowOpenBinarySensor(_FakeCoordinator(ScoutData(events=[event])))
    assert sensor.is_on is True

    closed_event = _event(vendor=VendorInfo(available="no", origin="explicit", confidence=0.9))
    sensor2 = VendorWindowOpenBinarySensor(_FakeCoordinator(ScoutData(events=[closed_event])))
    assert sensor2.is_on is False
