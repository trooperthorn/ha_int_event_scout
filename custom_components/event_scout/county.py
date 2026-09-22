"""County resolution via the US Census Bureau geocoder, cached in the Store."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import CENSUS_GEOCODER_URL, CENSUS_REQUEST_SPACING_SECONDS, LOGGER
from .store import MISSING, EventScoutStore


def county_name_from_response(payload: dict[str, Any]) -> str | None:
    """Extract the county name from a Census geocoder coordinates response.

    Unverified: the exact key path below (`result.geographies["Counties"][0]
    ["NAME"]`) is taken from the design and Census documentation, not
    confirmed against a live response. See docs/unverified.md.
    """
    try:
        counties = payload["result"]["geographies"]["Counties"]
    except (KeyError, TypeError):
        return None
    if not counties:
        return None
    name = counties[0].get("NAME")
    if not name:
        return None
    # Census returns "Travis County"; the design matches on the name
    # without the word County, so strip it here once.
    if name.endswith(" County"):
        name = name[: -len(" County")]
    return name


class CountyResolver:
    """Resolves and caches county names for coordinates using the Census geocoder."""

    def __init__(self, store: EventScoutStore) -> None:
        """Store the shared cache; a resolver is created fresh each refresh cycle."""
        self._store = store
        self._requested_this_cycle = False

    async def async_resolve(self, session: aiohttp.ClientSession, lat: float, lon: float) -> str | None:
        """Return the resolved county name for a coordinate, using the cache when possible."""
        cached = self._store.get_county(lat, lon)
        if cached is not MISSING:
            return cached

        if self._requested_this_cycle:
            await asyncio.sleep(CENSUS_REQUEST_SPACING_SECONDS)
        self._requested_this_cycle = True

        url = CENSUS_GEOCODER_URL.format(lat=lat, lon=lon)
        try:
            async with session.get(url) as resp:
                resp.raise_for_status()
                payload = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            # Coordinates are not logged: they are the household's location.
            LOGGER.warning("Census geocoder request failed: %s", err)
            return None

        county = county_name_from_response(payload)
        self._store.set_county(lat, lon, county)
        return county
