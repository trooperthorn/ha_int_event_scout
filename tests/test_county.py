"""Tests for county.py: Census geocoder parsing and Store-backed caching."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from custom_components.event_scout.county import CountyResolver, county_name_from_response
from custom_components.event_scout.store import EventScoutStore
from tests.conftest import load_fixture_text
from tests.fake_session import FakeResponse, FakeSession


def test_county_name_from_response_strips_the_word_county() -> None:
    import json

    payload = json.loads(load_fixture_text("census_geocoder_response.json"))
    assert county_name_from_response(payload) == "Williamson"


def test_county_name_from_response_missing_geographies_returns_none() -> None:
    assert county_name_from_response({"result": {}}) is None


def test_county_name_from_response_empty_counties_returns_none() -> None:
    assert county_name_from_response({"result": {"geographies": {"Counties": []}}}) is None


async def test_resolver_caches_and_avoids_second_request(hass) -> None:  # noqa: ANN001
    store = EventScoutStore(hass, "entry1")
    await store.async_load()
    body = load_fixture_text("census_geocoder_response.json")
    session = FakeSession()
    session.add_prefix("https://geocoding.geo.census.gov/", FakeResponse(status=200, _body=body))

    resolver = CountyResolver(store)
    first = await resolver.async_resolve(session, 30.5083, -97.6779)
    assert first == "Williamson"

    # Second call for the same (rounded) coordinate must not require another
    # queued fake response; FakeSession raises if one isn't registered.
    second = await resolver.async_resolve(session, 30.5083, -97.6779)
    assert second == "Williamson"


async def test_resolver_returns_none_without_raising_on_unresolved(hass) -> None:  # noqa: ANN001
    store = EventScoutStore(hass, "entry2")
    await store.async_load()
    session = FakeSession()
    session.add_prefix("https://geocoding.geo.census.gov/", FakeResponse(status=200, _body='{"result": {"geographies": {"Counties": []}}}'))

    resolver = CountyResolver(store)
    result = await resolver.async_resolve(session, 40.0, -100.0)
    assert result is None


async def test_resolver_returns_none_on_request_failure(hass) -> None:  # noqa: ANN001
    store = EventScoutStore(hass, "entry3")
    await store.async_load()
    session = FakeSession()
    session.add_prefix("https://geocoding.geo.census.gov/", FakeResponse(status=500, _body=""))

    resolver = CountyResolver(store)
    result = await resolver.async_resolve(session, 41.0, -101.0)
    assert result is None


async def test_resolver_sleeps_between_requests(hass) -> None:  # noqa: ANN001
    store = EventScoutStore(hass, "entry4")
    await store.async_load()
    body = load_fixture_text("census_geocoder_response.json")
    session = FakeSession()
    session.add_prefix("https://geocoding.geo.census.gov/", FakeResponse(status=200, _body=body))
    session.add_prefix("https://geocoding.geo.census.gov/", FakeResponse(status=200, _body=body))

    resolver = CountyResolver(store)
    with patch("custom_components.event_scout.county.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await resolver.async_resolve(session, 30.0, -97.0)
        await resolver.async_resolve(session, 31.0, -98.0)
    mock_sleep.assert_awaited_once()
