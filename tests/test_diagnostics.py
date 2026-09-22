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
    assert "excluded_counts" in diagnostics
    assert "last_osrm_error" in diagnostics


async def test_diagnostics_redacts_osrm_url_to_hostname(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="loc2",
        data={"name": "Loc2"},
        options={"osrm_url": "https://user:pass@my-osrm.example.com/some/path"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.event_scout.coordinator.EventScoutCoordinator._async_update_data",
        AsyncMock(return_value=ScoutData()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entry.subentries = {}
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["entry_options"]["osrm_url"] == "my-osrm.example.com"
    assert "user:pass" not in str(diagnostics["entry_options"]["osrm_url"])


async def test_diagnostics_never_includes_a_url_in_last_osrm_error(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="loc3",
        data={"name": "Loc3"},
        options={"osrm_url": "https://my-osrm.example.com"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.event_scout.coordinator.EventScoutCoordinator._async_update_data",
        AsyncMock(return_value=ScoutData()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # coordinator.py builds last_osrm_error without ever embedding the raw
    # exception text, so it never carries a URL for diagnostics to redact.
    entry.runtime_data.last_osrm_error = "ClientError: request to the configured OSRM server failed"
    entry.subentries = {}
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert "https://" not in diagnostics["last_osrm_error"]
    assert diagnostics["last_osrm_error"] == "ClientError: request to the configured OSRM server failed"
