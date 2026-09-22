"""Ticketmaster Discovery API v2 source.

Uses the hub's latitude, longitude, and radius; segments and keyword narrow
the search per design.md section 2. Coverage is ticketed events only, a
limitation documented in docs/decisions.md.
"""

from __future__ import annotations

from datetime import date, datetime

import aiohttp

from ..const import CATEGORY_FAMILY, CATEGORY_OTHER, SOURCE_KIND_TICKETMASTER
from ..models import ScoutEvent
from .base import Source, SourceContext, SourceValidationError

API_URL = "https://app.ticketmaster.com/discovery/v2/events.json"


class TicketmasterSource(Source):
    """Ticketmaster Discovery API source."""

    kind = SOURCE_KIND_TICKETMASTER

    async def async_fetch(self, session: aiohttp.ClientSession, ctx: SourceContext) -> list[ScoutEvent]:
        """Fetch events from the Ticketmaster Discovery API."""
        if ctx.latitude is None or ctx.longitude is None:
            raise SourceValidationError("Ticketmaster requires a hub latitude and longitude")

        params: dict[str, str] = {
            "apikey": self.data["api_key"],
            "latlong": f"{ctx.latitude},{ctx.longitude}",
            "radius": str(int(ctx.radius_miles or 50)),
            "unit": "miles",
            "size": "200",
        }
        segments = self.data.get("segments") or []
        if segments:
            params["segmentName"] = ",".join(segments)
        keyword = self.data.get("keyword")
        if keyword:
            params["keyword"] = keyword
        if "Family" in segments:
            params["includeFamily"] = "only"

        try:
            async with session.get(API_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 401:
                    raise SourceValidationError("Ticketmaster rejected the API key")
                resp.raise_for_status()
                payload = await resp.json()
        except aiohttp.ClientError as err:
            raise SourceValidationError(f"Could not reach Ticketmaster: {err}") from err

        raw_events = payload.get("_embedded", {}).get("events", [])
        events: list[ScoutEvent] = []
        for raw in raw_events:
            start_info = raw.get("dates", {}).get("start", {})
            local_date = start_info.get("localDate")
            if not local_date:
                continue
            local_time = start_info.get("localTime")
            start: date | datetime
            if local_time:
                start = datetime.fromisoformat(f"{local_date}T{local_time}")
            else:
                start = datetime.fromisoformat(local_date).date()

            venue = None
            latitude = longitude = None
            venues = raw.get("_embedded", {}).get("venues", [])
            if venues:
                venue = venues[0]
                location = venue.get("location", {})
                latitude = float(location["latitude"]) if location.get("latitude") else None
                longitude = float(location["longitude"]) if location.get("longitude") else None

            classifications = raw.get("classifications", [])
            is_family = any(c.get("family") for c in classifications)
            category = CATEGORY_FAMILY if is_family else CATEGORY_OTHER

            price_ranges = raw.get("priceRanges")
            cost_text = None
            if price_ranges:
                low = price_ranges[0].get("min")
                high = price_ranges[0].get("max")
                if low is not None:
                    cost_text = f"${low}-${high}" if high and high != low else f"${low}"

            events.append(
                ScoutEvent(
                    uid="",
                    series_key="",
                    source_kind=self.kind,
                    source_name=ctx.name,
                    source_event_id=str(raw.get("id")),
                    title=str(raw.get("name") or "Untitled event"),
                    url=raw.get("url"),
                    start=start,
                    all_day=not bool(local_time),
                    venue_name=venue.get("name") if venue else None,
                    city=(venue.get("city", {}) or {}).get("name") if venue else None,
                    state=(venue.get("state", {}) or {}).get("stateCode") if venue else None,
                    latitude=latitude,
                    longitude=longitude,
                    category=category,  # type: ignore[arg-type]
                    cost_text=cost_text,
                )
            )
        return events
