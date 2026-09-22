"""AreaFilter: decide whether an event falls inside the configured area."""

from __future__ import annotations

from dataclasses import dataclass, field

from .const import (
    AREA_MODE_ALL,
    DISTANCE_METRIC_STRAIGHT_LINE,
    EXCLUDED_REASON_COUNTY_UNRESOLVED,
    EXCLUDED_REASON_NO_COORDINATES,
    EXCLUDED_REASON_OUTSIDE_AREA,
    SOURCE_KIND_MANUAL,
)
from .models import ScoutEvent


@dataclass(frozen=True, kw_only=True)
class AreaDecision:
    """The result of testing one event against the configured area filter."""

    included: bool
    matched: list[str] = field(default_factory=list)
    reason: str | None = None


class AreaFilter:
    """Decides whether events fall inside a hub's configured area.

    Criteria (city, county, distance) are OR'd together by default (`any`
    mode) or AND'd together (`all` mode) when every enabled criterion is
    configured. A criterion with no configured value is disabled and does
    not count toward either mode.
    """

    def __init__(
        self,
        *,
        mode: str,
        cities: list[str],
        counties: list[str],
        distance_metric: str,
        distance_limit: float,
        include_unlocated: bool = True,
    ) -> None:
        """Store the configured criteria, normalized for case-insensitive matching."""
        self._mode = mode
        self._cities = {c.strip().lower() for c in cities if c.strip()}
        self._counties = {c.strip().lower() for c in counties if c.strip()}
        self._distance_metric = distance_metric
        self._distance_limit = distance_limit
        self._include_unlocated = include_unlocated

    @property
    def has_any_criterion(self) -> bool:
        """Return whether any criterion is actually enabled."""
        return bool(self._cities or self._counties or self._distance_limit > 0)

    def decide(self, event: ScoutEvent) -> AreaDecision:
        """Return whether an event matches the configured area.

        City always applies (it needs no coordinates). County and distance
        only apply when the event has coordinates; without them those two
        criteria simply never match for that event, per design section 1.
        """
        if event.source_kind == SOURCE_KIND_MANUAL:
            return AreaDecision(included=True, matched=[])

        if not self.has_any_criterion:
            return AreaDecision(included=True, matched=[])

        has_coordinates = event.latitude is not None and event.longitude is not None

        city_enabled = bool(self._cities)
        city_matched = city_enabled and event.city is not None and event.city.strip().lower() in self._cities

        county_enabled = bool(self._counties)
        county_matched = county_enabled and has_coordinates and event.county is not None and event.county.strip().lower() in self._counties

        distance_enabled = self._distance_limit > 0
        distance_value = self._distance_value(event) if distance_enabled and has_coordinates else None
        distance_matched = distance_enabled and distance_value is not None and distance_value <= self._distance_limit

        matched = [
            name for name, is_matched in (("city", city_matched), ("county", county_matched), ("distance", distance_matched)) if is_matched
        ]

        enabled_checks = [
            is_matched
            for enabled, is_matched in ((city_enabled, city_matched), (county_enabled, county_matched), (distance_enabled, distance_matched))
            if enabled
        ]

        if self._mode == AREA_MODE_ALL:
            included = all(enabled_checks) if enabled_checks else True
        else:
            included = bool(matched)

        if included:
            return AreaDecision(included=True, matched=matched)

        if not has_coordinates and not city_matched:
            if self._include_unlocated:
                return AreaDecision(included=True, matched=matched)
            if county_enabled or distance_enabled:
                return AreaDecision(included=False, matched=matched, reason=EXCLUDED_REASON_NO_COORDINATES)

        if county_enabled and has_coordinates and event.county is None and not city_matched and not distance_matched:
            return AreaDecision(included=False, matched=matched, reason=EXCLUDED_REASON_COUNTY_UNRESOLVED)

        return AreaDecision(included=False, matched=matched, reason=EXCLUDED_REASON_OUTSIDE_AREA)

    def _distance_value(self, event: ScoutEvent) -> float | None:
        if self._distance_metric == DISTANCE_METRIC_STRAIGHT_LINE:
            return event.distance_miles
        if self._distance_metric == "driving_minutes":
            return event.drive_minutes
        return event.drive_miles

    def summary(self) -> str:
        """Return a human sentence describing the configured area, for sensor attributes."""
        parts: list[str] = []
        if self._counties:
            parts.append(" or ".join(f"{c.title()} County" for c in sorted(self._counties)))
        if self._cities:
            parts.append(" or ".join(c.title() for c in sorted(self._cities)))
        if self._distance_limit > 0:
            unit = (
                "driving minutes"
                if self._distance_metric == "driving_minutes"
                else "driving miles"
                if self._distance_metric != DISTANCE_METRIC_STRAIGHT_LINE
                else "miles"
            )
            qualifier = "" if self._distance_metric == DISTANCE_METRIC_STRAIGHT_LINE else " (estimated)"
            parts.append(f"within {self._distance_limit:g} {unit}{qualifier}")
        if not parts:
            return "No area filter configured"
        joiner = " and " if self._mode == AREA_MODE_ALL else ", or "
        return joiner.join(parts)
