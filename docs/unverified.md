# Unverified and not done

Carried forward from `docs/research.md` (items marked UNVERIFIED there), plus
anything this build could not test live because it has no running Home
Assistant instance and no real API credentials.

## From research.md, still unverified

- Whether TFEA's Visit Widget (`tfea.visitwidget.com`) exposes a JSON
  endpoint. If it does, it becomes a `jsonld`-style named source later.
- The Austin Public Library calendar platform and its ICS URL, if any.
- Whether PredictHQ has any free tier.
- Whether SeatGeek's Platform API still issues self-serve keys in 2026.
- Whether Yelp Fusion's Events endpoint is still live or free in 2026.
- Whether any Evensi events API currently exists.
- Whether Hulafrog or Kidlist expose any API.
- Aggregate lead-time statistics for ZAPP and Eventeny vendor applications
  (directional figures only, per research.md section 2).
- Wikidata `inception` (P571) coverage and precision for small Texas towns,
  for seeding manual city-birthday entries.

## Not built in this release (documented non-goals)

- ZAPP and FestivalNet email (IMAP) ingestion.
- A `meetup` source (blocked on a Meetup Pro subscription decision).
- Any scraper against a paywalled vendor directory (ZAPP, FestivalNet,
  Sunshine Artist member areas).
- A custom dashboard card.

## Not verified live in this build

This integration was built and tested against
pytest-homeassistant-custom-component's simulated `hass` fixture in WSL, not
a running Home Assistant instance, and not against real external services.
Specifically not exercised against the real network:

- Real Ticketmaster Discovery API responses (tests use a recorded fixture
  shaped from the documented schema, not a live call).
- Real Eventbrite organization endpoint responses, including real
  pagination via `continuation` (tests use a recorded fixture).
- Real Socrata dataset responses beyond the documented Austin
  `p9ma-z6y9` schema described in research.md; the exact column names for
  any dataset must be checked against that dataset's own API docs before use.
- The vendor probe (`vendor.py: probe_vendor_pages`) against a real
  `robots.txt` and real vendor pages; tests use synthetic HTML fixtures.
- The Companion app notification actions (`EVENT_SCOUT_DISMISS`,
  `EVENT_SCOUT_ADD_CAL`) against a real phone; the event listener and its
  effect on the store are unit tested, the round trip through a real device
  is not.
- GitHub branch protection and the release GitHub App installation on this
  repository; both are explicitly left pending per the standing instruction
  that repository settings changes are reported, not applied unasked.

## Area filter (docs/design-area-filter.md), added 2026-09-22

- The Census geocoder response key path used by `county.py:
  county_name_from_response` (`result.geographies["Counties"][0]["NAME"]`)
  is taken from the design document and Census documentation, not confirmed
  against a live response. `tests/fixtures/census_geocoder_response.json`
  is constructed from documentation in that shape, not recorded from a real
  call; the path must be confirmed against a live response before this is
  treated as settled.
- Whether the public OSRM demo server (`https://router.project-osrm.org`)
  is available at any given time is not something this build can verify or
  guarantee; it carries no service guarantee per its own operators, which
  is why the estimate tier is the default and every routed failure falls
  back to it. `tests/fixtures/osrm_table_response.json` is constructed from
  the OSRM `/table` service documentation, not recorded from a real call.
- Real Census geocoder responses for coordinates outside the continental
  United States (the service is documented as US-only; behavior outside
  that area, including Alaska, Hawaii, and US territories, is not tested).
- The Census geocoder's actual rate limit; it publishes no numeric limit,
  so `county.py` serializes requests with a fixed 0.5 s spacing as a
  conservative default rather than a confirmed safe rate.
