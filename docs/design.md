# Event Scout design

Event Scout is a Home Assistant custom integration (domain `event_scout`) that
aggregates local events from several sources, keeps a rolling 90-day horizon,
exposes calendars and sensors, and turns vendor application windows into
actionable notifications that a user can act on from a phone.

Inputs to this design: `docs/research.md` (2026-09-22), the core 2026.9.2
source clone, and the house conventions in the ha-dev-current and
trooperthorn-projects skills. Every Home Assistant identifier named here was
grepped in the core clone before being written down.

## 1. Goals and non-goals

Goals:

- Daily and weekly digests of upcoming events, filterable by category
  (festival, family, city anniversary, community, other).
- A 90-day look-ahead that is a configurable horizon, default 90.
- Vendor tracking per event: application open date, deadline, fee, URL, and
  confidence, with notifications at configurable lead times.
- Notifications that a user can act on: open the application, add the event
  or deadline to a calendar, dismiss.
- A source plugin layer so new feeds are one file plus tests.

Non-goals for the first release:

- Scraping paywalled vendor directories (ZAPP, FestivalNet, Sunshine Artist).
- Facebook, Nextdoor, Eventbrite discovery, PredictHQ, SeatGeek, Yelp; all
  are closed, paid, unshipped, or dead per the research. Eventbrite is
  included only as a curated-organizer source.
- Meetup GraphQL (alive, but an OAuth client requires a paid Meetup Pro
  subscription; phase 2 if Sean holds one).
- IMAP ingestion of ZAPP and FestivalNet emails (phase 2).
- A custom dashboard card (the Companion app notification is the UI).

## 2. Configuration model

One hub config entry plus one subentry per source, using the core subentry
flow (`ConfigSubentryFlow` in `homeassistant/config_entries.py`, verified
present in 2026.9.2).

Hub entry (`ConfigFlow`):

| Field | Default | Notes |
| --- | --- | --- |
| `name` | Event Scout | Entry title |
| `latitude`, `longitude` | `hass.config.latitude/longitude` | Center for radius filters and distance |
| `radius_miles` | 50 | Applied to sources that support geo filtering; others are trusted as-is |
| `horizon_days` | 90 | Event look-ahead |
| `update_interval_hours` | 6 | Coordinator poll; never below 1 |

Hub options (`OptionsFlowWithReload`, no `__init__`, read
`self.config_entry`):

| Field | Default |
| --- | --- |
| `notify_service` | empty (no automatic notifications) |
| `vendor_lead_days` | `[30, 14, 3]` |
| `reconnaissance_days` | 240 |
| `digest_time` | 07:00 local |
| `categories` | all |

Source subentries (subentry type `source`, one flow step to pick the source
kind, one typed step for its arguments):

| Source kind | Arguments | Notes |
| --- | --- | --- |
| `ics` | `url`, `name`, `category`, optional `username`/`password` | webcal:// rewritten to https://; ETag and Last-Modified cached |
| `jsonld` | `url`, `name`, `category`, `vendor_probe` (bool) | Parses every `application/ld+json` block with `@type` Event or a list containing Event |
| `ticketmaster` | `api_key`, `segments` (multi-select: Family, Arts & Theatre, Music, Miscellaneous), `keyword` | Uses hub lat/lon and radius; `family=true` when Family selected |
| `socrata` | `domain`, `dataset_id`, field map (`title`, `start`, `end`, `url`, `venue`), optional `app_token` | Austin `p9ma-z6y9` is the documented example |
| `manual` | `name`, `title`, `category`, recurrence (`month`, `day` or `nth_weekday`), `city`, optional vendor fields | City birthdays and known recurring festivals |
| `eventbrite` | `token`, `organization_ids` (list), optional `venue_ids`, `category` | Curated organizers only; no discovery exists (research section 6). Polls `/v3/organizations/{id}/events/?status=live&expand=venue`; budget 1,000 calls per hour |

