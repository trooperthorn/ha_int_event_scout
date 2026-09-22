"""Tests for coordinator.py."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.event_scout.const import DOMAIN
from custom_components.event_scout.coordinator import EventScoutCoordinator


async def test_coordinator_marks_source_failure_without_failing_others(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(domain=DOMAIN, unique_id="loc", data={"name": "Loc", "horizon_days": 90, "radius_miles": 50})
    entry.add_to_hass(hass)
    entry.runtime_data = None

    coordinator = EventScoutCoordinator(hass, entry, update_interval=timedelta(hours=6))
    await coordinator._async_setup()

    good_day = date.today() + timedelta(days=10)
    entry.subentries = {
        "sub1": _FakeSubentry("source", {"source_kind": "manual", "title": "Bad", "month": "1"}, "Bad manual"),
        "sub2": _FakeSubentry(
            "source",
            {"source_kind": "manual", "title": "Good Event", "month": good_day.month, "day": good_day.day},
            "Good manual",
        ),
    }

    with patch.object(hass.config, "latitude", 30.0), patch.object(hass.config, "longitude", -97.0):
        data = await coordinator._async_update_data()

    assert data.source_status["sub1"].ok is False
    assert data.source_status["sub2"].ok is True
    assert len(data.events) == 1


async def test_coordinator_raises_update_failed_when_every_source_fails(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(domain=DOMAIN, unique_id="loc-fail", data={"name": "LocFail", "horizon_days": 90, "radius_miles": 50})
    entry.add_to_hass(hass)

    coordinator = EventScoutCoordinator(hass, entry, update_interval=timedelta(hours=6))
    await coordinator._async_setup()

    entry.subentries = {
        "sub1": _FakeSubentry("source", {"source_kind": "manual", "title": "Bad", "month": "1"}, "Bad manual"),
    }

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_applies_heuristic_vendor_when_no_explicit(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(domain=DOMAIN, unique_id="loc2", data={"name": "Loc2", "horizon_days": 120, "radius_miles": 50})
    entry.add_to_hass(hass)

    coordinator = EventScoutCoordinator(hass, entry, update_interval=timedelta(hours=6))
    await coordinator._async_setup()

    target_day = date.today() + timedelta(days=30)
    entry.subentries = {
        "sub1": _FakeSubentry(
            "source",
            {"source_kind": "manual", "title": "Local Fest", "category": "festival", "month": target_day.month, "day": target_day.day},
            "Local Fest",
        ),
    }

    data = await coordinator._async_update_data()
    assert len(data.events) == 1
    event = data.events[0]
    assert event.vendor is not None
    assert event.vendor.origin in ("heuristic", "manual")


class _FakeSubentry:
    """Minimal stand-in for a ConfigSubentry, just what the coordinator reads."""

    def __init__(self, subentry_type: str, data: dict, title: str) -> None:
        """Store the fields the coordinator uses."""
        self.subentry_type = subentry_type
        self.data = data
        self.title = title
