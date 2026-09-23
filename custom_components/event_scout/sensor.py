"""Sensor platform for Event Scout."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import EventScoutConfigEntry
from .area import AreaFilter
from .const import (
    ALERT_KIND_DEADLINE,
    CONF_AREA_MODE,
    CONF_CITIES,
    CONF_COUNTIES,
    CONF_DISTANCE_LIMIT,
    CONF_DISTANCE_METRIC,
    DEFAULT_AREA_MODE,
    DEFAULT_CITIES,
    DEFAULT_COUNTIES,
    DEFAULT_DISTANCE_LIMIT,
    DEFAULT_DISTANCE_METRIC,
    VENDOR_AVAILABLE_YES,
)
from .entity import EventScoutEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EventScoutConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Event Scout sensors."""
    coordinator = entry.runtime_data
    entities: list[EventScoutEntity] = [
        UpcomingEventsSensor(coordinator),
        NextVendorDeadlineSensor(coordinator),
        VendorApplicationsOpenSensor(coordinator),
    ]
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type == "source":
            entities.append(SourceCountSensor(coordinator, subentry_id, subentry.title or subentry_id))
    async_add_entities(entities)


class UpcomingEventsSensor(EventScoutEntity, SensorEntity):
    """Count of events inside the configured horizon."""

    _attr_translation_key = "upcoming_events"

    def __init__(self, coordinator) -> None:  # noqa: ANN001
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_upcoming_events"

    @property
    def native_value(self) -> int:
        """Return the number of events in the horizon."""
        return len(self.coordinator.data.events)

    @property
    def extra_state_attributes(self) -> dict:
        """Return per-category counts and the next event's title."""
        by_category: dict[str, int] = {}
        for event in self.coordinator.data.events:
            by_category[event.category] = by_category.get(event.category, 0) + 1
        next_event = self.coordinator.data.events[0].title if self.coordinator.data.events else None
        options = self.coordinator.config_entry.options
        area_filter = AreaFilter(
            mode=options.get(CONF_AREA_MODE, DEFAULT_AREA_MODE),
            cities=options.get(CONF_CITIES, DEFAULT_CITIES),
            counties=options.get(CONF_COUNTIES, DEFAULT_COUNTIES),
            distance_metric=options.get(CONF_DISTANCE_METRIC, DEFAULT_DISTANCE_METRIC),
            distance_limit=options.get(CONF_DISTANCE_LIMIT, DEFAULT_DISTANCE_LIMIT),
        )
        return {
            "by_category": by_category,
            "next_event": next_event,
            "excluded_counts": self.coordinator.data.excluded_counts,
            "area_summary": area_filter.summary(),
        }


class NextVendorDeadlineSensor(EventScoutEntity, SensorEntity):
    """Timestamp of the soonest upcoming vendor deadline."""

    _attr_translation_key = "next_vendor_deadline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator) -> None:  # noqa: ANN001
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_next_vendor_deadline"

    def _next_deadline_alert(self):  # noqa: ANN202
        deadline_alerts = [a for a in self.coordinator.data.deadlines if a.alert_kind == ALERT_KIND_DEADLINE]
        if not deadline_alerts:
            return None
        return min(deadline_alerts, key=lambda a: a.when)

    @property
    def native_value(self) -> datetime | None:
        """Return the next deadline as a timezone-aware datetime."""
        alert = self._next_deadline_alert()
        if alert is None:
            return None
        return dt_util.start_of_local_day(alert.when)

    @property
    def extra_state_attributes(self) -> dict:
        """Return details about the next deadline."""
        alert = self._next_deadline_alert()
        if alert is None:
            return {}
        vendor = alert.event.vendor
        return {
            "title": alert.event.title,
            "url": vendor.app_url if vendor else None,
            "estimated": bool(vendor and vendor.is_estimated),
            "fee": vendor.booth_fee_text if vendor else None,
        }


class VendorApplicationsOpenSensor(EventScoutEntity, SensorEntity):
    """Count of vendor application windows currently open."""

    _attr_translation_key = "vendor_applications_open"

    def __init__(self, coordinator) -> None:  # noqa: ANN001
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_vendor_applications_open"

    def _open_events(self):  # noqa: ANN202
        return [e for e in self.coordinator.data.events if e.vendor and e.vendor.available == VENDOR_AVAILABLE_YES]

    @property
    def native_value(self) -> int:
        """Return the number of currently open vendor applications."""
        return len(self._open_events())

    @property
    def extra_state_attributes(self) -> dict:
        """Return a summary of each open application."""
        return {
            "items": [
                {
                    "uid": e.uid,
                    "title": e.title,
                    "deadline": e.vendor.app_deadline.isoformat() if e.vendor and e.vendor.app_deadline else None,
                    "url": e.vendor.app_url if e.vendor else None,
                }
                for e in self._open_events()
            ]
        }


class SourceCountSensor(EventScoutEntity, SensorEntity):
    """Count of events contributed by a single source subentry."""

    _attr_translation_key = "source_events"

    def __init__(self, coordinator, subentry_id: str, name: str) -> None:  # noqa: ANN001
        """Initialize the per-source sensor."""
        super().__init__(coordinator)
        self._subentry_id = subentry_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_source_{subentry_id}"
        self._attr_translation_placeholders = {"source_name": name}

    @property
    def _status(self):  # noqa: ANN202
        return self.coordinator.data.source_status.get(self._subentry_id)

    @property
    def native_value(self) -> int:
        """Return how many events this source contributed on the last refresh."""
        status = self._status
        return status.event_count if status else 0

    @property
    def extra_state_attributes(self) -> dict:
        """Return the source's last status."""
        status = self._status
        if status is None:
            return {}
        return {
            "status": "ok" if status.ok else "error",
            "last_success": status.last_success.isoformat() if status.last_success else None,
            "error": status.error,
        }
