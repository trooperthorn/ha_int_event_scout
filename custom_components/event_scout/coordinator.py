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

from .area import AreaFilter
from .const import (
    ALERT_KIND_DEADLINE,
    ALERT_KIND_OPENS,
    ALERT_KIND_RECONNAISSANCE,
    CONF_AREA_MODE,
    CONF_AVERAGE_SPEED_MPH,
    CONF_CITIES,
    CONF_COUNTIES,
    CONF_DISTANCE_LIMIT,
    CONF_DISTANCE_METRIC,
    CONF_HORIZON_DAYS,
    CONF_INCLUDE_UNLOCATED,
    CONF_OSRM_URL,
    CONF_RADIUS_MILES,
    CONF_RECONNAISSANCE_DAYS,
    CONF_ROAD_FACTOR,
    CONF_VENDOR_LEAD_DAYS,
    DEFAULT_AREA_MODE,
    DEFAULT_AVERAGE_SPEED_MPH,
    DEFAULT_CITIES,
    DEFAULT_COUNTIES,
    DEFAULT_DISTANCE_LIMIT,
    DEFAULT_DISTANCE_METRIC,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_INCLUDE_UNLOCATED,
    DEFAULT_OSRM_URL,
    DEFAULT_RADIUS_MILES,
    DEFAULT_RECONNAISSANCE_DAYS,
    DEFAULT_ROAD_FACTOR,
    DEFAULT_VENDOR_LEAD_DAYS,
    DISTANCE_METRIC_STRAIGHT_LINE,
    DISTANCE_ORIGIN_ESTIMATED,
    DISTANCE_ORIGIN_ROUTED,
    DISTANCE_ORIGIN_STRAIGHT,
    DOMAIN,
    LOGGER,
    SOURCE_FETCH_TIMEOUT,
    VENDOR_AVAILABLE_UNKNOWN,
    VENDOR_ORIGIN_MANUAL,
)
from .county import CountyResolver
from .dedup import alias_key, deduplicate, series_key
from .geo import OSRMClient, OSRMError, estimate_drive, haversine_miles
from .models import DeadlineAlert, ScoutData, ScoutEvent, SourceStatus
from .sources import SourceContext, get_source
from .store import EventScoutStore
from .vendor import heuristic_vendor_info, series_offsets_from_explicit, vendor_from_series_offset

if TYPE_CHECKING:
    from . import EventScoutConfigEntry


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
        self.last_osrm_error: str | None = None

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
        within_horizon = [e for e in raw_events if today <= e.start_date <= horizon_end]

        filtered, excluded_counts = await self._apply_area_filter(within_horizon, session=session, hub_lat=hub_lat, hub_lon=hub_lon)

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
            excluded_counts=excluded_counts,
        )

    async def _apply_area_filter(
        self,
        events: list[ScoutEvent],
        *,
        session,  # noqa: ANN001
        hub_lat: float | None,
        hub_lon: float | None,
    ) -> tuple[list[ScoutEvent], dict[str, int]]:
        """Compute distance and county for every event with coordinates, then apply AreaFilter."""
        entry = self.config_entry
        options = entry.options
        data = entry.data

        distance_metric = options.get(CONF_DISTANCE_METRIC, DEFAULT_DISTANCE_METRIC)
        if CONF_DISTANCE_LIMIT in options:
            distance_limit = options[CONF_DISTANCE_LIMIT]
        else:
            # Seed from the legacy radius_miles hub data key on first load; no
            # migration version bump is needed since options are additive.
            distance_limit = (
                data.get(CONF_RADIUS_MILES, DEFAULT_RADIUS_MILES) if distance_metric == DISTANCE_METRIC_STRAIGHT_LINE else DEFAULT_DISTANCE_LIMIT
            )
        road_factor = options.get(CONF_ROAD_FACTOR, DEFAULT_ROAD_FACTOR)
        average_speed_mph = options.get(CONF_AVERAGE_SPEED_MPH, DEFAULT_AVERAGE_SPEED_MPH)
        osrm_url = options.get(CONF_OSRM_URL, DEFAULT_OSRM_URL)
        cities = options.get(CONF_CITIES, DEFAULT_CITIES)
        counties = options.get(CONF_COUNTIES, DEFAULT_COUNTIES)
        area_mode = options.get(CONF_AREA_MODE, DEFAULT_AREA_MODE)
        include_unlocated = options.get(CONF_INCLUDE_UNLOCATED, DEFAULT_INCLUDE_UNLOCATED)

        area_filter = AreaFilter(
            mode=area_mode,
            cities=cities,
            counties=counties,
            distance_metric=distance_metric,
            distance_limit=distance_limit,
            include_unlocated=include_unlocated,
        )

        with_geo: list[ScoutEvent] = []
        if hub_lat is None or hub_lon is None:
            with_geo = list(events)
        else:
            needs_drive = distance_metric != DISTANCE_METRIC_STRAIGHT_LINE and distance_limit > 0
            osrm_client = OSRMClient(osrm_url) if osrm_url else None
            resolver = CountyResolver(self.store) if counties else None

            for event in events:
                if event.latitude is None or event.longitude is None:
                    with_geo.append(event)
                    continue

                straight_miles = haversine_miles(hub_lat, hub_lon, event.latitude, event.longitude)
                updates: dict = {"distance_miles": straight_miles}

                if needs_drive:
                    drive_miles, drive_minutes, origin = await self._resolve_drive(
                        session, osrm_client, hub_lat, hub_lon, event.latitude, event.longitude, straight_miles, road_factor, average_speed_mph
                    )
                    updates.update(drive_miles=drive_miles, drive_minutes=drive_minutes, distance_origin=origin)
                else:
                    updates["distance_origin"] = DISTANCE_ORIGIN_STRAIGHT

                if resolver is not None:
                    updates["county"] = await resolver.async_resolve(session, event.latitude, event.longitude)

                with_geo.append(event.with_updates(**updates))

        excluded_counts: dict[str, int] = {}
        filtered: list[ScoutEvent] = []
        for event in with_geo:
            decision = area_filter.decide(event)
            if decision.included:
                filtered.append(event)
            else:
                reason = decision.reason or "outside_area"
                excluded_counts[reason] = excluded_counts.get(reason, 0) + 1

        return filtered, excluded_counts

    async def _resolve_drive(
        self,
        session,  # noqa: ANN001
        osrm_client: OSRMClient | None,
        hub_lat: float,
        hub_lon: float,
        event_lat: float,
        event_lon: float,
        straight_miles: float,
        road_factor: float,
        average_speed_mph: float,
    ) -> tuple[float, float, str]:
        """Return (drive_miles, drive_minutes, origin), routed when possible, estimated otherwise."""
        if osrm_client is not None:
            cached = self.store.get_route(event_lat, event_lon)
            if cached is not None:
                return cached["drive_miles"], cached["drive_minutes"], DISTANCE_ORIGIN_ROUTED
            try:
                results = await osrm_client.async_table(session, origin=(hub_lat, hub_lon), destinations=[(event_lat, event_lon)])
            except OSRMError as err:
                # Never store the raw exception text: aiohttp errors can embed
                # the full request URL, and diagnostics must only ever show
                # the OSRM server's hostname (see diagnostics.py).
                self.last_osrm_error = f"{err.__class__.__name__}: request to the configured OSRM server failed"
                LOGGER.warning("OSRM table request failed, falling back to the estimate tier: %s", err)
            else:
                result = results[0] if results else None
                if result is not None:
                    self.store.set_route(event_lat, event_lon, drive_miles=result.drive_miles, drive_minutes=result.drive_minutes)
                    return result.drive_miles, result.drive_minutes, DISTANCE_ORIGIN_ROUTED

        drive_miles, drive_minutes = estimate_drive(straight_miles, road_factor=road_factor, average_speed_mph=average_speed_mph)
        return drive_miles, drive_minutes, DISTANCE_ORIGIN_ESTIMATED

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
