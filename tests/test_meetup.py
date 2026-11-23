"""Tests for sources/meetup.py: JWT signing, token caching, introspection, and event mapping."""

from __future__ import annotations

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from custom_components.event_scout.sources.base import SourceContext, SourceValidationError
from custom_components.event_scout.sources.meetup import (
    _TOKEN_CACHE,
    JWT_AUDIENCE,
    MeetupSource,
    build_eventsearch_query,
    map_eventsearch_args,
)
from tests.conftest import load_fixture_text
from tests.fake_session import FakeResponse, FakeSession


@pytest.fixture
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


@pytest.fixture(autouse=True)
def _clear_token_cache():
    _TOKEN_CACHE.clear()
    yield
    _TOKEN_CACHE.clear()


def _ctx(**overrides) -> SourceContext:  # noqa: ANN003
    defaults = dict(subentry_id="s1", name="Meetup", category="community", latitude=30.5083, longitude=-97.6779, radius_miles=50)
    defaults.update(overrides)
    return SourceContext(**defaults)


def _source(private_pem: str) -> MeetupSource:
    return MeetupSource(
        {
            "name": "Meetup",
            "client_id": "client-123",
            "member_id": "member-456",
            "private_key": private_pem,
            "category": "community",
        }
    )


async def test_jwt_assertion_shape(rsa_keypair) -> None:  # noqa: ANN001
    private_pem, public_pem = rsa_keypair
    source = _source(private_pem)

    session = FakeSession()
    session.add(
        "https://secure.meetup.com/oauth2/access",
        FakeResponse(status=200, _json={"access_token": "tok-1", "expires_in": 3600}),
    )

    class _CapturingSession(FakeSession):
        def post(self, url, **kwargs):  # noqa: ANN001, ANN003, ANN202
            self.last_data = kwargs.get("data")
            return super().post(url, **kwargs)

    capturing = _CapturingSession(responses=session.responses)
    await source._async_get_token(capturing)

    assertion = capturing.last_data["assertion"]
    decoded = jwt.decode(assertion, public_pem, algorithms=["RS256"], audience=JWT_AUDIENCE)
    assert decoded["iss"] == "client-123"
    assert decoded["sub"] == "member-456"
    assert decoded["aud"] == JWT_AUDIENCE
    assert decoded["exp"] > decoded["iat"]


async def test_token_is_cached_until_near_expiry(rsa_keypair) -> None:  # noqa: ANN001
    private_pem, _ = rsa_keypair
    source = _source(private_pem)

    session = FakeSession()
    session.add(
        "https://secure.meetup.com/oauth2/access",
        FakeResponse(status=200, _json={"access_token": "tok-1", "expires_in": 3600}),
    )

    token1 = await source._async_get_token(session)
    token2 = await source._async_get_token(session)
    assert token1 == token2 == "tok-1"


async def test_token_is_refreshed_near_expiry(rsa_keypair) -> None:  # noqa: ANN001
    private_pem, _ = rsa_keypair
    source = _source(private_pem)
    _TOKEN_CACHE["client-123"] = ("stale-token", time.time() + 30)

    session = FakeSession()
    session.add(
        "https://secure.meetup.com/oauth2/access",
        FakeResponse(status=200, _json={"access_token": "fresh-token", "expires_in": 3600}),
    )

    token = await source._async_get_token(session)
    assert token == "fresh-token"


def test_map_eventsearch_args_finds_location_arguments() -> None:
    mapped = map_eventsearch_args(["lat", "lon", "radius", "startDateRange", "query", "first"])
    assert mapped == {"lat": "lat", "lon": "lon", "radius": "radius", "startDateRange": "startDateRange", "query": "query"}


def test_map_eventsearch_args_returns_empty_without_location_arguments() -> None:
    mapped = map_eventsearch_args(["query", "first"])
    assert "lat" not in mapped
    assert "lon" not in mapped


