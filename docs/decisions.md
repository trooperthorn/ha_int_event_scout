# Design decisions

## Why the dead or paywalled sources are excluded

Per `docs/research.md` section 1 and 2:

- **Eventbrite discovery** (public event search) ended 2019-12-12 and
  whitelisted creator keys were cut off in 2020. Only the organization-scoped
  endpoint still works, so Eventbrite ships as a curated-organizer source
  (`eventbrite`), never as discovery.
- **PredictHQ, SeatGeek, Yelp Fusion Events, AllEvents.in** are commercial,
  gated behind partner approval, or of unverified current availability, with
  no confirmed free tier. None are viable for a single-household MVP.
- **Meetup** has been GraphQL-only since February 2025 and OAuth client
  creation requires an active Meetup Pro subscription. Left as a phase 2 item
  in `docs/unverified.md`, not built, because it is a real recurring cost
  Sean has not committed to.
- **Facebook and Meta Events** are effectively unavailable: public event
  search was removed and the Events API permission is no longer granted.
  This is a genuine coverage ceiling, called out in the README, not a gap
  this integration can close.
- **ZAPP, FestivalNet, Sunshine Artist** are the best sources for vendor
  application data but have no public API and (for FestivalNet and Sunshine
  Artist) are paywalled. Scraping a paywalled member area was explicitly
  ruled a non-goal in `docs/design.md` section 1. ZAPP's weekly digest email
  is a terms-clean path (IMAP ingestion) but is phase 2 work, not build here.

## Why no BeautifulSoup

The only HTML parsing this integration needs is: collecting the text content
of `<script type="application/ld+json">` blocks (`sources/jsonld.py`), and
extracting visible text from a vendor page to search for deadline and fee
patterns (`vendor.py`). Both are done with the standard library's
`html.parser.HTMLParser`, the same approach the Catholic Calendar repository
uses for its own text extraction. Adding BeautifulSoup would be a dependency
for a job two small, auditable parser subclasses already do, and
`manifest.json` requirements should stay to what genuinely is not standard
library plus what core already ships (`ical`, `aiohttp`).

## Why difflib instead of a fuzzy-matching library

`dedup.py` needs one thing: a similarity ratio between two normalized event
titles, used only to decide whether two candidate events in the same
blocking group are the same event. `difflib.SequenceMatcher.ratio()` on a
token-sorted, stopword-stripped string does this well enough at the scale of
a few hundred events per refresh, and it ships in every Python install. A
dedicated library (rapidfuzz, fuzzywuzzy) would add a compiled dependency for
a comparison this integration only runs during deduplication, not on a hot
path, and design.md section 6 specifies this approach directly.

## Why `ical` is a range, not a pin

`check_stale.py` flags `ical>=14.1.1,<15` in `manifest.json` as an
unpinned requirement (review-level, not structural). This is intentional and
matches design.md section 12: `ical==14.1.1` is what core's own
`local_calendar` and `remote_calendar` pin in 2026.9.2, but `ical` is not
listed in core's `package_constraints.txt`, so a custom integration pinning
the exact same version core happens to use today would break the next time
core moves to `ical` 14.2 or 14.3 while this integration's own release
cadence lags behind it. A `<15` range accepts any compatible 14.x release
without requiring a manifest bump merely to track a dependency core already
manages independently.

## Why the vendor probe is opt-in and narrow

`vendor.py`'s `probe_vendor_pages` only runs when a `jsonld` source has
`vendor_probe` enabled, only requests four fixed candidate paths
(`/vendors`, `/vendor-application`, `/exhibitors`, `/apply`), and honors
`robots.txt` disallow rules for `User-agent: *` before requesting any of
them. This keeps the integration's own network footprint small, predictable,
and easy to explain in `SECURITY.md`, at the cost of missing vendor pages at
paths outside that fixed list; `docs/sources.md` documents the limitation.

## Why the US Census geocoder for county resolution

