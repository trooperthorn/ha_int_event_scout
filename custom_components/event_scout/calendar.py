"""Calendar platform: the events calendar and the vendor deadlines calendar."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EventScoutConfigEntry
from .entity import EventScoutEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EventScoutConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Event Scout calendars."""
    coordinator = entry.runtime_data
    async_add_entities([EventsCalendar(coordinator), VendorDeadlinesCalendar(coordinator)])


class EventsCalendar(EventScoutEntity, CalendarEntity):
    """A calendar of every event within the configured horizon."""

    _attr_translation_key = "events"

    def __init__(self, coordinator) -> None:  # noqa: ANN001
        """Initialize the events calendar."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_events"

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming (or currently active) event."""
        today = datetime.now().date()
        for scout_event in self.coordinator.data.events:
            end = scout_event.end or scout_event.start
            end_date = end.date() if isinstance(end, datetime) else end
            if end_date >= today:
                return _to_calendar_event(scout_event)
        return None

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        """Return every event overlapping the given time range."""
        results = []
        for scout_event in self.coordinator.data.events:
            event_start = scout_event.start
            start_cmp = event_start if isinstance(event_start, datetime) else datetime.combine(event_start, datetime.min.time())
            if start_date <= start_cmp < end_date:
                results.append(_to_calendar_event(scout_event))
        return results


class VendorDeadlinesCalendar(EventScoutEntity, CalendarEntity):
    """A calendar of vendor application alerts (reconnaissance, deadline, opens)."""

    _attr_translation_key = "vendor_deadlines"

    def __init__(self, coordinator) -> None:  # noqa: ANN001
        """Initialize the vendor deadlines calendar."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_vendor_deadlines"

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming deadline alert."""
        today = datetime.now().date()
        upcoming = sorted((a for a in self.coordinator.data.deadlines if a.when >= today), key=lambda a: a.when)
        if not upcoming:
            return None
        return _alert_to_calendar_event(upcoming[0])

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        """Return every deadline alert overlapping the given time range."""
        results = []
        for alert in self.coordinator.data.deadlines:
            alert_dt = datetime.combine(alert.when, datetime.min.time())
            if start_date <= alert_dt < end_date:
                results.append(_alert_to_calendar_event(alert))
        return results


def _to_calendar_event(scout_event) -> CalendarEvent:  # noqa: ANN001
    return CalendarEvent(
        start=scout_event.start,
        end=scout_event.end or scout_event.start,
        summary=scout_event.title,
        description=_description_lines(scout_event),
        location=scout_event.venue_name,
        uid=scout_event.uid,
    )


def _description_lines(scout_event) -> str:  # noqa: ANN001
    lines = [f"Category: {scout_event.category}"]

    if scout_event.drive_miles is not None and scout_event.drive_minutes is not None:
        origin = scout_event.distance_origin
        qualifier = "(estimated)" if origin == "estimated" else "(routed)" if origin == "routed" else ""
        prefix = "about " if origin == "estimated" else ""
        line = f"Drive: {prefix}{scout_event.drive_miles:.0f} mi, {prefix}{scout_event.drive_minutes:.0f} min"
        if qualifier:
            line = f"{line} {qualifier}"
        lines.append(line)

    if scout_event.county:
        lines.append(f"County: {scout_event.county}")

    return "\n".join(lines)


def _alert_to_calendar_event(alert) -> CalendarEvent:  # noqa: ANN001
    estimated = ", estimated" if alert.event.vendor and alert.event.vendor.is_estimated else ""
    summary = f"Apply: {alert.event.title} (deadline {alert.when.isoformat()}{estimated})"
    uid = f"{alert.event.uid}_{alert.alert_kind}_{alert.days}"
    return CalendarEvent(start=alert.when, end=alert.when, summary=summary, uid=uid)
