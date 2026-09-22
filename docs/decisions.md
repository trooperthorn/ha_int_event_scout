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
