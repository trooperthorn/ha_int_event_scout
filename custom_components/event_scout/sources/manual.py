"""Manual recurring-event source: city birthdays and known recurring festivals.

Computes the next occurrence of a fixed month/day or nth-weekday recurrence
inside the coordinator's horizon. No network access, so validate() only
checks the recurrence rule instead of calling async_fetch.
"""

from __future__ import annotations

import calendar as calendar_mod
from datetime import date, timedelta

import aiohttp

from ..const import SOURCE_KIND_MANUAL, VENDOR_ORIGIN_MANUAL
from ..models import ScoutEvent, VendorInfo
from .base import Source, SourceContext, SourceValidationError


def _next_month_day(today: date, month: int, day: int, horizon_end: date) -> date | None:
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if today <= candidate <= horizon_end:
            return candidate
    return None


def _next_nth_weekday(today: date, month: int, weekday: int, nth: int, horizon_end: date) -> date | None:
    for year in (today.year, today.year + 1):
        candidate = _nth_weekday_of_month(year, month, weekday, nth)
        if candidate and today <= candidate <= horizon_end:
            return candidate
    return None


def _nth_weekday_of_month(year: int, month: int, weekday: int, nth: int) -> date | None:
    calendar_obj = calendar_mod.Calendar()
    matches = [d for d in calendar_obj.itermonthdates(year, month) if d.month == month and d.weekday() == weekday]
    if not matches:
        return None
    if nth == -1:
        return matches[-1]
    if 1 <= nth <= len(matches):
        return matches[nth - 1]
    return None


class ManualSource(Source):
    """A single user-defined recurring event."""

    kind = SOURCE_KIND_MANUAL

    async def async_validate(self, session: aiohttp.ClientSession, ctx: SourceContext) -> None:
        """Validate the recurrence rule without any network access."""
        if "month" not in self.data or "day" not in self.data:
            if not all(k in self.data for k in ("month", "weekday", "nth")):
                raise SourceValidationError("Provide either month/day or month/weekday/nth")

    async def async_fetch(self, session: aiohttp.ClientSession, ctx: SourceContext) -> list[ScoutEvent]:
        """Compute the next occurrence of this recurring event."""
        today = date.today()
        horizon_end = today + timedelta(days=ctx.horizon_days)
        month = int(self.data["month"])

        if "day" in self.data:
            occurrence = _next_month_day(today, month, int(self.data["day"]), horizon_end)
        else:
            occurrence = _next_nth_weekday(today, month, int(self.data["weekday"]), int(self.data["nth"]), horizon_end)

        if occurrence is None:
            return []

        vendor = None
        if self.data.get("vendor_deadline"):
            vendor = VendorInfo(
                available="yes",
                app_deadline=date.fromisoformat(self.data["vendor_deadline"]),
                app_open=date.fromisoformat(self.data["vendor_open"]) if self.data.get("vendor_open") else None,
                app_url=self.data.get("vendor_url"),
                origin=VENDOR_ORIGIN_MANUAL,
                confidence=1.0,
            )

        return [
            ScoutEvent(
                uid="",
                series_key="",
                source_kind=self.kind,
                source_name=ctx.name,
                source_event_id=self.data.get("title", ctx.name),
                title=self.data.get("title", ctx.name),
                start=occurrence,
                all_day=True,
                city=self.data.get("city"),
                category=ctx.category,  # type: ignore[arg-type]
                vendor=vendor,
            )
        ]
