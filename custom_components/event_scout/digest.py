"""Digest building and notification payload construction."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .const import DIGEST_PERIOD_DAILY, EVENT_SCOUT_ADD_CAL, EVENT_SCOUT_DISMISS
from .models import DeadlineAlert, ScoutEvent


def events_for_period(events: list[ScoutEvent], *, period: str, categories: list[str] | None, today: date | None = None) -> list[ScoutEvent]:
    """Return events falling within a digest period, optionally filtered by category."""
    today = today or date.today()
    end = today + timedelta(days=1 if period == DIGEST_PERIOD_DAILY else 7)
    selected = [e for e in events if today <= e.start_date < end]
    if categories:
        selected = [e for e in selected if e.category in categories]
    return sorted(selected, key=lambda e: (e.start_date, e.title))


def deadlines_for_period(deadlines: list[DeadlineAlert], *, period: str, today: date | None = None) -> list[DeadlineAlert]:
    """Return deadline alerts falling within a digest period."""
    today = today or date.today()
    end = today + timedelta(days=1 if period == DIGEST_PERIOD_DAILY else 7)
    selected = [d for d in deadlines if today <= d.when < end]
    return sorted(selected, key=lambda d: d.when)


def render_markdown(events: list[ScoutEvent], deadlines: list[DeadlineAlert], *, period: str, group_by_county: bool = False) -> str:
    """Render a digest as markdown.

    When `group_by_county` is set (the hub has counties configured), events
    are grouped under a heading per county, with events that have no
    resolved county listed last under "Unknown county".
    """
    title = "Daily digest" if period == DIGEST_PERIOD_DAILY else "Weekly digest"
    lines = [f"# {title}", ""]

    lines.append("## Events")
    if not events:
        lines.append("- No events in this period.")
    elif group_by_county:
        groups: dict[str, list[ScoutEvent]] = {}
        for event in events:
            groups.setdefault(event.county or "Unknown county", []).append(event)
        for county in sorted(groups, key=lambda c: (c == "Unknown county", c)):
            lines.append(f"### {county}")
            for event in groups[county]:
                lines.append(f"- {event.start_date.isoformat()}: {event.title} ({event.category})")
    else:
        for event in events:
            lines.append(f"- {event.start_date.isoformat()}: {event.title} ({event.category})")

    lines.append("")
    lines.append("## Vendor deadlines")
    if deadlines:
        for alert in deadlines:
            estimated = " (estimated)" if alert.event.vendor and alert.event.vendor.is_estimated else ""
            lines.append(f"- {alert.when.isoformat()}: {alert.event.title} ({alert.alert_kind}{estimated})")
    else:
        lines.append("- No vendor deadlines in this period.")

    return "\n".join(lines)


def digest_response(events: list[ScoutEvent], deadlines: list[DeadlineAlert], *, period: str, group_by_county: bool = False) -> dict[str, Any]:
    """Build the structured response for event_scout.get_digest."""
    return {
        "period": period,
        "events": [
            {
                "uid": e.uid,
                "title": e.title,
                "start": e.start_date.isoformat(),
                "category": e.category,
                "url": e.url,
                "county": e.county,
            }
            for e in events
        ],
        "deadlines": [
            {
                "uid": alert.event.uid,
                "title": alert.event.title,
                "when": alert.when.isoformat(),
                "alert_kind": alert.alert_kind,
                "estimated": bool(alert.event.vendor and alert.event.vendor.is_estimated),
            }
            for alert in deadlines
        ],
        "markdown": render_markdown(events, deadlines, period=period, group_by_county=group_by_county),
    }


def notification_payload_for_alert(alert: DeadlineAlert, tag: str) -> dict[str, Any]:
    """Build a Companion app notification payload for one deadline alert."""
    vendor = alert.event.vendor
    estimated = " (estimated)" if vendor and vendor.is_estimated else ""
    deadline_text = vendor.app_deadline.isoformat() if vendor and vendor.app_deadline else "unknown"
    fee_text = f" Booth fee {vendor.booth_fee_text}." if vendor and vendor.booth_fee_text else ""

    actions = []
    if vendor and vendor.app_url:
        actions.append({"action": "URI", "title": "Open application", "uri": vendor.app_url})
    actions.append({"action": EVENT_SCOUT_ADD_CAL, "title": "Add to calendar"})
    actions.append({"action": EVENT_SCOUT_DISMISS, "title": "Dismiss"})

    return {
        "title": f"Vendor {alert.alert_kind} in {alert.days} days: {alert.event.title}",
        "message": f"Deadline {deadline_text}{estimated}.{fee_text} Tap to open.",
        "data": {
            "tag": tag,
            "channel": "Event Scout",
            "importance": "high",
            "url": vendor.app_url if vendor else None,
            "actions": actions,
            "action_data": {"uid": alert.event.uid, "tag": tag},
        },
    }
