"""Socrata (SODA) open-data source.

Fields are mapped from a per-subentry field map, since dataset schemas vary
by municipality; the Austin ACCD Event Listings dataset p9ma-z6y9 is the
documented example (docs/sources.md).
"""

from __future__ import annotations

from datetime import date, datetime

import aiohttp

from ..const import SOURCE_KIND_SOCRATA
from ..models import ScoutEvent
from .base import Source, SourceContext, SourceValidationError


class SocrataSource(Source):
    """Generic Socrata open-data source."""

    kind = SOURCE_KIND_SOCRATA

    async def async_fetch(self, session: aiohttp.ClientSession, ctx: SourceContext) -> list[ScoutEvent]:
        """Fetch and map rows from a Socrata dataset."""
        domain = self.data["domain"]
        dataset_id = self.data["dataset_id"]
        url = f"https://{domain}/resource/{dataset_id}.json"
        params = {"$limit": "1000"}
        headers = {}
        app_token = self.data.get("app_token")
        if app_token:
            headers["X-App-Token"] = app_token

        try:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 404:
                    raise SourceValidationError(f"Dataset {dataset_id} was not found on {domain}")
                resp.raise_for_status()
                rows = await resp.json()
        except aiohttp.ClientError as err:
            raise SourceValidationError(f"Could not reach Socrata endpoint: {err}") from err

        field_title = self.data.get("field_title", "title")
        field_start = self.data.get("field_start", "start_date")
        field_end = self.data.get("field_end")
        field_url = self.data.get("field_url")
        field_venue = self.data.get("field_venue")

        events: list[ScoutEvent] = []
        for index, row in enumerate(rows):
            raw_start = row.get(field_start)
            start = _parse(raw_start)
            if start is None:
                continue
            title = row.get(field_title)
            if not title:
                continue
            events.append(
                ScoutEvent(
                    uid="",
                    series_key="",
                    source_kind=self.kind,
                    source_name=ctx.name,
                    source_event_id=str(row.get(":id") or index),
                    title=str(title),
                    url=row.get(field_url) if field_url else None,
                    start=start,
                    end=_parse(row.get(field_end)) if field_end else None,
                    all_day=isinstance(start, date) and not isinstance(start, datetime),
                    venue_name=row.get(field_venue) if field_venue else None,
                    category=ctx.category,  # type: ignore[arg-type]
                )
            )
        return events


def _parse(value: object) -> date | datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
