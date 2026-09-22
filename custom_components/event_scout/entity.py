"""Base entity for Event Scout, providing the shared device."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EventScoutCoordinator


class EventScoutEntity(CoordinatorEntity[EventScoutCoordinator]):
    """Base entity for all Event Scout entities, sharing one service device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EventScoutCoordinator) -> None:
        """Initialize the entity and its shared device info."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )
