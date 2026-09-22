"""Persistent storage for Event Scout: uid aliases, series memory, overrides, dismissals."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import ROUTE_CACHE_MAX_AGE_DAYS, STORE_KEY_PREFIX, STORE_VERSION
from .models import VendorInfo


def _round_coord_key(lat: float, lon: float) -> str:
    """Return the cache key for a coordinate, rounded to three decimals (about 100 m)."""
    return f"{round(lat, 3)},{round(lon, 3)}"


class EventScoutStore:
    """Wraps a single Store instance holding all Event Scout persistence for one entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the store wrapper."""
        self._store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, f"{STORE_KEY_PREFIX}{entry_id}")
        self._data: dict[str, Any] = {
            "uid_aliases": {},
            "series_offsets": {},
            "overrides": {},
            "dismissed": {},
            "county_cache": {},
            "route_cache": {},
        }

    async def async_load(self) -> None:
        """Load persisted data, if any."""
        stored = await self._store.async_load()
        if stored:
            self._data.update(stored)
            for key in ("uid_aliases", "series_offsets", "overrides", "dismissed", "county_cache", "route_cache"):
                self._data.setdefault(key, {})

    async def async_save(self) -> None:
        """Persist the current state."""
        await self._store.async_save(self._data)

    def resolve_uid(self, alias_key: str) -> str | None:
        """Return the uid a given alias key maps to, if any."""
        return self._data["uid_aliases"].get(alias_key)

    def record_alias(self, alias_key: str, uid: str) -> None:
        """Record that an alias key now resolves to the given uid."""
        self._data["uid_aliases"][alias_key] = uid

    def get_series_offset(self, series_key: str) -> dict[str, Any] | None:
        """Return remembered deadline and open offsets for a series."""
        return self._data["series_offsets"].get(series_key)

    def set_series_offset(
        self,
        series_key: str,
        *,
        deadline_offset_days: int | None,
        open_offset_days: int | None,
        seen: str | None = None,
    ) -> None:
        """Remember a series' vendor lead time so next year's edition inherits it."""
        self._data["series_offsets"][series_key] = {
            "deadline_offset_days": deadline_offset_days,
            "open_offset_days": open_offset_days,
            "seen": seen or dt_util.utcnow().isoformat(),
        }

    def get_override(self, uid: str) -> VendorInfo | None:
        """Return a manual vendor override for a uid, if any."""
        raw = self._data["overrides"].get(uid)
        return VendorInfo.from_dict(raw) if raw else None

    def set_override(self, uid: str, vendor: VendorInfo) -> None:
        """Store a manual vendor override for a uid."""
        self._data["overrides"][uid] = vendor.as_dict()

    def is_dismissed(self, tag: str) -> bool:
        """Return whether an alert tag has been dismissed."""
        return tag in self._data["dismissed"]

    def dismiss(self, tag: str) -> None:
        """Mark an alert tag as dismissed."""
        self._data["dismissed"][tag] = dt_util.utcnow().isoformat()

    def prune_dismissed(self, keep_tags: set[str]) -> None:
        """Drop dismissed-tag records that no longer correspond to a live alert."""
        self._data["dismissed"] = {tag: ts for tag, ts in self._data["dismissed"].items() if tag in keep_tags}

    @property
    def dismissed_timestamp(self) -> dict[str, str]:
        """Return the raw dismissed-tag mapping."""
        return dict(self._data["dismissed"])

    def get_county(self, lat: float, lon: float) -> Any:
        """Return a cached county lookup for a coordinate.

        Returns the sentinel `MISSING` when there is no cache entry yet
        (as opposed to a cached "unresolved" result, which is stored as None).
        """
        key = _round_coord_key(lat, lon)
        if key not in self._data["county_cache"]:
            return MISSING
        return self._data["county_cache"][key]

    def set_county(self, lat: float, lon: float, county: str | None) -> None:
        """Cache a county lookup for a coordinate, forever (the geocoder result does not change)."""
        self._data["county_cache"][_round_coord_key(lat, lon)] = county

    def get_route(self, lat: float, lon: float) -> dict[str, Any] | None:
        """Return a cached OSRM route result for a coordinate, if fresh enough."""
        entry = self._data["route_cache"].get(_round_coord_key(lat, lon))
        if entry is None:
            return None
        cached_at = parse_iso(entry.get("cached_at"))
        if cached_at is None:
            return None
        age_days = (dt_util.utcnow() - cached_at).days
        if age_days > ROUTE_CACHE_MAX_AGE_DAYS:
            return None
        return entry

    def set_route(self, lat: float, lon: float, *, drive_miles: float, drive_minutes: float) -> None:
        """Cache an OSRM route result for a coordinate."""
        self._data["route_cache"][_round_coord_key(lat, lon)] = {
            "drive_miles": drive_miles,
            "drive_minutes": drive_minutes,
            "cached_at": dt_util.utcnow().isoformat(),
        }

    def as_diagnostics(self) -> dict[str, Any]:
        """Return a redaction-safe summary for diagnostics."""
        return {
            "uid_alias_count": len(self._data["uid_aliases"]),
            "series_offset_count": len(self._data["series_offsets"]),
            "override_count": len(self._data["overrides"]),
            "dismissed_count": len(self._data["dismissed"]),
            "county_cache_count": len(self._data["county_cache"]),
            "route_cache_count": len(self._data["route_cache"]),
        }


class _MissingType:
    """Sentinel type distinguishing an absent cache entry from a cached None."""

    def __repr__(self) -> str:
        """Return a readable sentinel repr for debugging."""
        return "MISSING"


MISSING = _MissingType()


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO string."""
    return dt_util.utcnow().isoformat()


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO timestamp, returning None on empty input."""
    return dt_util.parse_datetime(value) if value else None
