"""Tests for the coordinator's area-filter integration: excluded_counts and OSRM fallback."""

from __future__ import annotations

from datetime import date, timedelta

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.event_scout.const import DOMAIN
from custom_components.event_scout.coordinator import EventScoutCoordinator
from custom_components.event_scout.models import ScoutEvent
from tests.conftest import load_fixture_text
from tests.fake_session import FakeResponse, FakeSession


def _event(uid: str, *, city=None, lat=None, lon=None) -> ScoutEvent:  # noqa: ANN001
    return ScoutEvent(
        uid=uid,
        series_key=f"series-{uid}",
        source_kind="manual",
        source_name="Manual",
        source_event_id=uid,
        title=f"Event {uid}",
        start=date.today() + timedelta(days=5),
        city=city,
        latitude=lat,
        longitude=lon,
    )


async def test_apply_area_filter_reports_excluded_counts(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="area1",
        data={"name": "Area1", "horizon_days": 90, "radius_miles": 50},
        options={"distance_metric": "straight_line", "distance_limit": 10, "cities": [], "counties": []},
    )
    entry.add_to_hass(hass)
    coordinator = EventScoutCoordinator(hass, entry, update_interval=timedelta(hours=6))
    await coordinator._async_setup()

    events = [
        _event("in_range", lat=30.55, lon=-97.68),  # close to hub
        _event("out_of_range", lat=32.0, lon=-96.0),  # far from hub (Dallas-ish)
        _event("no_coords"),
    ]

    session = FakeSession()
    filtered, excluded_counts = await coordinator._apply_area_filter(events, session=session, hub_lat=30.5083, hub_lon=-97.6779)

    filtered_uids = {e.uid for e in filtered}
    assert "in_range" in filtered_uids
    assert "out_of_range" not in filtered_uids
    assert excluded_counts.get("outside_area", 0) == 1


async def test_apply_area_filter_falls_back_to_estimate_on_osrm_failure(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="area2",
        data={"name": "Area2", "horizon_days": 90, "radius_miles": 50},
        options={
            "distance_metric": "driving_miles",
            "distance_limit": 100,
            "osrm_url": "https://router.project-osrm.org",
            "cities": [],
            "counties": [],
        },
    )
    entry.add_to_hass(hass)
    coordinator = EventScoutCoordinator(hass, entry, update_interval=timedelta(hours=6))
    await coordinator._async_setup()

    events = [_event("e1", lat=30.55, lon=-97.68)]

    session = FakeSession()
    session.add_prefix("https://router.project-osrm.org/table/v1/driving/", FakeResponse(status=500, _body=""))

    filtered, _excluded_counts = await coordinator._apply_area_filter(events, session=session, hub_lat=30.5083, hub_lon=-97.6779)

    assert len(filtered) == 1
    assert filtered[0].distance_origin == "estimated"
    assert coordinator.last_osrm_error is not None


async def test_apply_area_filter_uses_routed_tier_on_success(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="area3",
        data={"name": "Area3", "horizon_days": 90, "radius_miles": 50},
        options={
            "distance_metric": "driving_miles",
            "distance_limit": 100,
            "osrm_url": "https://router.project-osrm.org",
            "cities": [],
            "counties": [],
        },
    )
    entry.add_to_hass(hass)
    coordinator = EventScoutCoordinator(hass, entry, update_interval=timedelta(hours=6))
    await coordinator._async_setup()

    events = [_event("e1", lat=30.6333, lon=-97.6811)]

    body = load_fixture_text("osrm_table_response.json")
    session = FakeSession()
    session.add_prefix("https://router.project-osrm.org/table/v1/driving/", FakeResponse(status=200, _body=body))

    filtered, _excluded_counts = await coordinator._apply_area_filter(events, session=session, hub_lat=30.5083, hub_lon=-97.6779)

    assert len(filtered) == 1
    assert filtered[0].distance_origin == "routed"


async def test_apply_area_filter_resolves_county_when_configured(hass) -> None:  # noqa: ANN001
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="area4",
        data={"name": "Area4", "horizon_days": 90, "radius_miles": 50},
        options={"distance_metric": "straight_line", "distance_limit": 0, "cities": [], "counties": ["williamson"]},
    )
    entry.add_to_hass(hass)
    coordinator = EventScoutCoordinator(hass, entry, update_interval=timedelta(hours=6))
    await coordinator._async_setup()

    events = [_event("e1", lat=30.6333, lon=-97.6780)]

    body = load_fixture_text("census_geocoder_response.json")
    session = FakeSession()
    session.add_prefix("https://geocoding.geo.census.gov/", FakeResponse(status=200, _body=body))

    filtered, excluded_counts = await coordinator._apply_area_filter(events, session=session, hub_lat=30.5083, hub_lon=-97.6779)

    assert len(filtered) == 1
    assert filtered[0].county == "Williamson"
    assert excluded_counts == {}