Secrets (`api_key`, `password`, `app_token`) are stored in the subentry data
and masked in diagnostics.

## 3. Runtime layout

```text
custom_components/event_scout/
  __init__.py          async_setup (services), async_setup_entry, async_unload_entry
  config_flow.py       ConfigFlow, OptionsFlowWithReload, SourceSubentryFlow
  const.py
  coordinator.py       EventScoutCoordinator(DataUpdateCoordinator[ScoutData])
  models.py            ScoutEvent, VendorInfo, ScoutData dataclasses
  store.py             Store-backed overrides, dismissals, series memory, uid map
  dedup.py             blocking + scoring + merge
  vendor.py            explicit extraction + heuristics + alert schedule
  digest.py            daily/weekly digest builder, notification payload builder
  sources/
    __init__.py        registry: SOURCES = {kind: SourceSpec}
    base.py            Source ABC: async fetch(session, ctx) -> list[ScoutEvent]
    ics.py, jsonld.py, ticketmaster.py, socrata.py, manual.py, eventbrite.py
  calendar.py          EventsCalendar, VendorDeadlinesCalendar
  sensor.py            counts, next deadline
  binary_sensor.py     vendor_application_open (any)
  diagnostics.py
  services.yaml
  translations/en.json
  icons.json
  quality_scale.yaml
  manifest.json
blueprints/automation/event_scout/
  daily_digest.yaml, weekly_digest.yaml, vendor_alert_actions.yaml
```

`entry.runtime_data` holds the coordinator through a typed alias
`type EventScoutConfigEntry = ConfigEntry[EventScoutCoordinator]`. Nothing
goes in `hass.data[DOMAIN]` except the shared aiohttp session accessor
already provided by core (`async_get_clientsession`).

## 4. Data model

`ScoutEvent` (frozen dataclass):

```text
uid, series_key, source_kind, source_name, source_event_id
title, description, url
start, end (date or datetime), all_day
venue_name, address, city, state, latitude, longitude, distance_miles
category (festival | family | city_anniversary | community | other)
is_free, cost_text
organizer_name, organizer_url
vendor: VendorInfo | None
first_seen, last_seen
```

`VendorInfo`:

```text
available: Literal["yes", "no", "unknown"]
app_open, app_deadline, notify_date: date | None
app_url, booth_fee_text, jury_fee_text
categories: list[str]
juried: bool | None
origin: Literal["explicit", "heuristic", "manual"]
confidence: float
```

`ScoutData` is what the coordinator publishes: `events` (deduplicated,
sorted), `deadlines` (derived list of `(event, alert_kind, when)`),
`source_status` (per subentry: ok, error text, last success time,
event count).

## 5. Coordinator cycle

1. For each source subentry, run `fetch` with a per-source timeout of 30 s.
   A source failure is recorded in `source_status`, raises a repair issue
   (`issue_registry.async_create_issue`, id `source_failed_<subentry_id>`,
   cleared on the next success), and does not raise `UpdateFailed` unless
   every source failed.
2. Filter to `[today, today + horizon_days]` and, when coordinates are
   present, to `radius_miles` using the haversine distance.
3. Deduplicate (section 6) and assign stable uids from the store.
4. Apply vendor extraction and heuristics (section 7), then manual overrides
   from the store, which always win.
5. Compute the alert schedule (section 8) and drop alerts the store marks
   dismissed.
6. Persist series memory: for every event with an explicit deadline, record
   `series_key -> deadline offset in days` so next year's edition inherits it.

The coordinator uses `DataUpdateCoordinator(hass, LOGGER, config_entry=entry,
name=..., update_interval=timedelta(hours=n))` and `_async_setup` to load
the store once.

## 6. Deduplication

Blocking key: `(start date rounded to day, geo cell of 0.05 degrees or city
name when no coordinates)`. Within a block, score pairs:

