"""Diagnostics support for Event Scout."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from . import EventScoutConfigEntry

TO_REDACT = {"api_key", "password", "app_token", "token", "username", "latitude", "longitude"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: EventScoutConfigEntry) -> dict[str, Any]:
    """Return diagnostics for an Event Scout config entry."""
    coordinator = entry.runtime_data
    subentries = {subentry_id: async_redact_data(dict(subentry.data), TO_REDACT) for subentry_id, subentry in entry.subentries.items()}
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": dict(entry.options),
        "subentries": subentries,
        "event_count": len(coordinator.data.events),
        "deadline_count": len(coordinator.data.deadlines),
        "source_status": {
            subentry_id: {
                "ok": status.ok,
                "error": status.error,
                "event_count": status.event_count,
            }
            for subentry_id, status in coordinator.data.source_status.items()
        },
        "store": coordinator.store.as_diagnostics(),
    }