def test_build_eventsearch_query_includes_only_discovered_arguments() -> None:
    query = build_eventsearch_query({"lat": "lat", "lon": "lon"}, lat=30.5, lon=-97.6, radius=50, start_date_range="2026-10-01", query_text="")
    assert "lat: 30.5" in query
    assert "lon: -97.6" in query
    assert "radius" not in query


async def test_validate_stores_discovered_eventsearch_args(rsa_keypair) -> None:  # noqa: ANN001
    private_pem, _ = rsa_keypair
    source = _source(private_pem)

    session = FakeSession()
    session.add(
        "https://secure.meetup.com/oauth2/access",
        FakeResponse(status=200, _json={"access_token": "tok-1", "expires_in": 3600}),
    )
    session.add("https://api.meetup.com/gql-ext", FakeResponse(status=200, _body=load_fixture_text("meetup_introspection_response.json")))

    await source.async_validate(session, _ctx())

    assert source.data["eventsearch_args"]["lat"] == "lat"
    assert source.data["eventsearch_args"]["lon"] == "lon"
    assert source.data["eventsearch_args"]["startDateRange"] == "startDateRange"


async def test_validate_fails_without_location_arguments(rsa_keypair) -> None:  # noqa: ANN001
    private_pem, _ = rsa_keypair
    source = _source(private_pem)

    no_location_schema = {
        "data": {"__schema": {"queryType": {"fields": [{"name": "eventSearch", "args": [{"name": "query"}, {"name": "first"}]}]}}}
    }

    session = FakeSession()
    session.add(
        "https://secure.meetup.com/oauth2/access",
        FakeResponse(status=200, _json={"access_token": "tok-1", "expires_in": 3600}),
    )
    session.add("https://api.meetup.com/gql-ext", FakeResponse(status=200, _body=json.dumps(no_location_schema)))

    with pytest.raises(SourceValidationError, match="location arguments"):
        await source.async_validate(session, _ctx())


async def test_fetch_maps_events_and_drops_online_by_default(rsa_keypair) -> None:  # noqa: ANN001
    private_pem, _ = rsa_keypair
    source = _source(private_pem)
    source.data["eventsearch_args"] = {"lat": "lat", "lon": "lon", "radius": "radius", "startDateRange": "startDateRange", "query": "query"}

    session = FakeSession()
    session.add(
        "https://secure.meetup.com/oauth2/access",
        FakeResponse(status=200, _json={"access_token": "tok-1", "expires_in": 3600}),
    )
    session.add("https://api.meetup.com/gql-ext", FakeResponse(status=200, _body=load_fixture_text("meetup_eventsearch_response.json")))

    events = await source.async_fetch(session, _ctx())

    assert len(events) == 1
    event = events[0]
    assert event.title == "Austin Maker Meetup"
    assert event.city == "Austin"
    assert event.organizer_name == "Austin Makers"
    assert event.latitude == pytest.approx(30.2672)


async def test_fetch_includes_online_events_when_enabled(rsa_keypair) -> None:  # noqa: ANN001
    private_pem, _ = rsa_keypair
    source = _source(private_pem)
    source.data["eventsearch_args"] = {"lat": "lat", "lon": "lon"}
    source.data["include_online"] = True

    session = FakeSession()
    session.add(
        "https://secure.meetup.com/oauth2/access",
        FakeResponse(status=200, _json={"access_token": "tok-1", "expires_in": 3600}),
    )
    session.add("https://api.meetup.com/gql-ext", FakeResponse(status=200, _body=load_fixture_text("meetup_eventsearch_response.json")))

    events = await source.async_fetch(session, _ctx())
    assert len(events) == 2


async def test_fetch_without_hub_coordinates_raises() -> None:
    source = MeetupSource({"name": "Meetup", "client_id": "c", "member_id": "m", "private_key": "k", "category": "community"})
    session = FakeSession()
    with pytest.raises(SourceValidationError):
        await source.async_fetch(session, _ctx(latitude=None, longitude=None))