- title similarity on a normalized form (lowercase, strip ordinals, "annual",
  "festival", "fest", "the", punctuation) using `difflib.SequenceMatcher`
  ratio on token-sorted strings; no third-party fuzzy library.
- plus 0.1 when URL hosts match, plus 0.1 when venue tokens overlap.
- Merge at 0.85 or higher.

Field precedence on merge: manual, then jsonld from the event's own site,
then socrata, then ticketmaster, then ics. The winning event keeps its uid;
losers are recorded as aliases in the store so a later refresh maps them to
the same uid.

`series_key` is `slug(normalized title) + "|" + slug(city or venue)`; the
year is deliberately excluded.

## 7. Vendor information

Explicit extraction, in order:

1. `manual` source fields.
2. JSON-LD on the event page: `offers` with names containing vendor,
   exhibitor, booth; any `Event` whose name contains "vendor application";
   `validFrom` and `validThrough` map to open and deadline.
3. When `vendor_probe` is on, fetch up to four candidate paths on the event's
   host (`/vendors`, `/vendor-application`, `/exhibitors`, `/apply`) with
   robots.txt honored, then extract dates near the words deadline, due, close,
   and dollar amounts near booth, jury, fee. Anything found this way is
   `origin=explicit, confidence=0.7`; anything from JSON-LD is 0.9.

Heuristics when nothing explicit exists and the series memory has no offset:

| Category | Open | Deadline | Confidence |
| --- | --- | --- | --- |
| festival, juried keywords present | event minus 300 d | event minus 180 d | 0.4 |
| festival, community | event minus 150 d | event minus 60 d | 0.4 |
| family, community | event minus 90 d | event minus 45 d | 0.3 |
| other | none | none | 0 |

Heuristic dates are labeled as estimates in every entity attribute and every
notification. The integration never presents an estimate as a fact.

## 8. Alerts and notifications

Alert kinds:

- `reconnaissance`: at event minus `reconnaissance_days` for events whose
  vendor availability is unknown.
- `deadline`: at deadline minus each of `vendor_lead_days`.
- `opens`: on the application open date.

Each alert has a tag `event_scout_<uid>_<kind>_<days>` so a notification can
be replaced or cleared. Alerts are exposed two ways:

1. The Vendor Deadlines calendar, whose events are the alerts themselves
   (all-day, summary "Apply: <title> (deadline <date>[, estimated])"), so
   core calendar triggers can drive automations without any custom trigger.
2. The service `event_scout.send_alerts`, which builds Companion app
   notification payloads and calls the configured notify service.

Notification payload shape (verified against the Companion app
documentation cited in the research):

```yaml
title: "Vendor deadline in 14 days: Old Settler's Music Festival"
message: "Deadline 2027-01-15 (estimated). Booth fee $150. Tap to open."
data:
  tag: event_scout_<uid>_deadline_14
  channel: Event Scout
  importance: high
  url: <vendor app url>
  actions:
    - action: URI
      title: Open application
      uri: <vendor app url>
    - action: EVENT_SCOUT_ADD_CAL
      title: Add to calendar
    - action: EVENT_SCOUT_DISMISS
      title: Dismiss
  action_data:
    uid: <uid>
    tag: <tag>
```

The integration listens for `mobile_app_notification_action` events in
`async_setup_entry`. `EVENT_SCOUT_DISMISS` records the tag as dismissed in
the store and clears the notification. `EVENT_SCOUT_ADD_CAL` calls
`calendar.create_event` on the calendar entity named in options
(`target_calendar`, default none, in which case the action only records that
the user wants it and the digest reminds them to set a target).

Digest services:

- `event_scout.get_digest` (`SupportsResponse.ONLY`): `period` daily or
  weekly, optional `categories`; returns structured events and deadlines
  plus a rendered markdown text.
- `event_scout.send_digest`: same inputs, sends through the notify service
  with an Open dashboard URI action.
- `event_scout.set_vendor_info`: manual override for one uid; fields from
  `VendorInfo`, stored with `origin=manual`.
