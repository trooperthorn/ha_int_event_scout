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
