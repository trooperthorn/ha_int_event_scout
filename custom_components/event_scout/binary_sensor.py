"""Binary sensor platform for Event Scout."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EventScoutConfigEntry
from .const import VENDOR_AVAILABLE_YES
from .entity import EventScoutEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EventScoutConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Event Scout binary sensor."""
    coordinator = entry.runtime_data
    async_add_entities([VendorWindowOpenBinarySensor(coordinator)])


class VendorWindowOpenBinarySensor(EventScoutEntity, BinarySensorEntity):
    """On when at least one vendor application window is currently open."""

    _attr_translation_key = "vendor_window_open"

    def __init__(self, coordinator) -> None:  # noqa: ANN001
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_vendor_window_open"

    @property
    def is_on(self) -> bool:
        """Return whether any event has an open vendor application window."""
        return any(e.vendor and e.vendor.available == VENDOR_AVAILABLE_YES for e in self.coordinator.data.events)
