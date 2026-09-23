"""Distance helpers: straight-line haversine, the no-network road estimate, and the OSRM table client."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import OSRM_MAX_DESTINATIONS_PER_REQUEST, OSRM_TABLE_PATH

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance between two points, in miles."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def estimate_drive(straight_line_miles: float, *, road_factor: float, average_speed_mph: float) -> tuple[float, float]:
    """Return an estimated (drive_miles, drive_minutes) without any network call.

    This is a labeled estimate, not a routed figure: straight-line distance is
    multiplied by a road factor to approximate road-network travel, and minutes
    are derived from an assumed average speed. See docs/decisions.md for why
    this is the default tier.
    """
    drive_miles = straight_line_miles * road_factor
    drive_minutes = (drive_miles / average_speed_mph) * 60 if average_speed_mph > 0 else 0.0
    return drive_miles, drive_minutes


class OSRMError(Exception):
    """Raised when the OSRM table service cannot be used for a batch."""


@dataclass(frozen=True, kw_only=True)
class RouteResult:
    """One destination's routed distance and duration from the hub."""

    drive_miles: float
    drive_minutes: float


class OSRMClient:
    """Thin client for the OSRM table service, batched at OSRM_MAX_DESTINATIONS_PER_REQUEST."""

    def __init__(self, osrm_url: str) -> None:
        """Store the OSRM base URL, without a trailing slash."""
        self._base_url = osrm_url.rstrip("/")

    async def async_table(
        self,
        session: aiohttp.ClientSession,
        *,
        origin: tuple[float, float],
        destinations: list[tuple[float, float]],
    ) -> list[RouteResult | None]:
        """Return one RouteResult per destination, in the same order, batching requests of 50.

        A destination entry is None when OSRM returned null for that pair
        (unreachable in its graph). Raises OSRMError on any HTTP or parse
        failure for a batch; callers fall back to the estimate tier.
        """
        results: list[RouteResult | None] = []
        for start in range(0, len(destinations), OSRM_MAX_DESTINATIONS_PER_REQUEST):
            batch = destinations[start : start + OSRM_MAX_DESTINATIONS_PER_REQUEST]
            results.extend(await self._async_table_batch(session, origin=origin, destinations=batch))
        return results

    async def _async_table_batch(
        self,
        session: aiohttp.ClientSession,
        *,
        origin: tuple[float, float],
        destinations: list[tuple[float, float]],
    ) -> list[RouteResult | None]:
        coord_pairs = [origin, *destinations]
        coords = ";".join(f"{lon},{lat}" for lat, lon in coord_pairs)
        url = self._base_url + OSRM_TABLE_PATH.format(coords=coords)
        try:
            async with session.get(url) as resp:
                resp.raise_for_status()
                payload: dict[str, Any] = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise OSRMError(str(err)) from err

        if payload.get("code") != "Ok":
            raise OSRMError(f"OSRM returned code {payload.get('code')}")

        try:
            distances = payload["distances"][0]
            durations = payload["durations"][0]
        except (KeyError, IndexError, TypeError) as err:
            raise OSRMError("Malformed OSRM table response") from err

        # Row 0 (source to itself) is dropped; the rest line up with destinations.
        distances = distances[1:]
        durations = durations[1:]

        results: list[RouteResult | None] = []
        for meters, seconds in zip(distances, durations, strict=True):
            if meters is None or seconds is None:
                results.append(None)
                continue
            results.append(RouteResult(drive_miles=meters / 1609.344, drive_minutes=seconds / 60))
        return results
