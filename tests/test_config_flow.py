"""Tests for config_flow.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.event_scout.const import DOMAIN


async def test_user_flow_creates_hub_entry(hass) -> None:  # noqa: ANN001
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] == "form"

    result2 = await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "My Event Scout"})
    assert result2["type"] == "create_entry"
    assert result2["title"] == "My Event Scout"
    assert result2["data"]["name"] == "My Event Scout"


async def test_user_flow_aborts_on_duplicate_name(hass) -> None:  # noqa: ANN001
    MockConfigEntry(domain=DOMAIN, unique_id="my event scout", data={"name": "My Event Scout"}).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result2 = await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "My Event Scout"})
    assert result2["type"] == "abort"
    assert result2["reason"] == "already_configured"


async def test_options_flow_updates_options(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(domain=DOMAIN, unique_id="my event scout", data={"name": "My Event Scout"})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.event_scout.coordinator.EventScoutCoordinator._async_update_data",
        AsyncMock(return_value=_empty_scout_data()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"

    result2 = await hass.config_entries.options.async_configure(result["flow_id"], {"notify_service": "mobile_app_phone"})
    assert result2["type"] == "create_entry"
    assert entry.options["notify_service"] == "mobile_app_phone"


async def test_options_flow_accepts_area_filter_fields(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(domain=DOMAIN, unique_id="area event scout", data={"name": "Area Event Scout"})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.event_scout.coordinator.EventScoutCoordinator._async_update_data",
        AsyncMock(return_value=_empty_scout_data()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "area_mode": "all",
            "cities": ["Georgetown", "Round Rock"],
            "counties": ["Williamson"],
            "distance_metric": "driving_minutes",
            "distance_limit": 45,
            "road_factor": 1.25,
            "average_speed_mph": 40,
            "osrm_url": "https://router.project-osrm.org",
        },
    )
    assert result2["type"] == "create_entry"
    assert entry.options["area_mode"] == "all"
    assert entry.options["cities"] == ["Georgetown", "Round Rock"]
    assert entry.options["counties"] == ["Williamson"]
    assert entry.options["distance_metric"] == "driving_minutes"
    assert entry.options["distance_limit"] == 45


async def test_source_subentry_flow_manual(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(domain=DOMAIN, unique_id="my event scout", data={"name": "My Event Scout"})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.event_scout.coordinator.EventScoutCoordinator._async_update_data",
        AsyncMock(return_value=_empty_scout_data()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.subentries.async_init((entry.entry_id, "source"), context={"source": config_entries.SOURCE_USER})
    assert result["type"] == "form"

    result2 = await hass.config_entries.subentries.async_configure(result["flow_id"], {"source_kind": "manual"})
    assert result2["type"] == "form"
    assert result2["step_id"] == "args"

    result3 = await hass.config_entries.subentries.async_configure(
        result2["flow_id"],
        {"name": "Founders Day", "title": "Founders Day", "category": "city_anniversary", "month": 12, "day": 27},
    )
    assert result3["type"] == "create_entry"


def _empty_scout_data():
    from custom_components.event_scout.models import ScoutData

    return ScoutData()
