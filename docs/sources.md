# Source argument reference

Every source is added as a subentry on the Event Scout hub entry (the
integration's own page, three-dot menu, **Add source**). The first step
picks the source kind; the second step collects that kind's arguments below.

## `ics`

| Field | Required | Notes |
| --- | --- | --- |
| `name` | yes | Display name; becomes this source's per-source sensor name. |
| `url` | yes | An `.ics` URL. `webcal://` is rewritten to `https://` automatically. |
| `category` | yes | One of `festival`, `family`, `city_anniversary`, `community`, `other`. Applied to every event from this feed. |
| `username`, `password` | no | HTTP basic auth, if the feed requires it. |

## `jsonld`

| Field | Required | Notes |
| --- | --- | --- |
| `name` | yes | Display name. |
| `url` | yes | The page to fetch and parse for `schema.org/Event` JSON-LD blocks. |
| `category` | yes | Applied to every event found on this page. |
| `vendor_probe` | no, default off | When on, probes `/vendors`, `/vendor-application`, `/exhibitors`, `/apply` on the same host for vendor deadline and fee text. See `docs/decisions.md` for why the probe is narrow and robots.txt-respecting. |

## `ticketmaster`

| Field | Required | Notes |
| --- | --- | --- |
| `name` | yes | Display name. |
| `api_key` | yes | A free Ticketmaster Discovery API key (5,000 calls/day). |
| `segments` | no | Multi-select from Family, Arts & Theatre, Music, Miscellaneous. Selecting Family also sets `includeFamily=only`. |
| `keyword` | no | Free-text keyword filter. |

Uses the hub's configured latitude, longitude, and radius. No vendor
application data; Ticketmaster only covers ticketed events.

## `socrata`

| Field | Required | Notes |
| --- | --- | --- |
| `name` | yes | Display name. |
| `domain` | yes | The Socrata portal's domain, e.g. `data.austintexas.gov`. |
| `dataset_id` | yes | The dataset's four-by-four ID, e.g. `p9ma-z6y9`. |
| `category` | yes | Applied to every row. |
| `field_title` | yes, default `title` | The dataset's title/name column. |
| `field_start` | yes, default `start_date` | The dataset's start-date column. |
| `field_end` | no | The dataset's end-date column, if any. |
| `field_url` | no | A column with a link to the event. |
| `field_venue` | no | A column naming the venue. |
| `app_token` | no | Recommended at any real request volume; register one on the portal. |

The exact column names vary by city. Check the dataset's own API
documentation page before configuring the field map. Austin's ACCD Event
Listings (`p9ma-z6y9`) is the documented reference dataset; see the README.

## `eventbrite`

| Field | Required | Notes |
| --- | --- | --- |
| `name` | yes | Display name. |
| `token` | yes | A personal OAuth token from your Eventbrite account's API keys page. |
| `organization_ids` | yes | Comma-separated Eventbrite organizer IDs. Read one from an `eventbrite.com/o/<slug>-<id>` URL; the trailing digits are the ID. |
| `venue_ids` | no | Comma-separated venue IDs; when set, only events at those venues are kept. |
| `category` | yes | Applied to every event from these organizers. |

Curated organizers only; there is no Eventbrite discovery endpoint left to
poll (`docs/decisions.md`). Fetches `GET
/v3/organizations/{id}/events/?status=live&expand=venue` for each configured
organizer and follows `pagination.has_more_items` via `continuation`.

## `manual`

| Field | Required | Notes |
| --- | --- | --- |
| `name` | yes | Source display name. |
| `title` | yes | The event's title. |
| `category` | yes | Applied to this event. |
| `month` | yes | 1-12. |
| `day` | one of `day` or `weekday`/`nth` | Fixed day of month. |
| `weekday`, `nth` | one of `day` or `weekday`/`nth` | `weekday` is 0=Monday; `nth` is 1-5 or -1 for the last occurrence. |
| `city` | no | Recorded on the event. |
| `vendor_open`, `vendor_deadline`, `vendor_url` | no | If set, the event carries a manual (`origin=manual`, confidence 1.0) vendor record instead of a heuristic estimate. |

No network access; used for city birthdays and known recurring festivals
that have no feed at all.

## `meetup`

| Field | Required | Notes |
| --- | --- | --- |
| `name` | yes | Display name. |
| `client_id` | yes | The Meetup OAuth client's ID (used as both the JWT `iss` and `kid`). Requires a Meetup Pro subscription to create; see the README. |
| `member_id` | yes | Your Meetup member ID (the JWT `sub`). |
| `private_key` | yes | The RSA private key (PEM) registered with the OAuth client. Multi-line; pasted directly, never a file path. |
| `query` | no | Keyword filter passed to `eventSearch`. |
| `category` | yes | Applied to every event from this source. |
| `include_online` | no, default off | When off, events with `isOnline: true` are dropped. |
| `topic_category_ids` | no | Meetup topic category IDs, if the live schema exposes that argument; leave empty when unknown. |

Uses a JWT (server to server) OAuth client, the only unattended auth flow
Meetup supports since going GraphQL-only in 2025 (`docs/decisions.md`). The
exact `eventSearch` argument names are UNVERIFIED without a live Pro token
(`docs/unverified.md`); validate runs an introspection query and stores the
discovered argument names on the subentry, and fetch only ever uses those
discovered names. Uses the hub's latitude, longitude, and radius. No vendor
application data.

## `vendor_email`

| Field | Required | Notes |
| --- | --- | --- |
| `name` | yes | Display name. |
| `server` | yes | IMAP server hostname. |
| `port` | no, default `993` | IMAP over TLS only; there is no plaintext or STARTTLS option. |
| `username`, `password` | yes | Mailbox credentials; an app password is strongly recommended (see the README for Gmail and Outlook). |
| `folder` | no, default `INBOX` | |
| `senders` | no, default `zapplication.org`, `festivalnet.com` | Matched as a domain suffix of the message's From address. |
| `lookback_days` | no, default `14` | Only messages newer than this are read. |
| `parsers` | no, default all three | `zapp`, `festivalnet`, `generic`. |
| `mark_seen` | no, default off | The integration never deletes, moves, or copies mail; this is the only write it can ever make, and only when explicitly turned on. |

Connects read-only (IMAP `EXAMINE`, never `SELECT`), searches by date,
filters by sender, and runs each configured parser against the message
text until one matches. Both the `zapp` and `festivalnet` parser fixtures
are constructed from the vendors' own help-page descriptions of their
digest layout, not real mail (`docs/unverified.md`); every parser tolerates
a mismatched email by returning nothing rather than raising.
