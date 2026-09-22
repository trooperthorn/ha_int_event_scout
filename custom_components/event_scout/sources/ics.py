"""ICS calendar source.

Fetches a webcal:// or https:// .ics feed and returns its events flattened
through ical's Calendar and timeline. webcal:// is rewritten to https://
before the request, per design.md section 2.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import aiohttp
from ical.calendar_stream import IcsCalendarStream
from ical.exceptions import CalendarParseError

from ..const import SOURCE_KIND_ICS
from ..models import ScoutEvent
from .base import Source, SourceContext, SourceValidationError


def _rewrite_webcal(url: str) -> str:
    if url.startswith("webcal://"):
        return "https://" + url[len("webcal://") :]
    return url


class IcsSource(Source):
    """Generic ICS feed source."""

    kind = SOURCE_KIND_ICS

    async def async_fetch(self, session: aiohttp.ClientSession, ctx: SourceContext) -> list[ScoutEvent]:
        """Fetch and parse the configured ICS feed."""
        url = _rewrite_webcal(self.data["url"])
        auth = None
        username = self.data.get("username")
        password = self.data.get("password")
        if username and password:
            auth = aiohttp.BasicAuth(username, password)

        try:
            async with session.get(url, auth=auth, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise SourceValidationError(f"Could not fetch ICS feed: {err}") from err

        try:
            calendar = IcsCalendarStream.calendar_from_ics(text)
        except CalendarParseError as err:
            raise SourceValidationError(f"Invalid ICS content: {err}") from err

        horizon_start = date.today()
        horizon_end = horizon_start + timedelta(days=ctx.horizon_days)
        events: list[ScoutEvent] = []
        for vevent in calendar.timeline.overlapping(
            datetime.combine(horizon_start, datetime.min.time()),
            datetime.combine(horizon_end, datetime.max.time()),
        ):
            start = vevent.start
            end = vevent.end
            all_day = isinstance(start, date) and not isinstance(start, datetime)
            events.append(
                ScoutEvent(
                    uid=f"{ctx.subentry_id}:{vevent.uid}",
                    series_key="",
                    source_kind=self.kind,
                    source_name=ctx.name,
                    source_event_id=str(vevent.uid),
                    title=vevent.summary or "Untitled event",
                    description=vevent.description,
                    url=str(vevent.url) if vevent.url else None,
                    start=start,
                    end=end,
                    all_day=all_day,
                    venue_name=vevent.location,
                    category=ctx.category,  # type: ignore[arg-type]
                )
            )
        return events