- `event_scout.refresh`: request a coordinator refresh.

Shipped blueprints call these services at `digest_time` daily and on the
chosen weekday weekly, and a third blueprint wires calendar triggers on the
Vendor Deadlines calendar to `send_alerts`.

## 9. Entities

| Entity | Type | State | Attributes |
| --- | --- | --- | --- |
| `calendar.event_scout_events` | calendar | on during an event | none (events carry category in description) |
| `calendar.event_scout_vendor_deadlines` | calendar | on on a deadline day | none |
| `sensor.event_scout_upcoming_events` | sensor, count | events in horizon | `by_category`, `next_event` |
| `sensor.event_scout_next_vendor_deadline` | sensor, timestamp | next deadline | `title`, `url`, `estimated`, `fee` |
| `sensor.event_scout_vendor_applications_open` | sensor, count | open windows now | `items` (uid, title, deadline, url) |
| `sensor.event_scout_source_<subentry>` | sensor, count | events from that source | `status`, `last_success`, `error` |
| `binary_sensor.event_scout_vendor_window_open` | binary sensor | any open window | none |

All entities are on one device (`DeviceEntryType.SERVICE`) owned by the hub
entry. Per-source sensors carry the subentry id in their unique id so
removing a subentry removes them.

## 10. Storage

`homeassistant.helpers.storage.Store` version 1, key
`event_scout.<entry_id>`:

```text
uid_aliases: {alias_key: uid}
series_offsets: {series_key: {deadline_offset_days, open_offset_days, seen}}
overrides: {uid: VendorInfo as dict}
dismissed: {tag: iso timestamp}
```

## 11. Quality scale target

Bronze complete, Silver complete, Gold where it does not require a device.
`quality_scale.yaml` records each rule honestly. Notable rules: `runtime-data`
done, `test-before-configure` done (each source validates its arguments by
fetching once), `unique-config-entry` done (one hub per location name),
`diagnostics` done with secrets redacted, `repair-issues` done for source
failures, `parallel-updates` set to 0, `entity-translations` done.

## 12. Requirements

`ical>=14.1.1,<15` for ICS parsing (the version core's local_calendar pins in
2026.9.2; not in `package_constraints.txt`, so a range is safe). Everything
else is standard library plus aiohttp from core. No BeautifulSoup: JSON-LD is
read with `html.parser` collecting `script` blocks, and the vendor probe uses
regular expressions on visible text extracted the same way the Catholic
Calendar repo does.

## 13. Testing

pytest-homeassistant-custom-component 0.13.365 with `homeassistant==2026.9.2`
pinned; run in WSL Ubuntu (the harness imports `fcntl`). Fixtures under
`tests/fixtures/` hold one recorded response per source kind, a JSON-LD page
with and without vendor offers, and a vendors page for the probe. Tests
cover: config and subentry flows, each source parser, dedup merges and uid
stability across two refreshes, heuristic table, alert schedule and
dismissal, notification payload, digest service response, calendar
`async_get_events` bounds, diagnostics redaction. Target coverage 90% or
higher.

## 14. Release and security baseline

Apply the ha-dev baseline: manifest-driven CalVer on merge to main, SHA-pinned
workflows with `permissions: contents: read`, hassfest and hacs/action gates,
SBOM and attestation, branch protection on main, `.release.json`. The GitHub
App private key stays Sean's to set.

## 15. Open items for Sean

- Whether TFEA's Visit Widget exposes JSON (research marked UNVERIFIED); if
  it does, it becomes a `jsonld`-style named source.
- The Austin Public Library calendar platform and its ICS URL.
- A Ticketmaster API key, which he creates himself.
- Phase 2: IMAP ingestion of the ZAPP weekly deadline email.
- Phase 2: a `meetup` source behind the JWT flow, if a Meetup Pro
  subscription is acceptable.
- Nextdoor Events search: recheck around 2027-03 for general availability.
