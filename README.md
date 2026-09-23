# Event Scout

Event Scout is a Home Assistant custom integration that aggregates local
events from several sources, keeps a rolling look-ahead window (90 days by
default), exposes calendars and sensors for them, and turns vendor
application windows (booth applications for festivals and markets) into
actionable phone notifications.

## What it does

- Pulls events from ICS feeds, schema.org JSON-LD pages, the Ticketmaster
  Discovery API, Socrata open-data portals, a curated list of Eventbrite
  organizers, and a manual list of recurring dates such as city birthdays.
- Deduplicates events collected from more than one source using title
  similarity, so the same festival listed on an ICS feed and a JSON-LD page
  becomes one entity.
- Extracts vendor (booth) application information where it is published, and
  falls back to a clearly labeled estimate when it is not.
- Publishes two calendars (`calendar.event_scout_events` and
  `calendar.event_scout_vendor_deadlines`), several sensors, and a binary
  sensor for "a vendor window is open right now".
- Sends actionable Companion app notifications for vendor deadlines and daily
  or weekly digests, with buttons to open the application, add it to a
  calendar, or dismiss it.

## Sources

| Source | What it needs | Notes |
| --- | --- | --- |
| `ics` | A `.ics` or `webcal://` URL, optional basic auth | Generic calendar feed source; works with most parks, library, and school calendar platforms. |
| `jsonld` | A page URL | Parses every `schema.org/Event` block in the page's `application/ld+json` scripts. Works with most WordPress (The Events Calendar), Squarespace, and civic CMS event pages. |
| `ticketmaster` | A free Ticketmaster Discovery API key | Uses the hub's location and radius. Ticketed events only; misses most free small-town festivals. |
| `socrata` | A city open-data domain, dataset ID, and a field map | See the Austin example below. |
| `eventbrite` | A personal OAuth token and one or more organizer IDs | Curated organizers only. Eventbrite's public event search shut down in 2019, so this source cannot discover new organizers; it can only poll organizers you already know. |
| `manual` | A recurring month/day or nth-weekday rule | City birthdays and known recurring festivals that have no feed at all. |

### Socrata example: Austin ACCD Event Listings

City of Austin's Convention Center and Palmer Events Center listings are a
public, redistribution-safe dataset. When adding a `socrata` source:

- Domain: `data.austintexas.gov`
- Dataset ID: `p9ma-z6y9`
- Title field: `event_name` (check the dataset's actual column names first;
  Socrata schemas vary by city)
- Start date field: the dataset's start-date column
- An app token is optional at low request volume but recommended.

Any other city's Socrata portal works the same way: find its dataset ID from
the portal's API docs page, and map the field names it actually uses.

### Eventbrite example: reading an organizer ID

Eventbrite organizer pages look like `eventbrite.com/o/some-slug-12345678`.
The trailing digits after the last hyphen are the organizer ID
(`12345678` in that example). Enter one or more of those IDs,
comma-separated, in `organization_ids` when adding an `eventbrite` source.
The token is a personal OAuth token from your Eventbrite account's API keys
page.

## Choosing an area

By default Event Scout includes an event when it matches any enabled area
criterion: a city, a county, or a distance limit from the hub location.
An option (`area_mode`) switches this to requiring every enabled criterion
instead. Set the criteria you want in the integration's options and leave
the rest empty to disable them; leaving all of them empty (or `distance_limit`
at `0` with no cities or counties) disables the area filter entirely and
keeps every event within the horizon.

- **Cities** match `ScoutEvent.city` case-insensitively.
- **Counties** are never guessed from a city name. They are resolved from
  each event's coordinates through the US Census Bureau geocoder, which is
  free and keyless but **covers the United States only**; an event outside
  the US, or without coordinates, cannot be matched by county. Every
  resolved county is cached, so a given coordinate is geocoded once.
- **Distance** is measured from the hub's location, in one of three
  metrics: straight line, estimated driving miles, or estimated driving
  minutes. Events without coordinates cannot be matched by distance or
  county; they can still match by city. The `excluded_counts` sensor
  attribute reports how many events were left out for each reason,
  including lacking coordinates, so the gap stays visible.

### The estimated distance tier (default)

Driving distance defaults to an estimate that makes no network call: the
straight-line distance is multiplied by a **road factor** (default `1.3`;
typical rural Texas values run `1.2` to `1.4`, since actual road distance is
always somewhat longer than a straight line because roads curve around
terrain, property lines, and towns instead of connecting two points
directly). Minutes are derived from that estimated distance and an assumed
**average speed** (default 45 mph). Every value from this tier is labeled
`estimated` everywhere it appears: calendar descriptions, sensor
attributes, digests, and diagnostics. It is never presented as a routed
fact.

### The routed distance tier (optional)

Setting `osrm_url` switches the driving metrics to actual routed distances
and times from an [OSRM](https://project-osrm.org) server, using its table
service so a whole refresh costs a small number of batched requests rather
than one per event. You can point this at a self-hosted OSRM instance, or
at the public demo server `https://router.project-osrm.org`.

**The public OSRM demo server carries no service guarantee.** It can be
slow, rate-limited, or unavailable at any time, and OSRM's own operators do
not promise otherwise. Event Scout treats any OSRM failure as
non-fatal: that batch falls back to the estimated tier for that refresh,
a warning is logged once, and the area filter keeps working. Values from
the routed tier are labeled `routed` wherever the estimated tier is
labeled `estimated`.

## Notifications

Vendor deadline alerts arrive as Companion app actionable notifications with
three buttons: **Open application** (opens the vendor URL directly), **Add to
calendar** (adds the deadline to a calendar entity you choose in the
integration's options), and **Dismiss** (suppresses that specific alert going
forward). See `docs/notifications.md` for the full payload shape and how the
shipped blueprints use it.

## Known coverage limits

Read `docs/research.md` and `docs/decisions.md` for the full picture; the
short version:

- **Facebook events are not covered.** Facebook's public event search and
  the Events API were shut down, and a real share of small-town Texas
  festivals exist only as Facebook events. This is a coverage ceiling, not a
  bug.
- Ticketmaster only covers ticketed events sold through Ticketmaster.
- Eventbrite is curated-organizer only; it is not a discovery source.
- Vendor application data is often estimated, not confirmed, and every
  estimated date is labeled as such everywhere it appears (entity
  attributes, notifications, digests). The integration never presents an
  estimate as a fact.
- Paywalled vendor directories (ZAPP, FestivalNet, Sunshine Artist) are not
  scraped in this release.

## Installation

### HACS (custom repository)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=trooperthorn&repository=ha_int_event_scout&category=integration)

1. In Home Assistant, open HACS, the three-dot menu (top right), **Custom
   repositories**.
2. Paste `https://github.com/trooperthorn/ha_int_event_scout`, choose type
   **Integration**, and select **Add**.
3. Find **Event Scout** in the HACS list and select **Download**.
4. Restart Home Assistant.

### Add the integration

[![Add integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=event_scout)

Go to **Settings, Devices & services, Add integration**, search for
**Event Scout**, and follow the setup flow. After the hub entry is created,
add one or more sources from the integration's own page (its three-dot menu,
**Add source**).

## License

MIT, see `LICENSE`.
