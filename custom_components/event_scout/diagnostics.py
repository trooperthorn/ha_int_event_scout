"""Diagnostics support for Event Scout."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from . import EventScoutConfigEntry
from .const import CONF_OSRM_URL

TO_REDACT = {"api_key", "password", "app_token", "token", "username", "latitude", "longitude"}


def _redact_osrm_url(url: str | None) -> str | None:
    """Return only the hostname of an OSRM URL, never the full URL, path, or credentials."""
    if not url:
        return url
    return urlparse(url).hostname


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: EventScoutConfigEntry) -> dict[str, Any]:
    """Return diagnostics for an Event Scout config entry."""
    coordinator = entry.runtime_data
    subentries = {subentry_id: async_redact_data(dict(subentry.data), TO_REDACT) for subentry_id, subentry in entry.subentries.items()}
    entry_options = dict(entry.options)
    if CONF_OSRM_URL in entry_options:
        entry_options[CONF_OSRM_URL] = _redact_osrm_url(entry_options[CONF_OSRM_URL])
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": entry_options,
        "subentries": subentries,
        "event_count": len(coordinator.data.events),
        "deadline_count": len(coordinator.data.deadlines),
        "excluded_counts": coordinator.data.excluded_counts,
        "source_status": {
            subentry_id: {
                "ok": status.ok,
                "error": status.error,
                "event_count": status.event_count,
            }
            for subentry_id, status in coordinator.data.source_status.items()
        },
        "store": coordinator.store.as_diagnostics(),
        # last_osrm_error is built in coordinator.py without ever including
        # the raw exception text, so it never carries a URL to redact here.
        "last_osrm_error": coordinator.last_osrm_error,
    }
