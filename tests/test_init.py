"""Tests for __init__.py: setup, unload, and services."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.event_scout.const import DOMAIN
from custom_components.event_scout.models import DeadlineAlert, ScoutData, ScoutEvent, VendorInfo


def _event() -> ScoutEvent:
    return ScoutEvent(
        uid="u1",
        series_key="s1",
        source_kind="manual",
        source_name="Test",
        source_event_id="1",
        title="Fall Festival",
        start=date(2026, 10, 1),
        category="festival",
        vendor=VendorInfo(app_deadline=date(2026, 9, 25), app_url="https://example.com/apply", origin="explicit", confidence=0.9),
    )


async def test_setup_unload_entry(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(domain=DOMAIN, unique_id="loc", data={"name": "Loc"})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.event_scout.coordinator.EventScoutCoordinator._async_update_data",
        AsyncMock(return_value=ScoutData()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_get_digest_service_returns_response(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(domain=DOMAIN, unique_id="loc", data={"name": "Loc"})
    entry.add_to_hass(hass)

    event = _event()
    alert = DeadlineAlert(event=event, alert_kind="deadline", when=date(2026, 9, 25), days=3)
    data = ScoutData(events=[event], deadlines=[alert])

    with patch(
        "custom_components.event_scout.coordinator.EventScoutCoordinator._async_update_data",
        AsyncMock(return_value=data),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    response = await hass.services.async_call(DOMAIN, "get_digest", {"period": "daily"}, blocking=True, return_response=True)
    assert response["period"] == "daily"


async def test_set_vendor_info_service_stores_override(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(domain=DOMAIN, unique_id="loc", data={"name": "Loc"})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.event_scout.coordinator.EventScoutCoordinator._async_update_data",
        AsyncMock(return_value=ScoutData()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        "set_vendor_info",
        {"uid": "u1", "available": "yes", "app_deadline": "2026-11-01"},
        blocking=True,
    )
    coordinator = entry.runtime_data
    override = coordinator.store.get_override("u1")
    assert override is not None
    assert override.app_deadline == date(2026, 11, 1)


async def test_send_digest_and_send_alerts_call_notify(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(domain=DOMAIN, unique_id="loc", data={"name": "Loc"}, options={"notify_service": "phone"})
    entry.add_to_hass(hass)

    calls = []
    hass.services.async_register("notify", "phone", lambda call: calls.append(call.data))

    event = _event()
    alert = DeadlineAlert(event=event, alert_kind="deadline", when=date(2026, 9, 25), days=3)
    data = ScoutData(events=[event], deadlines=[alert])

    with patch(
        "custom_components.event_scout.coordinator.EventScoutCoordinator._async_update_data",
        AsyncMock(return_value=data),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    await hass.services.async_call(DOMAIN, "send_digest", {"period": "daily"}, blocking=True)
    await hass.services.async_call(DOMAIN, "send_alerts", {}, blocking=True)
    await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
    await hass.async_block_till_done()

    assert len(calls) == 2


async def test_send_digest_requires_notify_service(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(domain=DOMAIN, unique_id="loc", data={"name": "Loc"})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.event_scout.coordinator.EventScoutCoordinator._async_update_data",
        AsyncMock(return_value=ScoutData()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    from homeassistant.exceptions import ServiceValidationError

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "send_digest", {"period": "daily"}, blocking=True)


async def test_notification_add_cal_action_calls_create_event(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(domain=DOMAIN, unique_id="loc", data={"name": "Loc"}, options={"target_calendar": "calendar.target"})
    entry.add_to_hass(hass)

    event = _event()
    data = ScoutData(events=[event])

    calls = []

    with patch(
        "custom_components.event_scout.coordinator.EventScoutCoordinator._async_update_data",
        AsyncMock(return_value=data),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    hass.services.async_register("calendar", "create_event", lambda call: calls.append(call.data))

    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": "EVENT_SCOUT_ADD_CAL", "action_data": {"tag": "event_scout_u1_deadline_3", "uid": "u1"}},
    )
    await hass.async_block_till_done()
    assert len(calls) == 1


async def test_notification_dismiss_action_records_tag(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(domain=DOMAIN, unique_id="loc", data={"name": "Loc"})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.event_scout.coordinator.EventScoutCoordinator._async_update_data",
        AsyncMock(return_value=ScoutData()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    coordinator = entry.runtime_data
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": "EVENT_SCOUT_DISMISS", "action_data": {"tag": "event_scout_u1_deadline_3", "uid": "u1"}},
    )
    await hass.async_block_till_done()
    assert coordinator.store.is_dismissed("event_scout_u1_deadline_3")
