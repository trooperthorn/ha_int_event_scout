"""Tests for geo.py: haversine, the road estimate, and the OSRM table client."""

from __future__ import annotations

import json

import pytest

from custom_components.event_scout.geo import OSRMClient, OSRMError, estimate_drive, haversine_miles
from tests.conftest import load_fixture_text
from tests.fake_session import FakeResponse, FakeSession


def test_haversine_known_pair() -> None:
    # Austin, TX to Georgetown, TX is roughly 24 miles straight line.
    miles = haversine_miles(30.2672, -97.7431, 30.6333, -97.6780)
    assert 22 < miles < 27


def test_haversine_zero_distance() -> None:
    assert haversine_miles(30.0, -97.0, 30.0, -97.0) == pytest.approx(0.0)


def test_estimate_drive_arithmetic() -> None:
    drive_miles, drive_minutes = estimate_drive(20.0, road_factor=1.3, average_speed_mph=40)
    assert drive_miles == pytest.approx(26.0)
    assert drive_minutes == pytest.approx(39.0)


def test_estimate_drive_zero_speed_returns_zero_minutes() -> None:
    drive_miles, drive_minutes = estimate_drive(10.0, road_factor=1.3, average_speed_mph=0)
    assert drive_miles == pytest.approx(13.0)
    assert drive_minutes == 0.0


async def test_osrm_table_parses_recorded_fixture() -> None:
    body = load_fixture_text("osrm_table_response.json")
    session = FakeSession()
    session.add_prefix("https://router.project-osrm.org/table/v1/driving/", FakeResponse(status=200, _body=body))

    client = OSRMClient("https://router.project-osrm.org")
    results = await client.async_table(
        session,
        origin=(30.5083, -97.6779),
        destinations=[(30.5083, -97.6779), (30.6333, -97.6811)],
    )

    assert len(results) == 2
    assert results[0] is not None
    assert results[0].drive_miles == pytest.approx(48280.5 / 1609.344)
    assert results[0].drive_minutes == pytest.approx(2760.2 / 60)
    assert results[1] is not None
    assert results[1].drive_miles == pytest.approx(96561.0 / 1609.344)


async def test_osrm_table_batches_at_fifty_destinations() -> None:
    payload = json.loads(load_fixture_text("osrm_table_response.json"))
    # 60 destinations split into batches of 50 and 10; each fake response must
    # be sized to match the batch it answers, since the OSRM table service
    # returns one row per coordinate actually sent in that request.
    first_batch_distances = [0.0] + [1000.0] * 50
    first_batch_durations = [0.0] + [100.0] * 50
    second_batch_distances = [0.0] + [1000.0] * 10
    second_batch_durations = [0.0] + [100.0] * 10

    session = FakeSession()
    session.add_prefix(
        "https://router.project-osrm.org/table/v1/driving/",
        FakeResponse(status=200, _body=json.dumps({**payload, "distances": [first_batch_distances], "durations": [first_batch_durations]})),
    )
    session.add_prefix(
        "https://router.project-osrm.org/table/v1/driving/",
        FakeResponse(status=200, _body=json.dumps({**payload, "distances": [second_batch_distances], "durations": [second_batch_durations]})),
    )

    client = OSRMClient("https://router.project-osrm.org")
    destinations = [(30.0 + i * 0.01, -97.0) for i in range(60)]
    results = await client.async_table(session, origin=(30.0, -97.0), destinations=destinations)

    assert len(results) == 60


async def test_osrm_table_raises_on_bad_status() -> None:
    session = FakeSession()
    session.add_prefix("https://example.com/table/v1/driving/", FakeResponse(status=500, _body=""))

    client = OSRMClient("https://example.com")
    with pytest.raises(OSRMError):
        await client.async_table(session, origin=(30.0, -97.0), destinations=[(30.1, -97.1)])


async def test_osrm_table_raises_on_error_code() -> None:
    session = FakeSession()
    session.add_prefix("https://example.com/table/v1/driving/", FakeResponse(status=200, _body=json.dumps({"code": "NoRoute"})))

    client = OSRMClient("https://example.com")
    with pytest.raises(OSRMError):
        await client.async_table(session, origin=(30.0, -97.0), destinations=[(30.1, -97.1)])


async def test_osrm_table_handles_null_entries() -> None:
    body = json.dumps({"code": "Ok", "distances": [[0, None]], "durations": [[0, None]]})
    session = FakeSession()
    session.add_prefix("https://example.com/table/v1/driving/", FakeResponse(status=200, _body=body))

    client = OSRMClient("https://example.com")
    results = await client.async_table(session, origin=(30.0, -97.0), destinations=[(30.1, -97.1)])
    assert results == [None]
