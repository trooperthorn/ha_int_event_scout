"""Tests for area.py: AreaFilter decisions per criterion, any/all modes, and no-coordinate events."""

from __future__ import annotations

from datetime import date

from custom_components.event_scout.area import AreaFilter
from custom_components.event_scout.const import EXCLUDED_REASON_COUNTY_UNRESOLVED, EXCLUDED_REASON_NO_COORDINATES, EXCLUDED_REASON_OUTSIDE_AREA
from custom_components.event_scout.models import ScoutEvent


def _event(**overrides) -> ScoutEvent:  # noqa: ANN003
    defaults = dict(
        uid="u1",
        series_key="s1",
        source_kind="ics",
        source_name="ICS",
        source_event_id="e1",
        title="Test Event",
        start=date(2026, 10, 1),
        city="Georgetown",
        latitude=30.6333,
        longitude=-97.6780,
        distance_miles=25.0,
        county="Williamson",
        drive_miles=30.0,
        drive_minutes=40.0,
    )
    defaults.update(overrides)
    return ScoutEvent(**defaults)


def test_no_criteria_configured_includes_everything() -> None:
    area_filter = AreaFilter(mode="any", cities=[], counties=[], distance_metric="straight_line", distance_limit=0)
    decision = area_filter.decide(_event())
    assert decision.included is True
    assert decision.matched == []


def test_city_alone_matches_case_insensitively() -> None:
    area_filter = AreaFilter(mode="any", cities=["georgetown"], counties=[], distance_metric="straight_line", distance_limit=0)
    decision = area_filter.decide(_event(city="GEORGETOWN"))
    assert decision.included is True
    assert decision.matched == ["city"]


def test_city_alone_no_match() -> None:
    area_filter = AreaFilter(mode="any", cities=["austin"], counties=[], distance_metric="straight_line", distance_limit=0)
    decision = area_filter.decide(_event(city="Georgetown"))
    assert decision.included is False
    assert decision.reason == EXCLUDED_REASON_OUTSIDE_AREA


def test_county_alone_matches() -> None:
    area_filter = AreaFilter(mode="any", cities=[], counties=["williamson"], distance_metric="straight_line", distance_limit=0)
    decision = area_filter.decide(_event(county="Williamson"))
    assert decision.included is True
    assert decision.matched == ["county"]


def test_county_alone_no_match() -> None:
    area_filter = AreaFilter(mode="any", cities=[], counties=["travis"], distance_metric="straight_line", distance_limit=0)
    decision = area_filter.decide(_event(county="Williamson"))
    assert decision.included is False
    assert decision.reason == EXCLUDED_REASON_OUTSIDE_AREA


def test_distance_alone_straight_line_matches() -> None:
    area_filter = AreaFilter(mode="any", cities=[], counties=[], distance_metric="straight_line", distance_limit=30)
    decision = area_filter.decide(_event(distance_miles=25.0))
    assert decision.included is True
    assert decision.matched == ["distance"]


def test_distance_alone_driving_minutes_matches() -> None:
    area_filter = AreaFilter(mode="any", cities=[], counties=[], distance_metric="driving_minutes", distance_limit=50)
    decision = area_filter.decide(_event(drive_minutes=40.0))
    assert decision.included is True
    assert decision.matched == ["distance"]


def test_distance_alone_no_match() -> None:
    area_filter = AreaFilter(mode="any", cities=[], counties=[], distance_metric="straight_line", distance_limit=10)
    decision = area_filter.decide(_event(distance_miles=25.0))
    assert decision.included is False
    assert decision.reason == EXCLUDED_REASON_OUTSIDE_AREA


def test_any_mode_includes_when_one_criterion_matches() -> None:
    area_filter = AreaFilter(mode="any", cities=["austin"], counties=["williamson"], distance_metric="straight_line", distance_limit=0)
    decision = area_filter.decide(_event(city="Georgetown", county="Williamson"))
    assert decision.included is True
    assert decision.matched == ["county"]


def test_all_mode_requires_every_enabled_criterion() -> None:
    area_filter = AreaFilter(mode="all", cities=["austin"], counties=["williamson"], distance_metric="straight_line", distance_limit=0)
    decision = area_filter.decide(_event(city="Georgetown", county="Williamson"))
    assert decision.included is False

    area_filter2 = AreaFilter(mode="all", cities=["georgetown"], counties=["williamson"], distance_metric="straight_line", distance_limit=0)
    decision2 = area_filter2.decide(_event(city="Georgetown", county="Williamson"))
    assert decision2.included is True
    assert set(decision2.matched) == {"city", "county"}


def test_no_coordinate_event_matches_only_by_city() -> None:
    area_filter = AreaFilter(mode="any", cities=["georgetown"], counties=["williamson"], distance_metric="straight_line", distance_limit=30)
    decision = area_filter.decide(_event(latitude=None, longitude=None, city="Georgetown", county=None, distance_miles=None))
    assert decision.included is True
    assert decision.matched == ["city"]


def test_no_coordinate_event_excluded_reason_when_only_distance_configured() -> None:
    area_filter = AreaFilter(mode="any", cities=[], counties=[], distance_metric="straight_line", distance_limit=30, include_unlocated=False)
    decision = area_filter.decide(_event(latitude=None, longitude=None, distance_miles=None))
    assert decision.included is False
    assert decision.reason == EXCLUDED_REASON_NO_COORDINATES


def test_no_coordinate_event_included_by_default_when_include_unlocated_true() -> None:
    area_filter = AreaFilter(mode="any", cities=[], counties=[], distance_metric="straight_line", distance_limit=30)
    decision = area_filter.decide(_event(latitude=None, longitude=None, distance_miles=None))
    assert decision.included is True


def test_manual_source_always_passes_regardless_of_area_criteria() -> None:
    area_filter = AreaFilter(
        mode="any", cities=["austin"], counties=[], distance_metric="straight_line", distance_limit=0, include_unlocated=False
    )
    decision = area_filter.decide(_event(source_kind="manual", city="Georgetown", latitude=None, longitude=None, distance_miles=None))
    assert decision.included is True
    assert decision.matched == []


def test_no_coordinate_event_city_match_always_included_even_with_include_unlocated_off() -> None:
    area_filter = AreaFilter(
        mode="any", cities=["georgetown"], counties=[], distance_metric="straight_line", distance_limit=0, include_unlocated=False
    )
    decision = area_filter.decide(_event(city="Georgetown", latitude=None, longitude=None, distance_miles=None))
    assert decision.included is True
    assert decision.matched == ["city"]


def test_county_unresolved_reason_when_coordinates_present_but_county_none() -> None:
    area_filter = AreaFilter(mode="any", cities=[], counties=["williamson"], distance_metric="straight_line", distance_limit=0)
    decision = area_filter.decide(_event(county=None))
    assert decision.included is False
    assert decision.reason == EXCLUDED_REASON_COUNTY_UNRESOLVED


def test_legacy_radius_miles_seeding_is_coordinator_responsibility() -> None:
    # AreaFilter itself just receives a distance_limit; the coordinator seeds
    # it from the legacy radius_miles hub data key when distance_limit is
    # absent from options (see coordinator.py: _apply_area_filter).
    area_filter = AreaFilter(mode="any", cities=[], counties=[], distance_metric="straight_line", distance_limit=50)
    decision = area_filter.decide(_event(distance_miles=45.0))
    assert decision.included is True
