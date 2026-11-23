"""Meetup GraphQL source.

Uses a JWT (server to server) OAuth client, the only unattended flow Meetup
supports since it went GraphQL-only in February 2025 (docs/research.md,
docs/decisions.md). The exact eventSearch argument names are UNVERIFIED
without a live Meetup Pro token (docs/unverified.md); validate() runs an
introspection query against the live schema and stores the discovered
argument names in the subentry data, and fetch() only ever uses those
discovered names, never a hardcoded guess. See docs/design-optional-sources.md
section 1.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import aiohttp
import jwt

from ..const import CATEGORY_OTHER, SOURCE_KIND_MEETUP
from ..models import ScoutEvent
from .base import Source, SourceContext, SourceValidationError

TOKEN_URL = "https://secure.meetup.com/oauth2/access"
GRAPHQL_URL = "https://api.meetup.com/gql-ext"
JWT_AUDIENCE = "api.meetup.com"
JWT_TTL_SECONDS = 120
TOKEN_REFRESH_MARGIN_SECONDS = 60

INTROSPECTION_QUERY = """
{
  __schema {
    queryType {
      fields {
        name
        args {
          name
        }
      }
    }
  }
}
"""

_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


def _sign_jwt(client_id: str, member_id: str, private_key: str) -> str:
    """Sign a short-lived RS256 JWT assertion for the jwt-bearer grant."""
    now = int(time.time())
    payload = {
        "iss": client_id,
        "sub": member_id,
        "aud": JWT_AUDIENCE,
        "exp": now + JWT_TTL_SECONDS,
        "iat": now,
    }
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": client_id})


def map_eventsearch_args(arg_names: list[str]) -> dict[str, str]:
    """Map introspected eventSearch argument names to the concepts fetch() needs."""
    mapped: dict[str, str] = {}
    for name in arg_names:
        lowered = name.lower()
        if "lat" in lowered and "lat" not in mapped:
            mapped["lat"] = name
        elif "lon" in lowered and "lon" not in mapped:
            mapped["lon"] = name
        elif "radius" in lowered and "radius" not in mapped:
            mapped["radius"] = name
        elif "startdate" in lowered and "startDateRange" not in mapped:
            mapped["startDateRange"] = name
        elif lowered == "query" and "query" not in mapped:
            mapped["query"] = name
    return mapped


def build_eventsearch_query(args: dict[str, str], *, lat: float, lon: float, radius: int, start_date_range: str, query_text: str) -> str:
    """Build the eventSearch GraphQL query using only the discovered argument names."""
    parts = [f"{args['lat']}: {lat}", f"{args['lon']}: {lon}"]
    if "radius" in args:
        parts.append(f"{args['radius']}: {radius}")
    if "startDateRange" in args:
        parts.append(f'{args["startDateRange"]}: "{start_date_range}"')
    if "query" in args and query_text:
        parts.append(f'{args["query"]}: "{query_text}"')
    arg_str = ", ".join(parts)
    return f"""
    {{
      eventSearch({arg_str}) {{
        edges {{
          node {{
            id
            title
            description
            eventUrl
            dateTime
            endTime
            isOnline
            venue {{ name address city state lat lng }}
            group {{ name }}
          }}
        }}
      }}
    }}
    """


def _event_from_node(node: dict, *, ctx: SourceContext, category: str) -> ScoutEvent | None:
    date_time = node.get("dateTime")
    if not date_time:
        return None
    start = datetime.fromisoformat(date_time)
    end_raw = node.get("endTime")
    end = datetime.fromisoformat(end_raw) if end_raw else None

    venue = node.get("venue") or {}
    latitude = float(venue["lat"]) if venue.get("lat") is not None else None
    longitude = float(venue["lng"]) if venue.get("lng") is not None else None
    group = node.get("group") or {}

    return ScoutEvent(
        uid="",
        series_key="",
        source_kind=SOURCE_KIND_MEETUP,
        source_name=ctx.name,
        source_event_id=str(node.get("id") or node.get("eventUrl") or date_time),
        title=str(node.get("title") or "Untitled event"),
        description=node.get("description"),
        url=node.get("eventUrl"),
        start=start,
        end=end,
        all_day=False,
        venue_name=venue.get("name"),
        address=venue.get("address"),
        city=venue.get("city"),
        state=venue.get("state"),
        latitude=latitude,
        longitude=longitude,
        category=category,  # type: ignore[arg-type]
        organizer_name=group.get("name"),
    )


class MeetupSource(Source):
    """Meetup GraphQL source using a JWT (server to server) OAuth client."""

    kind = SOURCE_KIND_MEETUP

    async def _async_get_token(self, session: aiohttp.ClientSession) -> str:
        client_id = self.data["client_id"]
        cached = _TOKEN_CACHE.get(client_id)
        now = time.time()
        if cached and cached[1] - TOKEN_REFRESH_MARGIN_SECONDS > now:
            return cached[0]

        assertion = _sign_jwt(client_id, self.data["member_id"], self.data["private_key"])
        form = {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}
        try:
            async with session.post(TOKEN_URL, data=form, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 401:
                    raise SourceValidationError("Meetup rejected the JWT client credentials")
                resp.raise_for_status()
                payload = await resp.json()
        except aiohttp.ClientError as err:
            raise SourceValidationError(f"Could not reach Meetup's token endpoint: {err}") from err

        access_token = payload.get("access_token")
        if not access_token:
            raise SourceValidationError("Meetup's token response did not include an access_token")
        expires_in = payload.get("expires_in", 3600)
        _TOKEN_CACHE[client_id] = (access_token, now + expires_in)
        return access_token

    async def _async_graphql(self, session: aiohttp.ClientSession, token: str, query: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with session.post(GRAPHQL_URL, json={"query": query}, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                payload = await resp.json()
        except aiohttp.ClientError as err:
            raise SourceValidationError(f"Could not reach Meetup's GraphQL endpoint: {err}") from err

        if payload.get("errors"):
            raise SourceValidationError(f"Meetup GraphQL returned errors: {payload['errors']}")
        return payload.get("data") or {}

    async def async_validate(self, session: aiohttp.ClientSession, ctx: SourceContext) -> None:
        """Exchange the JWT, then introspect eventSearch and store its argument names."""
        token = await self._async_get_token(session)
        data = await self._async_graphql(session, token, INTROSPECTION_QUERY)

        fields = data.get("__schema", {}).get("queryType", {}).get("fields", [])
        event_search = next((f for f in fields if f.get("name") == "eventSearch"), None)
        if event_search is None:
            raise SourceValidationError("Meetup's GraphQL schema does not expose an eventSearch field")

        arg_names = [a["name"] for a in event_search.get("args", [])]
        mapped = map_eventsearch_args(arg_names)
        if "lat" not in mapped or "lon" not in mapped:
            raise SourceValidationError("eventSearch has no location arguments; cannot filter by the hub location")

        self.data["eventsearch_args"] = mapped

    async def async_fetch(self, session: aiohttp.ClientSession, ctx: SourceContext) -> list[ScoutEvent]:
        """Fetch events near the hub location using the introspected eventSearch arguments."""
        if ctx.latitude is None or ctx.longitude is None:
            raise SourceValidationError("Meetup requires a hub latitude and longitude")

        args = self.data.get("eventsearch_args")
        if not args:
            await self.async_validate(session, ctx)
            args = self.data["eventsearch_args"]

        token = await self._async_get_token(session)
        radius = int(ctx.radius_miles or 50)
        start_range = datetime.now(tz=UTC).date().isoformat()
        query_text = self.data.get("query") or ""

        query = build_eventsearch_query(
            args, lat=ctx.latitude, lon=ctx.longitude, radius=radius, start_date_range=start_range, query_text=query_text
        )
        data = await self._async_graphql(session, token, query)

        include_online = bool(self.data.get("include_online", False))
        category = self.data.get("category", CATEGORY_OTHER)
        events: list[ScoutEvent] = []
        edges = (data.get("eventSearch") or {}).get("edges", [])
        for edge in edges:
            node = edge.get("node") or {}
            if node.get("isOnline") and not include_online:
                continue
            event = _event_from_node(node, ctx=ctx, category=category)
            if event is not None:
                events.append(event)
        return events
