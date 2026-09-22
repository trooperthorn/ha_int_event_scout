# Research: event sources, vendor application data, and Home Assistant prior art

Date of research: 2026-09-22. Target region: Central Texas (Austin); location is
configurable in the integration. Every claim below carries its source URL.
Items marked UNVERIFIED could not be confirmed from a primary source and must
be checked by hand before code depends on them.

## 1. Event data sources

### Ticketing and commercial aggregators

Eventbrite is unsuitable for discovery. Public access to `GET /v3/events/search/`
ended 2019-12-12 and whitelisted creator keys were cut off 2020-02-20. The
remaining endpoints require a known event, venue, or organization ID
(https://www.eventbrite.com/platform/docs/changelog,
https://github.com/Automattic/eventbrite-api/issues/83). It is useful only with
hard-coded organizer IDs (for example Austin Public Library,
https://www.eventbrite.com/o/austin-public-library-14779874945) polled through
`GET /v3/organizations/{id}/events/` with a personal OAuth token. No vendor
application fields.

Ticketmaster Discovery API v2 is the best free structured source. Base URL
`https://app.ticketmaster.com/discovery/v2/events.json?apikey=...`. Free key,
5,000 calls per day, 5 requests per second
(https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/,
https://developer.ticketmaster.com/products-and-docs/apis/getting-started/).
Geographic filtering through `latlong` plus `radius`, `city`, `stateCode`,
`dmaId`, or `geoPoint` (geohash). The classification tree is Segment, Genre,
Sub-genre; segments include Music, Sports, Arts & Theatre, Family, Film, and
Miscellaneous, and classifications carry a `family` boolean
(https://developer.ticketmaster.com/products-and-docs/tutorials/events-search/search_events_with_discovery_api.html).
Weakness: only ticketed events sold through Ticketmaster, so it misses most
free small-town festivals, which are the vendor target. Terms require
attribution and branding compliance. No vendor application data.

PredictHQ is commercially the best fit but paid. Categories include
`festivals`, `community`, `performing-arts`, `school-holidays`; radius, place,
and IATA search; per-event rank (https://www.predicthq.com/apis,
https://www.predicthq.com/events/local-events). Pricing is enterprise quote
only (https://www.predicthq.com/pricing). UNVERIFIED whether any free tier
exists. Redistribution is contractually restricted. Not viable for an MVP.

SeatGeek has a Platform API (`api.seatgeek.com/2/events`, docs at
https://seatgeek.github.io/) but access is gated behind the partner program
and Platform Terms (https://seatgeek.com/api-terms,
https://support.seatgeek.com/hc/en-us/articles/4409765051283). UNVERIFIED
whether self-serve keys still issue in 2026. Same coverage gap as
Ticketmaster.

Meetup is GraphQL only since February 2025 and OAuth consumer creation
requires an active Meetup Pro subscription with discretionary approval
(https://help.meetup.com/hc/en-us/articles/41453576628749,
https://www.meetup.com/graphql/). Not viable.

Bandsintown REST v3 (`https://rest.bandsintown.com`, `X-API-Key` header)
binds each key to a single artist
(https://help.artists.bandsintown.com/en/articles/7053475). No geographic
discovery. Not viable.

AllEvents.in has a commercial API covering about 40,000 cities with city,
category, and organizer queries (https://allevents.developer.azure-api.net/,
https://allevents.in/pages/events-api). Pricing is sales-gated, UNVERIFIED,
no published free tier. Redistribution terms unknown.

Evensi and Stay22: UNVERIFIED. No current public developer documentation for
an Evensi events API was found. Stay22 is an affiliate layer, not an events
feed. Treat as unavailable.

Yelp Fusion Events (`GET /v3/events`, `/v3/events/featured`) historically
existed (https://www.yelp.com/developers/documentation/v3/event_categories_list)
but Yelp has been deprecating and monetizing endpoints
(https://docs.developer.yelp.com/changelog,
https://techcrunch.com/2024/08/02/yelps-lack-of-transparency-around-api-charges-angers-developers/).
UNVERIFIED that the Events endpoint is still live or free in 2026. Do not
build on it.

Facebook and Meta Events are effectively unavailable. Public event search was
removed, `/events/attending` returns empty, and the Events API permission is
no longer granted
(https://developers.facebook.com/docs/graph-api/reference/event/,
https://github.com/tobilg/facebook-events-by-location-core, deprecated). A
large share of small-town Texas festivals exist only as Facebook events, which
is a real coverage ceiling.

Eventful is dead; https://api.eventful.com/docs/formats is a historical
artifact.

### Local, civic, and Texas-specific

Do512 (DoStuff Media) is Austin's dominant local calendar, with
http://family.do512.com/ for kids' events. There is an undocumented
`events.json` endpoint; third parties report the `category` parameter is
accepted but ignored and there is no text search
(https://apify.com/hoholabs/dostuffmedia-scraper). No public developer terms,
so redistribution risk. Best effort only.

City of Austin Open Data (Socrata), https://data.austintexas.gov/. The ACCD
Event Listings dataset `p9ma-z6y9` covers Austin Convention Center and Palmer
Events Center shows with dates, attendance, contacts, and websites. SODA
endpoint `https://data.austintexas.gov/resource/p9ma-z6y9.json` with `$where`
and `$limit`; no auth needed at low volume, app token recommended. Open-data
licensed, so redistribution-safe. Narrow scope, high quality, and its contact
and website fields can seed vendor lookups.

Texas Highways and TravelTexas is the best statewide festival index. One
editorial pipeline feeds texashighways.com, the quarterly print Events
Calendar, and traveltexas.com
(https://texashighways.com/events/submit-event/,
https://texashighways.com/events/submit-event/event-submission-guidelines/,
https://www.traveltexas.com/plan-ahead/events/). Its own publication
deadlines run about three months ahead (Spring issue deadline December 1,
Winter issue deadline September 1), a useful proxy that a festival is real
and planning is underway. No documented API; HTML and JSON-LD only.
UNVERIFIED whether any feed exists.

Texas Festivals & Events Association (TFEA) publishes a member event calendar
(https://www.tfea.org/p/get-involved/203,
https://www.tfea.org/events/filters/iso=1) and a Visit Widget instance
(https://tfea.visitwidget.com/). Visit Widget aggregates through
OccasionGenius (https://visitwidget.com/automatic-event-sourcing-made-easy/).
UNVERIFIED whether the Visit Widget instance exposes a JSON endpoint; check
the browser network tab by hand. TFEA membership is the closest thing to a
canonical list of Texas festival organizers, the people who publish vendor
calls.

Libraries fall into three platform families, all with feeds:

- Springshare LibCal: REST API v1.1 with OAuth2 client credentials, for
  example Austin Community College at
  https://austincc.libcal.com/calendar/LSEvents; per-institution keys
  (https://github.com/BGSU-LITS/libcal).
- BiblioCommons BiblioEvents: Events API needs a customer key, but
  BiblioEvents exports XML/RSS, CSV, Excel, and dynamic event feeds without
  staff work (https://www.bibliocommons.com/solutions/biblioevents,
  https://github.com/remocrevo/biblio-calendar).
- Communico: UNVERIFIED for Austin. Austin Public Library's calendar is at
  https://library.austintexas.gov/events/calendar; the platform and any ICS
  export could not be confirmed. Inspect the page for `webcal:` or `.ics`
  links before committing.

Parks and recreation and school districts (ActiveNet, RecTrac, CivicPlus,
CivicRec, Finalsite, Blackboard, Apptegy) expose per-calendar `.ics` and RSS.
This is generically solvable with an ICS fetcher. UNVERIFIED for specific
Austin and Round Rock URLs; enumerate at configuration time, not in code.

Family-event networks: Macaroni KID uses per-city subdomains with free and
low-cost family events and no documented API or RSS
(https://national.macaronikid.com/events). Mommy Poppins is major-metro
centric with no API (https://mommypoppins.com/). Red Tricycle was acquired by
Tinybeans in 2020 and its calendar persists there
(https://theygotacquired.com/content/red-tricycle-acquired-by-tinybeans/,
https://tinybeans.com/event-calendar-faq/). Hulafrog and Kidlist: UNVERIFIED,
no API found. All are scrape-or-nothing.

Generic schema.org Event JSON-LD is the highest-leverage generic extractor.
Most WordPress festival sites (The Events Calendar plugin), Squarespace, and
civic CMSes emit `<script type="application/ld+json">` with `@type: Event`,
`startDate`, `location`, `offers`, and `url`. On legality, hiQ v. LinkedIn,
Van Buren, and Meta v. Bright Data (2024-01-23) support that scraping public,
unauthenticated pages is not a CFAA violation, while contract, trespass, and
copyright claims remain live
(https://www.ropesgray.com/en/insights/alerts/2026/05/web-scraping-in-the-age-of-ai-guidance-for-data-owners-and-scrapers,
https://en.wikipedia.org/wiki/HiQ_Labs_v._LinkedIn). For a single-household
integration fetching a handful of pages daily the risk is low; honor
robots.txt, send a real User-Agent, cache aggressively, never redistribute.

## 2. Vendor application data

ZAPP (zapplication.org, run by WESTAF) is the canonical source for juried
fine-art and craft fairs. Each event page carries a structured Event Timeline:
application open date, early-bird and late-fee deadlines, application
deadline, notification date, accept-invitation and purchase deadline, and
event start (https://artist-help.zapplication.org/doc/event-information-page).
No public API (UNVERIFIED that any exists). ZAPP emails a weekly Wednesday
digest of upcoming deadlines and newly opened events to artists on the Show
Information list (https://artisthelp.zapplication.org/managing-applications/).
That email is a terms-clean ingestion path (IMAP then parse).

Eventeny has a public directory of open applications at
https://www.eventeny.com/events/applications/ with location, month, and
price-range filters ($0-10, 10-25, 25-50, 50-100, $100+), so application fee
is a first-class facet. Detail pages carry booth fees and deadlines. No
official API; third-party scrapers exist
(https://apify.com/hypebridge/eventeny-vendor-market-directory/api).
Eventeny is increasingly where small-town Texas festivals put vendor
applications, so it is arguably more relevant than ZAPP for this user.

FestivalNet lists 20,000+ events with a public deadlines page
(https://festivalnet.com/deadlines) and Calls for Artists
(https://festivalnet.com/calls-for-artists), but full details, promoter
contacts, and deadlines are paywalled behind annual membership
(https://festivalnet.com/faq?category_id=1). Members get a bi-monthly deadline
reminder email and a weekly Calls for Artists newsletter. No API.

Submittable has a real REST API (v3 and v4, OAuth plus webhooks,
https://submittable-api.submittable.com/docs/v4/index.html,
https://submittable.help/en/articles/5504544) but it is organization scoped:
it exposes your submissions and your organization's opportunities, not a
global marketplace. Useful for tracking filed applications, not discovery.
Its Discover Opportunities page
(https://manager.submittable.com/opportunities/discover) is browse only.

Sunshine Artist (https://sunshineartist.com/events/calendar) and
ArtFairCalendar (https://artfaircalendar.com/call-for-entries) are editorial
listings with deadlines. Sunshine Artist gates the full audit data behind a
subscription. No APIs. ArtFairCalendar's Call for Entries page is a small,
structured, scrapeable deadline list.

The long tail: most small festivals use JotForm, Google Forms, or a PDF on
their own site linked from a `/vendors` or `/vendor-application` page. There
is no feed. The practical approach is to maintain the festival list from
event sources, then probe each festival's domain for `/vendor*`,
`/exhibitor*`, `/apply*`, `/become-a-vendor` and extract dates and PDF links.

Typical lead times (directional; partially UNVERIFIED as aggregate
statistics):

- Large juried art fairs on ZAPP: applications open 8 to 12 months before the
  event, close 5 to 8 months before, jury notification 1 to 2 months after
  close. Jury fees $25 to $50, booth fees $300 to $900 and up.
- Small-town and community festivals on Eventeny or a JotForm: open 3 to 5
  months out, close 30 to 90 days before, often "until full". Booth fees $50
  to $250, usually no jury fee; food vendors pay more and need a health permit
  with its own earlier deadline.
- Texas Highways print listing deadline about three months before the season
  is a good floor for "this event is already planned".

Fields that matter: application open date, application deadline (plus
early-bird and late deadlines), jury or application fee, booth fee, booth
size and electricity add-ons, notification date, accepted categories (fine
art, craft, commercial, food, nonprofit, kids activity), certificate of
insurance requirement, sales-tax permit requirement, load-in time,
application URL, and juried versus first-come.

## 3. City birthdays

There is no structured API for city founding or incorporation anniversaries.
Wikidata has an `inception` (P571) property on most city items, queryable
through SPARQL; coverage and precision for small Texas towns is inconsistent
(UNVERIFIED per city). Austin was incorporated 1839-12-27
(https://en.wikipedia.org/wiki/Timeline_of_Austin,_Texas). The celebration is
almost never on the founding date: Fiesta San Antonio is an eleven-day April
event (https://en.wikipedia.org/wiki/Fiesta_San_Antonio); Austin-area city
birthday events are parks-department programming announced one to three
months ahead.

Recommendation: treat city birthdays as a user-maintained list of recurring
dates (name, city, month and day or nth-weekday rule, optional vendor
application lead time), optionally seeded from Wikidata at setup. Do not build
a scraper for this.

## 4. Home Assistant prior art (2026.9 baseline)

Core platform. `CalendarEntity` exposes `event` (current or next
`CalendarEvent`), state on or off like a binary sensor, and requires
`async_get_events(hass, start_date, end_date)`; the start bound applies to
the event end (exclusive) and the end bound to the event start (exclusive),
and recurrences must be flattened by the integration. WebSocket
`calendar/event/subscribe` is handled by the base class; call
`async_update_event_listeners()` after out-of-band mutations. Optional
CREATE_EVENT, UPDATE_EVENT, DELETE_EVENT features map to
`async_create_event`, `async_update_event`, `async_delete_event`
(https://developers.home-assistant.io/docs/core/entity/calendar). The
`calendar.get_events` action and calendar triggers (event start and end with
offset) come free once the entity exists.

Core integrations to reuse rather than reinvent: `local_calendar` (writable
local ICS store), `remote_calendar` (added 2025.4, fetches a public `.ics`
over http or https with optional basic auth; `webcal://` must be rewritten by
hand and some SaaS feeds fail, with 2025.12 reports of entities going
unavailable, https://www.home-assistant.io/integrations/remote_calendar/,
https://github.com/home-assistant/core/issues/159051), `caldav`, `google`,
`holiday`, `workday`, plus `rest`, `scrape`, `feedparser` (HACS), and
`multiscrape` (HACS) as generic fetchers.

HACS prior art:

- https://github.com/jamesstocktonj1/ticketmaster-events: Discovery API to a
  calendar entity plus a count sensor with next-event attributes. Closest
  existing thing to the MVP.
- https://github.com/Thrasher2020/home-assistant-gigfinder: merges
  Ticketmaster, Fatsoma, and Skiddle into one calendar with source tags. A
  direct multi-source precedent.
- https://github.com/tybritten/ical-sensor-homeassistant: N next-event sensors
  plus a calendar from an ICS URL.
- https://github.com/mampfes/hacs_waste_collection_schedule: the architecture
  to copy. A `sources/` package of per-provider modules behind one normalized
  type, config-flow-driven source selection with typed per-source arguments,
  and increasingly declarative source definitions with response validation.
- No `ha-eventbrite` of any maturity found, consistent with the API being
  dead.

Notifications. Companion app actionable notifications use `data.actions[]`
with `action` and `title`; `action: "URI"` plus `uri:` opens a URL, a
dashboard view, `entityId:<id>`, `app://<pkg>`, or `deep-link://`. Any other
action fires the `mobile_app_notification_action` event carrying the action
key and any `action_data`
(https://companion.home-assistant.io/docs/notifications/actionable-notifications/).
This maps to three buttons: Open application (URI with the vendor URL, no
round trip), Add to calendar (custom action, automation calls
`calendar.create_event` on a `local_calendar`), Dismiss (custom action that
clears a marker). Use `data.tag` for replace and dismiss semantics and
`data.channel` plus `importance: high` on Android for deadline alerts.

## 5. Recommended architecture inputs

(a) MVP sources, all free and defensible:

1. Ticketmaster Discovery v2, the only real free keyed API with geography and
   Family and festival classification.
2. A generic ICS or webcal fetcher covering libraries, parks and recreation,
   school districts, city calendars, and Google public calendars. One code
   path, unlimited user-supplied URLs. Carries most kids and family volume.
3. A generic schema.org Event JSON-LD extractor for user-supplied festival
   and aggregator page URLs (Texas Highways, TFEA, individual festival sites).
4. Socrata SODA open data, with Austin `p9ma-z6y9` as the reference.

Plus a user-maintained list for city birthdays and known recurring
festivals. Defer PredictHQ, AllEvents, Meetup, SeatGeek, Yelp, Eventbrite,
Facebook. For vendor data the MVP should use JSON-LD and heuristic extraction
from each event's own vendors page, plus optional IMAP ingestion of the ZAPP
weekly deadline and FestivalNet Calls for Artists emails. Do not scrape ZAPP
or FestivalNet directly; both are paywalled and terms-protected.

(b) Source-plugin design: copy waste_collection_schedule. Each source exposes
a title, description, URL, test cases, and a fetch returning normalized
events. The config flow lists sources, then renders typed arguments per
source. Two or three generic sources cover most real use; named convenience
sources are thin wrappers. Per-source unit tests with recorded fixtures keep
a scraper fleet alive.

(c) Normalized schema: uid, source_id, source_event_id, title, description,
url, start, end, all_day, timezone, venue_name, address, city, state, lat,
lon, distance_mi, categories, is_family, is_festival, free, cost,
organizer_name, organizer_email, organizer_url, and a vendor block:
vendor_available (true, false, unknown), vendor_app_open,
vendor_app_deadline, vendor_app_url, vendor_booth_fee, vendor_jury_fee,
vendor_notify_date, vendor_categories, vendor_juried,
vendor_insurance_required, vendor_source (explicit, heuristic, manual),
vendor_confidence (0 to 1), last_seen, first_seen, raw.

Expose one calendar per configured source plus an aggregate, and a second
Vendor Deadlines calendar whose events are the deadlines rather than the
festivals; calendar triggers with negative offsets then do the notification
work for free. Sensors: upcoming events in 90 days, vendor applications open
now, next vendor deadline with a list attribute.

(d) Deduplication: blocking key of date bucket plus or minus one day and a
roughly three-mile geo cell, then score on normalized title (lowercase, strip
"annual", ordinals, "festival", ampersands, token-set ratio), venue token
overlap, and URL host equality. Merge above about 0.85. Keep a stable uid per
merged cluster in a store so calendar UIDs do not churn, and record source
precedence (official site, then open data, then Ticketmaster, then scraped
aggregator) for field-level conflict resolution. Carry an annual series key
(slug plus city) so the 2027 edition links to the 2026 one.

(e) Deriving deadlines when absent: if the same festival was seen last year
with a known deadline offset, reuse it (highest confidence). Else use class
priors: juried art fair deadline at event minus 180 days and open at minus
300; community festival deadline at minus 60 and open at minus 150; food
vendor deadline at minus 45. Mark the vendor source heuristic with confidence
0.4 and phrase the notification as "check now, likely closes around X"
rather than asserting a date. Fire a reconnaissance notification at event
minus 240 days for any festival with unknown vendor availability, prompting
the user to open the site once and store a manual override. Manual overrides
win permanently and survive re-scrapes. Notify at deadline minus 30, 14, and
3 days, deduplicated by tag.

(f) Risks: ZAPP, FestivalNet, and Sunshine Artist are subscription products
and scraping them is a contract risk; use email ingestion or manual entry.
JSON-LD is the stable scraping surface, CSS selectors are not; expect a
source to go dark every few months, make source failures non-fatal, and
surface a repair issue rather than failing the config entry. Ticketmaster
limits are ample for a daily 90-day sweep (5 to 20 calls); cache ICS with
ETag and If-Modified-Since; never poll faster than once per six hours.
Facebook-only festivals are unreachable, so provide a first-class manual
event path. The integration ships code, not data; bundle only test fixtures.

## 6. Follow-up: Nextdoor, Meetup, Facebook, Eventbrite (2026-09-22, second pass)

Method note: the Eventbrite pages `/platform/new/api` and `/platform/api`
returned HTTP 401 to an unauthenticated fetch and the changelog rendered as an
empty JavaScript shell, so the Eventbrite findings lean on secondary sources.

Nextdoor developer platform. Three product families: Advertising, Sharing,
and Content Display (https://developer.nextdoor.com/reference/introduction).
The Search API overview lists Posts (live), Marketplace (live), Business
Pages (coming soon), and Events, "coming soon"
(https://developer.nextdoor.com/docs/overview-copy-1). The live sibling
endpoint `GET https://nextdoor.com/content_api/v2/search_post` takes `lat`,
`lon`, `radius` in miles, and `query`, and only returns posts from the last
seven days (https://developer.nextdoor.com/reference/search-posts). Every API
except Share Plugin requires an individually reviewed access application;
research-focused applications are refused for Ads
(https://developer.nextdoor.com/reference/applying-for-access). Named
production users are corporate partners
(https://www.businesswire.com/news/home/20220517005433/en/Nextdoor-announces-first-API-partnership-with-Microsoft-to-deliver-hyperlocal-neighborhood-content-to-users).
Rate limits UNVERIFIED. No RSS or ICS feed for neighborhood events was found
(UNVERIFIED that none exists). Verdict: NOT VIABLE today; recheck in six
months. If it ships, a plugin needs a token, lat, lon, radius, and query.

Meetup GraphQL. The API is alive. Access is included with Meetup Pro and only
Pro subscribers can create OAuth consumers (https://www.meetup.com/graphql/,
https://help.meetup.com/hc/en-us/articles/41453576628749-How-can-I-get-access-to-Meetup-s-API,
wording UNVERIFIED because the page returned 403). Pro price UNVERIFIED. Four
OAuth2 flows including JWT server-to-server, which suits an unattended
integration (https://www.meetup.com/api/authentication/). The February 2025
update split `keywordSearch` into `groupSearch` and `eventSearch` and added
introspection (https://www.meetup.com/graphql/guide/). Whether `eventSearch`
takes lat, lon, and radius is UNVERIFIED without a Pro token. Rate limit is
500 points per 60 seconds (same guide). Caching and redistribution terms are
UNVERIFIED; read the terms before shipping. Verdict: VIABLE WITH CAVEATS,
blocked only by the paid subscription; coverage for festivals and city
anniversaries is expected to be thin. Plugin config: client id, secret or
JWT key, member id, lat, lon, radius, category filter.

Meta Official Events API. A publish-side product for partner ticketing
platforms to push events onto Facebook, partner-gated, and its page still
carries a COVID-era onboarding pause notice
(https://developers.facebook.com/products/official-events-api/). Verdict:
NOT VIABLE.

Facebook Graph API v26.0. The Page node reference lists no `events` edge
(https://developers.facebook.com/docs/graph-api/reference/page/) and the
events edge reference URL returns 404. Page Public Content Access grants
Pages Search and public post reads after App Review plus Business
Verification and says nothing about events
(https://developers.facebook.com/docs/features-reference/page-public-content-access).
The `pages_read_engagement` reference returned HTTP 500 (UNVERIFIED wording)
and is own-Page only in any case. Verdict: NOT VIABLE; there is no compliant
path for an individual to read a set of public Pages' events on a schedule.

Eventbrite. What `/platform/new/api` is remains UNVERIFIED (401). No 2026
announcement of a restored discovery endpoint was found; the one confirmed
2026 corporate event is the Bending Spoons acquisition closed 2026-03-10
(https://en.wikipedia.org/wiki/Eventbrite). Discovery search ended
2020-02-20 (https://github.com/Automattic/eventbrite-api/issues/83).
Endpoints that work with a personal OAuth token: `/v3/users/me/`,
`/v3/users/me/organizations/`, `/v3/organizations/{id}/events/?status=live`,
`/v3/events/{id}/`, `/v3/venues/{id}/events/`. Tokens come from the account
API key page
(https://www.eventbrite.com/help/en-us/articles/849962/generate-an-api-key/).
Rate limit 1,000 calls per hour per token in the terms
(https://www.eventbrite.com/help/en-us/articles/833731/eventbrite-api-terms-of-use/);
secondary sources cite 2,000 per hour, UNVERIFIED. Organizer IDs cannot be
enumerated by city; they are read from public organizer profile URLs by hand.
Verdict: VIABLE WITH CAVEATS as a curated-organizer source: token, list of
organization ids, optional venue ids.
