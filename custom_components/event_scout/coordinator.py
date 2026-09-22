"""Coordinator: fetch every source, deduplicate, apply vendor info, compute alerts."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    ALERT_KIND_DEADLINE,
    ALERT_KIND_OPENS,
    ALERT_KIND_RECONNAISSANCE,
    CONF_HORIZON_DAYS,
    CONF_RADIUS_MILES,
    CONF_RECONNAISSANCE_DAYS,
    CONF_VENDOR_LEAD_DAYS,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_RADIUS_MILES,
    DEFAULT_RECONNAISSANCE_DAYS,
    DEFAULT_VENDOR_LEAD_DAYS,
    DOMAIN,
    LOGGER,
    SOURCE_FETCH_TIMEOUT,
    VENDOR_AVAILABLE_UNKNOWN,
    VENDOR_ORIGIN_MANUAL,
)
from .dedup import alias_key, deduplicate, series_key
from .models import DeadlineAlert, ScoutData, ScoutEvent, SourceStatus
from .sources import SourceContext, get_source
from .store import EventScoutStore
from .vendor import heuristic_vendor_info, series_offsets_from_explicit, vendor_from_series_offset

if TYPE_CHECKING:
    from . import EventScoutConfigEntry


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

    radius = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


class EventScoutCoordinator(DataUpdateCoordinator[ScoutData]):
    """Coordinates fetching every configured source and building ScoutData."""

    config_entry: EventScoutConfigEntry

    def __init__(self, hass: HomeAssistant, entry: EventScoutConfigEntry, *, update_interval: timedelta) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=update_interval,
        )
        self.store = EventScoutStore(hass, entry.entry_id)

    async def _async_setup(self) -> None:
        """Load the store once before the first refresh."""
        await self.store.async_load()

    async def _async_update_data(self) -> ScoutData:
        """Run one full coordinator cycle."""
        entry = self.config_entry
        session = async_get_clientsession(self.hass)
        horizon_days = entry.data.get(CONF_HORIZON_DAYS, DEFAULT_HORIZON_DAYS)
        radius_miles = entry.data.get(CONF_RADIUS_MILES, DEFAULT_RADIUS_MILES)
        hub_lat = entry.data.get("latitude", self.hass.config.latitude)
        hub_lon = entry.data.get("longitude", self.hass.config.longitude)

        raw_events: list[ScoutEvent] = []
        statuses: dict[str, SourceStatus] = {}
        any_success = False

        for subentry_id, subentry in entry.subentries.items():
            if subentry.subentry_type != "source":
                continue
            data = dict(subentry.data)
            kind = data.pop("source_kind")
            name = subentry.title or kind
            status = SourceStatus(subentry_id=subentry_id, name=name)
            ctx = SourceContext(
                subentry_id=subentry_id,
                name=name,
                category=data.get("category", "other"),
                latitude=hub_lat,
                longitude=hub_lon,
                radius_miles=radius_miles,
                horizon_days=horizon_days,
            )
            try:
                source = get_source(kind, data)
                async with asyncio.timeout(SOURCE_FETCH_TIMEOUT):
                    fetched = await source.async_fetch(session, ctx)
            except Exception as err:  # noqa: BLE001 - any source failure degrades to a per-source status, not a crash
                status.ok = False
                status.error = str(err)
                LOGGER.warning("Source %s (%s) failed: %s", name, kind, err)
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    f"source_failed_{subentry_id}",
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="source_failed",
                    translation_placeholders={"name": name, "error": str(err)},
                )
            else:
                any_success = True
                status.ok = True
                status.last_success = dt_util.utcnow()
                status.event_count = len(fetched)
                ir.async_delete_issue(self.hass, DOMAIN, f"source_failed_{subentry_id}")
                for event in fetched:
                    if not event.uid:
                        event = event.with_updates(uid=alias_key(event))
                    raw_events.append(event.with_updates(series_key=series_key(event.title, event.city or event.venue_name)))
            statuses[subentry_id] = status

        if entry.subentries and not any_success:
            raise UpdateFailed("Every configured source failed")

        today = date.today()
        horizon_end = today + timedelta(days=horizon_days)
        filtered = [e for e in raw_events if today <= e.start_date <= horizon_end]
        if hub_lat is not None and hub_lon is not None:
            filtered = [
                e
                for e in filtered
                if e.latitude is None or e.longitude is None or _haversine_miles(hub_lat, hub_lon, e.latitude, e.longitude) <= radius_miles
            ]

        deduped, alias_map = deduplicate(filtered)
        for loser_key, winner_key in alias_map.items():
            self.store.record_alias(loser_key, winner_key)

        resolved: list[ScoutEvent] = []
        for event in deduped:
            resolved_uid = self.store.resolve_uid(alias_key(event)) or event.uid
            self.store.record_alias(alias_key(event), resolved_uid)
            resolved.append(event.with_updates(uid=resolved_uid))

        with_vendor = [self._apply_vendor(e) for e in resolved]

        for event in with_vendor:
            deadline_offset, open_offset = series_offsets_from_explicit(event)
            if deadline_offset is not None or open_offset is not None:
                self.store.set_series_offset(event.series_key, deadline_offset_days=deadline_offset, open_offset_days=open_offset)

        entry_options = entry.options
        lead_days = entry_options.get(CONF_VENDOR_LEAD_DAYS, DEFAULT_VENDOR_LEAD_DAYS)
        reconnaissance_days = entry_options.get(CONF_RECONNAISSANCE_DAYS, DEFAULT_RECONNAISSANCE_DAYS)
        deadlines = self._compute_alerts(with_vendor, lead_days=lead_days, reconnaissance_days=reconnaissance_days)

        await self.store.async_save()

        return ScoutData(
            events=sorted(with_vendor, key=lambda e: (e.start_date, e.title)),
            deadlines=deadlines,
            source_status=statuses,
        )

    def _apply_vendor(self, event: ScoutEvent) -> ScoutEvent:
        override = self.store.get_override(event.uid)
        if override is not None:
            return event.with_updates(vendor=override)

        if event.vendor is not None and event.vendor.origin in ("explicit", "manual"):
            return event

        offset = self.store.get_series_offset(event.series_key)
        if offset:
            vendor = vendor_from_series_offset(event, offset)
            if vendor:
                return event.with_updates(vendor=vendor)

        return event.with_updates(vendor=heuristic_vendor_info(event))

    def _compute_alerts(self, events: list[ScoutEvent], *, lead_days: list[int], reconnaissance_days: int) -> list[DeadlineAlert]:
        alerts: list[DeadlineAlert] = []
        today = date.today()

        for event in events:
            vendor = event.vendor
            if vendor is None:
                continue

            if vendor.available == VENDOR_AVAILABLE_UNKNOWN and vendor.origin != VENDOR_ORIGIN_MANUAL:
                recon_date = event.start_date - timedelta(days=reconnaissance_days)
                if recon_date >= today:
                    alerts.append(DeadlineAlert(event=event, alert_kind=ALERT_KIND_RECONNAISSANCE, when=recon_date, days=reconnaissance_days))

            if vendor.app_deadline:
                for days in lead_days:
                    when = vendor.app_deadline - timedelta(days=days)
                    if when >= today:
                        alerts.append(DeadlineAlert(event=event, alert_kind=ALERT_KIND_DEADLINE, when=when, days=days))

            if vendor.app_open and vendor.app_open >= today:
                alerts.append(DeadlineAlert(event=event, alert_kind=ALERT_KIND_OPENS, when=vendor.app_open, days=0))

        tags = {f"event_scout_{a.event.uid}_{a.alert_kind}_{a.days}" for a in alerts}
        self.store.prune_dismissed(tags)
        return [a for a in alerts if not self.store.is_dismissed(f"event_scout_{a.event.uid}_{a.alert_kind}_{a.days}")]
