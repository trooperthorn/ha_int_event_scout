# Security Policy

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, private
addresses, or logs. Use GitHub's private vulnerability-reporting feature for
this repository. If private reporting is unavailable, open a minimal issue
asking the maintainer to establish a private channel; omit technical details.

Include the affected version/commit, prerequisites, impact, a minimal
reproduction, and suggested remediation. Remove API keys, tokens, and any
event or vendor data specific to your household.

## Response targets

These are project targets, not an SLA: acknowledge critical/high reports in
three business days, establish severity and containment in seven, and publish
a coordinated fix/advisory as soon as safely validated. Lower-severity issues
are prioritized by exploitability and impact.

## Supported version

Only the latest published release and the default branch receive security
fixes. Operators should update Home Assistant and Event Scout promptly and
keep a tested rollback.

## Security boundaries

Event Scout is a Home Assistant custom integration, not a sandbox. It
fetches from external URLs and APIs you configure (ICS feeds, JSON-LD pages,
Ticketmaster, Socrata, Eventbrite) and, when the vendor probe is enabled,
from a small set of candidate paths on an event's own host, honoring
robots.txt. It cannot verify that a configured feed or organizer is honest;
treat every fetched URL and every vendor deadline as untrusted content to be
reviewed before acting on it. Secrets (API keys, tokens, passwords) are
stored in the config entry's subentry data, which Home Assistant encrypts at
rest the same way it protects any other integration's credentials, and are
redacted from diagnostics exports.
