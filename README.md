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