`docs/design-area-filter.md` section 1 requires that county never be
guessed from a city name. The US Census Bureau's geocoder
(`geocoding.geo.census.gov`) resolves coordinates to their containing
county, is free, requires no API key, and is authoritative for US
addresses because it is the source the Census Bureau itself uses for
geography assignment. Its coverage is United States only, which is an
acceptable limit for a household in Texas and is called out in the README.
Every resolved coordinate is cached forever in the Store (`county_cache`,
rounded to three decimal places, about 100 meters), so a given event is
geocoded once across its lifetime, not once per refresh.

## Why OSRM's table service for routed distance

The routed distance tier (`geo.py: OSRMClient`) uses OSRM's `/table`
endpoint rather than repeated `/route` calls. The table service accepts one
origin and many destinations in a single request and returns a full
distance and duration matrix, so a refresh with a few hundred candidate
events costs one HTTP request per batch of 50 destinations instead of one
request per event. OSRM is also the only router with a public,
no-registration demo server (`router.project-osrm.org`), which keeps the
routed tier usable without asking Sean to run infrastructure before trying
it, provided the demo's lack of an availability guarantee is documented
(README, `docs/unverified.md`) and every routed failure falls back to the
estimate tier rather than failing the refresh.

## Why the estimate tier is the default

`distance_metric` defaults to `straight_line`, and even the driving metrics
never call OSRM unless `osrm_url` is explicitly set. A straight-line
distance, or a road-factor estimate of it, requires no network call at all,
so the area filter always works, even with no OSRM server configured and
even when a self-hosted one is temporarily down. Making a routed lookup the
default would mean the area filter's behavior for every user without an
OSRM server depends on the public demo's availability, which
`docs/design-area-filter.md` explicitly says carries no service guarantee.
Every estimated figure is labeled `estimated` (calendar descriptions,
sensor attributes, diagnostics) so the estimate is never presented as a
measured fact.

## Legacy radius_miles seeding excludes coordinate-less events by default

Because `distance_limit` seeds itself from the existing `radius_miles` hub
data key (default 50) when no area options have been set, an upgraded hub
has the distance criterion enabled out of the box. Per
`docs/design-area-filter.md` section 1, an event with no coordinates cannot
be distance- or county-filtered, so with only the seeded distance criterion
enabled and no cities configured, such an event (for example, a `manual`
source city birthday, which never carries coordinates) is excluded rather
than passed through unfiltered as it was before this feature. This is a
real behavior change on upgrade, not an incidental side effect: anyone
relying on coordinate-less sources should add at least one city to
`cities`, or set `distance_limit` to `0`, to keep those events included.
The README's "Choosing an area" section and this note are how that trade-off
is surfaced; there is no way to make "match nothing extra by default" and
"seed the existing radius as a working distance filter" both true at once.

## Manual events always pass the area filter; include_unlocated controls the rest

PR #10's first cut excluded any coordinate-less event once a county or
distance criterion was enabled, with no way to opt back in except adding a
matching city. Two problems: a `manual` source event (a city birthday, a
known recurring festival) is user curated, entered by hand specifically
because Sean wants to see it, and should never be silently dropped by a
filter meant for automatically discovered events. And for every other
source, defaulting to "excluded" on upgrade was a worse default than
"included, but counted" (`excluded_counts.no_coordinates`), since most
households would rather see an event they have to double check than lose it
without noticing. `area.py: AreaFilter.decide` now special-cases
`source_kind == "manual"` to always include, and adds `include_unlocated`
(default `True`) for every other source: on, a coordinate-less event is
always included; off, it is excluded and counted, unless the city criterion
is enabled and the event's city matches, which is always honored regardless
of `include_unlocated` since city needs no coordinates to test.

## Why no paid routing API

A paid routing API (Google Distance Matrix, Mapbox, HERE) would give exact
driving distances without asking Sean to run OSRM himself, but it would
also mean the area filter, a feature meant to run unattended on a schedule,
depends on a billed, keyed, rate-limited third-party service by default.
That contradicts `docs/design.md`'s own non-goal list, which already
excludes paid APIs wherever a free path exists, and the two free tiers
(no-network estimate, self-hosted or demo OSRM) cover the stated
requirement well enough for a single household's use.
