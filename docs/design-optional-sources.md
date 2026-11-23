# Optional sources: Meetup GraphQL and vendor email ingestion

Addendum to `docs/design.md` (2026-09-22). Both sources are optional source
subentries. Nothing in the hub depends on them, they can be added, changed
through the subentry Reconfigure step, or removed at any time, and their
absence changes nothing else.

## 1. `meetup` source

Requires a Meetup Pro subscription, because only Pro subscribers can create
an OAuth client (research section 6). The integration never asks for a
Meetup password. The user supplies the credentials of a JWT (server to
server) OAuth client, which is the flow that works unattended.

Subentry arguments:

| Key | Type | Notes |
| --- | --- | --- |
| `name` | string | Subentry title |
| `client_id` | string | Meetup OAuth client id (the JWT `iss` and `kid` values) |
| `member_id` | string | Meetup member id, the JWT `sub` |
| `private_key` | multi-line secret | RSA private key PEM registered with the OAuth client |
| `query` | string, optional | Keyword filter |
| `category` | select | Category label applied to every event from this source |
| `topic_category_ids` | list of strings, optional | Meetup topic category ids if the schema exposes them; leave empty when unknown |

Flow: sign a JWT (`RS256`, `aud` `api.meetup.com`, `exp` now plus 120 s)
with the private key, exchange it at `https://secure.meetup.com/oauth2/access`
with `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`, cache the
access token until 60 s before expiry, then POST GraphQL to
`https://api.meetup.com/gql-ext` (the endpoint named in the 2025 guide; if
the live endpoint differs the validate step reports the exact HTTP error).
The query uses `eventSearch` filtered by `lat`, `lon`, `radius` (hub values),
`startDateRange` now to now plus horizon, and `query`. Because the argument
signature was UNVERIFIED without a Pro token, the source first runs an
introspection query for `eventSearch` arguments during validate and stores
the discovered names in the subentry data; the fetch builds its query from
those names. If introspection shows no location arguments, validate fails
with a clear message rather than silently returning everything.

JWT signing uses `pyjwt` with the `cryptography` extra; both are already
core dependencies (verify the exact pins in `package_constraints.txt` and
declare ranges, never exact pins). Cost accounting: one introspection call
at validate, one search call per refresh page, within the documented 500
points per 60 seconds.

Mapped fields: `title`, `description`, `eventUrl`, `dateTime`, `endTime`,
`venue.name`, `venue.address`, `venue.city`, `venue.state`, `venue.lat`,
`venue.lng`, `group.name` as organizer, `isOnline` (online events are
dropped unless the user enables `include_online`). No vendor fields.

## 2. `vendor_email` source

Ingests the deadline digests that ZAPP and FestivalNet email to members, plus
any other sender the user names. This is the terms-clean path to those
paywalled directories: the user is a member, receives the mail, and the
integration reads only that mailbox.

Subentry arguments:

| Key | Type | Notes |
| --- | --- | --- |
| `name` | string | |
| `server`, `port` | string, int (default 993) | IMAP over TLS only; no STARTTLS or plaintext option |
| `username`, `password` | secrets | An app password is recommended; documented for Gmail and Outlook |
| `folder` | string, default `INBOX` | |
| `senders` | list of strings | Default `zapplication.org`, `festivalnet.com`; matched as domain suffix of the From address |
| `lookback_days` | int, default 14 | Only messages newer than this are read |
| `parsers` | multi-select | `zapp`, `festivalnet`, `generic` |
| `mark_seen` | bool, default false | The integration never deletes or moves mail |

Fetch: connect with `aioimaplib` (`aioimaplib>=2.0.1,<3`, the core pin), log
in, select the folder read-only, `SEARCH SINCE <date>`, fetch headers and
the text or HTML body of each candidate, filter by sender, then parse. HTML
bodies go through the same `html.parser` text extractor used by the vendor
probe. Each parser returns zero or more `ScoutEvent`s with `vendor` filled
from the email, `origin=explicit`, `confidence=0.8`, and
`source_event_id` equal to the message id plus an index so a re-read never
duplicates.

Parsers:

- `zapp`: the weekly Wednesday digest lists events with application
  deadlines; the parser looks for blocks of the form event name, city and
  state, deadline date, and a `zapplication.org/event-info.php?ID=` link.
  The fee is taken when present.
- `festivalnet`: the deadline reminder and Calls for Artists newsletter list
  event name, dates, city, and a deadline; links point at
  `festivalnet.com/event/`. Paywalled detail is not fetched.
- `generic`: any sender; finds a date within 200 characters of the words
  deadline, due, closes, or apply by, and the nearest preceding line as the
  event name; confidence 0.5.

Because no real ZAPP or FestivalNet email was available at build time, both
parser fixtures are constructed from the layout described on the vendors'
help pages and are listed in `docs/unverified.md`. The parser code must
tolerate mismatch: an email that yields nothing is logged once at debug
level and counted in `source_status`, never raised.

Events from this source usually name a festival that another source also
lists; the dedup step merges them and the email's explicit vendor block wins
over heuristics, which is the point of the source.

## 3. Reconfigure

The existing `SourceSubentryFlow.async_step_reconfigure` shows the same
schema as the add step with current values as defaults and re-runs validate
before saving. Secrets are shown as empty password fields; an empty
submission keeps the stored secret. Both new sources reuse that step with no
special cases. Changing the Meetup client or the mailbox takes effect on the
next refresh because the flow reloads the entry.

## 4. Diagnostics and security

Diagnostics redact `private_key`, `password`, and the cached access token.
The private key is stored in the config entry like every other secret in
Home Assistant custom integrations; the README states that plainly and
recommends a dedicated OAuth client and a dedicated app password so either
can be revoked without touching anything else. The IMAP source never writes
to the mailbox unless `mark_seen` is on.

## 5. Tests

Meetup: JWT assertion shape (decoded with the public half of a test key),
token caching and refresh, introspection-driven argument mapping, event
mapping from a fixture, validate failure when introspection lacks location
arguments. Vendor email: a fake IMAP client injected in place of
`aioimaplib`, sender filtering, lookback date, each parser against its
fixture, message id based idempotence across two refreshes, read-only
behavior (no store, copy, or expunge calls issued). Reconfigure: empty secret
keeps the stored value, changed server triggers validate.
