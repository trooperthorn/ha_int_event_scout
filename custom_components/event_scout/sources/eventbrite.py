"""Eventbrite curated-organizer source.

Eventbrite's public event search has been shut down since 2019-12-12
(docs/research.md section 1), so this source only polls a fixed list of
organizer IDs the user already knows, through the still-live
`/v3/organizations/{id}/events/` endpoint. It is not a discovery source.
"""

from __future__ import annotations

from datetime import datetime

import aiohttp

from ..const import SOURCE_KIND_EVENTBRITE
from ..models import ScoutEvent
from .base import Source, SourceContext, SourceValidationError

API_BASE = "https://www.eventbriteapi.com/v3"


class EventbriteSource(Source):
    """Curated-organizer Eventbrite source."""

    kind = SOURCE_KIND_EVENTBRITE

    async def async_fetch(self, session: aiohttp.ClientSession, ctx: SourceContext) -> list[ScoutEvent]:
        """Fetch events for every configured organization ID."""
        token = self.data["token"]
        org_ids = [org.strip() for org in str(self.data.get("organization_ids", "")).split(",") if org.strip()]
        if not org_ids:
            raise SourceValidationError("organization_ids must list at least one Eventbrite organizer ID")

        venue_ids = {v.strip() for v in str(self.data.get("venue_ids", "")).split(",") if v.strip()}
        headers = {"Authorization": f"Bearer {token}"}

        events: list[ScoutEvent] = []
        for org_id in org_ids:
            events.extend(await self._fetch_organization(session, headers, org_id, venue_ids, ctx))
        return events

    async def _fetch_organization(
        self,
        session: aiohttp.ClientSession,
        headers: dict[str, str],
        org_id: str,
        venue_ids: set[str],
        ctx: SourceContext,
    ) -> list[ScoutEvent]:
        events: list[ScoutEvent] = []
        url = f"{API_BASE}/organizations/{org_id}/events/"
        params: dict[str, str] = {"status": "live", "expand": "venue"}
        continuation: str | None = None

        while True:
            if continuation:
                params["continuation"] = continuation
            try:
                async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 401:
                        raise SourceValidationError("Eventbrite rejected the token")
                    if resp.status == 404:
                        raise SourceValidationError(f"Eventbrite organizer {org_id} was not found")
                    resp.raise_for_status()
                    payload = await resp.json()
            except aiohttp.ClientError as err:
                raise SourceValidationError(f"Could not reach Eventbrite: {err}") from err

            for raw in payload.get("events", []):
                event = self._event_from_raw(raw, org_id, venue_ids, ctx)
                if event is not None:
                    events.append(event)

            pagination = payload.get("pagination", {})
            if pagination.get("has_more_items"):
                continuation = pagination.get("continuation")
                if not continuation:
                    break
            else:
                break
        return events

    def _event_from_raw(self, raw: dict, org_id: str, venue_ids: set[str], ctx: SourceContext) -> ScoutEvent | None:
        venue = raw.get("venue") or {}
        if venue_ids and str(venue.get("id")) not in venue_ids:
            return None

        start_local = raw.get("start", {}).get("local")
        if not start_local:
            return None
        start = datetime.fromisoformat(start_local)
        end_local = raw.get("end", {}).get("local")
        end = datetime.fromisoformat(end_local) if end_local else None

        address = venue.get("address", {}) or {}
        latitude = float(venue["latitude"]) if venue.get("latitude") else None
        longitude = float(venue["longitude"]) if venue.get("longitude") else None

        return ScoutEvent(
            uid="",
            series_key="",
            source_kind=self.kind,
            source_name=ctx.name,
            source_event_id=str(raw.get("id") or f"{org_id}:{start_local}"),
            title=str((raw.get("name") or {}).get("text") or "Untitled event"),
            description=(raw.get("description") or {}).get("text"),
            url=raw.get("url"),
            start=start,
            end=end,
            all_day=False,
            venue_name=venue.get("name"),
            address=address.get("localized_address_display"),
            latitude=latitude,
            longitude=longitude,
            category=ctx.category,  # type: ignore[arg-type]
            is_free=raw.get("is_free"),
        )
