"""Tests for diagnostics.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.event_scout.const import DOMAIN
from custom_components.event_scout.diagnostics import async_get_config_entry_diagnostics
from custom_components.event_scout.models import ScoutData


async def test_diagnostics_redacts_secrets(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="loc",
        data={"name": "Loc", "latitude": 30.1, "longitude": -97.1},
        options={"notify_service": "mobile_app_phone"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.event_scout.coordinator.EventScoutCoordinator._async_update_data",
        AsyncMock(return_value=ScoutData()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entry.subentries = {
        "sub1": type("S", (), {"data": {"api_key": "secret-value", "name": "Test"}})(),
    }

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["entry_data"]["latitude"] == "**REDACTED**"
    assert diagnostics["subentries"]["sub1"]["api_key"] == "**REDACTED**"
    assert diagnostics["subentries"]["sub1"]["name"] == "Test"
