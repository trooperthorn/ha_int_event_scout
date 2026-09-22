# Area filter design: city, county, and driving distance

Addendum to `docs/design.md` (2026-09-22). This replaces the single
`radius_miles` filter in design section 5 step 2 with an area filter that can
combine a city list, a county list, and a distance limit, and that can express
the distance limit as an estimated driving distance or driving time instead
of a straight line.

## 1. Requirements

- Include an event when it matches any enabled criterion (OR across city,
  county, and distance), so a user can say "Travis County, plus Georgetown,
  plus anything within 40 driving miles". A hub option switches this to AND
  for users who want the intersection.
- Distance is measured from the hub location. The user chooses the metric:
  straight line, estimated driving miles, or estimated driving minutes.
- Driving distance never comes from a paid API by default. Two tiers:
  1. Estimate without any network call: straight line times a road factor
     (default 1.3, configurable; typical rural Texas values run 1.2 to 1.4).
     Labeled `estimated` everywhere.
  2. Optional routed distance from an OSRM server the user names (self-hosted
     or the public demo at `https://router.project-osrm.org`, which carries
     no service guarantee and must be documented as such). Uses the table
     service so many events cost one request. Labeled `routed`.
- County is never guessed from a city name. It is resolved from coordinates
  through the US Census Bureau geocoder, which is free, keyless, and
  authoritative for US addresses, and every result is cached so an event is
  resolved once.
- Events with no coordinates cannot be distance or county filtered; they
  match only by city. The digest and sensors state how many events were
  excluded for lack of coordinates so the gap is visible.

## 2. Configuration (hub options, `OptionsFlowWithReload`)

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `area_mode` | select: `any`, `all` | `any` | OR or AND across enabled criteria |
| `cities` | list of strings | empty | Case-insensitive match on `ScoutEvent.city`; empty disables the criterion |
| `counties` | list of strings | empty | Match on resolved county name without the word County; empty disables |
| `distance_metric` | select: `straight_line`, `driving_miles`, `driving_minutes` | `straight_line` | |
| `distance_limit` | number | 50 | Miles, or minutes when the metric is `driving_minutes`; 0 disables |
| `road_factor` | number 1.0 to 2.0 | 1.3 | Used by the estimate tier for both miles and minutes |
| `average_speed_mph` | number | 45 | Estimate tier only: minutes = estimated miles / speed * 60 |
| `osrm_url` | string | empty | When set, the routed tier is used and the estimate tier is the fallback on error |

The legacy `radius_miles` hub data key stays readable; on first load it seeds
`distance_limit` with `straight_line` when the option is absent. No
migration version bump is needed because options are additive.

## 3. Runtime additions

```text
custom_components/event_scout/
  area.py        AreaFilter: decide(event) -> AreaDecision
  geo.py         haversine (moved from coordinator), road estimate, OSRM table client
  county.py      CountyResolver: Census geocoder client with Store-backed cache
```

`ScoutEvent` gains `county: str | None`, `drive_miles: float | None`,
`drive_minutes: float | None`, and `distance_origin: Literal["straight",
"estimated", "routed"] | None`. `distance_miles` keeps the straight-line
value.

`AreaDecision` is a small dataclass: `included: bool`, `matched: list[str]`
(which criteria matched, for the digest and diagnostics), `reason: str`
(why excluded, for the source status counters).

Coordinator step 2 becomes: compute straight-line distance for every event
with coordinates; if the distance metric is driving, compute the drive tier
(routed when `osrm_url` is set, otherwise estimated); if counties are
configured, resolve the county for events with coordinates; then apply
`AreaFilter`. `ScoutData` gains `excluded_counts: dict[str, int]` keyed by
reason (`outside_area`, `no_coordinates`, `county_unresolved`).

## 4. External calls

Census geocoder, coordinates to geographies:
`https://geocoding.geo.census.gov/geocoder/geographies/coordinates?x=<lon>&y=<lat>&benchmark=Public_AR_Current&vintage=Current_Current&format=json`.
The county name is `result.geographies["Counties"][0]["NAME"]` (this key
path must be confirmed against a live response before the fixture is
written; record the raw response as the test fixture). One request per
unique coordinate rounded to three decimals, cached forever in the Store
under `county_cache`. Serialize requests with a 0.5 s spacing; the geocoder
publishes no numeric limit.

OSRM table service:
`<osrm_url>/table/v1/driving/<lon>,<lat>;<lon1>,<lat1>;...?sources=0&annotations=distance,duration`.
Batch at most 50 destinations per request. `distances` are meters,
`durations` seconds. Cache per rounded coordinate in the Store under
`route_cache` with a 30-day age. Any HTTP or parse error falls back to the
estimate tier for that batch and records a warning once per refresh, not a
repair issue, because the estimate tier keeps the feature working.

## 5. Surfaces

- Calendar event descriptions gain one line: `Drive: about 32 mi, 41 min
  (estimated)` or `(routed)`, and `County: Williamson` when resolved.
- `sensor.event_scout_upcoming_events` attributes gain `excluded_counts` and
  `area_summary` (a human sentence such as "Travis or Williamson County, or
  within 40 driving miles (estimated)").
- Digest text groups events by county when counties are configured.
- Diagnostics include the area options, cache sizes, and the last OSRM error
  with the URL host redacted to its hostname only.

## 6. Tests

Unit tests for `geo.py` (haversine known pair, road estimate arithmetic,
OSRM table parsing from a recorded fixture, batch splitting at 50), for
`county.py` (fixture parse, cache hit avoids a second request, unresolved
coordinates return None without raising), and for `area.py` (each criterion
alone, `any` versus `all`, no-coordinate events, legacy `radius_miles`
seeding). Coordinator tests assert `excluded_counts` and that an OSRM failure
falls back to the estimate with `distance_origin == "estimated"`.

## 7. Honesty rules

Every drive figure carries its origin. The word "about" precedes estimated
values in user-facing text. The README states that the public OSRM demo
server has no availability promise and that the Census geocoder covers only
the United States.
