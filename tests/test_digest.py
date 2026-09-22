"""Tests for digest.py."""

from __future__ import annotations

from datetime import date

from custom_components.event_scout.digest import (
    deadlines_for_period,
    digest_response,
    events_for_period,
    notification_payload_for_alert,
    render_markdown,
)
from custom_components.event_scout.models import DeadlineAlert, ScoutEvent, VendorInfo


def _event(**overrides) -> ScoutEvent:
    base = {
        "uid": "u1",
        "series_key": "s1",
        "source_kind": "ics",
        "source_name": "Test",
        "source_event_id": "1",
        "title": "Fall Festival",
        "start": date(2026, 9, 23),
        "category": "festival",
    }
    base.update(overrides)
    return ScoutEvent(**base)


def test_events_for_period_daily() -> None:
    events = [_event(start=date(2026, 9, 23)), _event(start=date(2026, 9, 30), source_event_id="2")]
    result = events_for_period(events, period="daily", categories=None, today=date(2026, 9, 23))
    assert len(result) == 1


def test_events_for_period_weekly_filters_category() -> None:
    events = [_event(category="festival"), _event(category="family", source_event_id="2")]
    result = events_for_period(events, period="weekly", categories=["family"], today=date(2026, 9, 23))
    assert len(result) == 1
    assert result[0].category == "family"


def test_deadlines_for_period() -> None:
    event = _event()
    alerts = [
        DeadlineAlert(event=event, alert_kind="deadline", when=date(2026, 9, 24), days=14),
        DeadlineAlert(event=event, alert_kind="deadline", when=date(2026, 10, 5), days=3),
    ]
    result = deadlines_for_period(alerts, period="weekly", today=date(2026, 9, 23))
    assert len(result) == 1


def test_render_markdown_contains_estimated_tag() -> None:
    event = _event(vendor=VendorInfo(app_deadline=date(2026, 10, 1), origin="heuristic", confidence=0.4))
    alert = DeadlineAlert(event=event, alert_kind="deadline", when=date(2026, 10, 1), days=14)
    markdown = render_markdown([event], [alert], period="daily")
    assert "estimated" in markdown


def test_digest_response_shape() -> None:
    event = _event()
    response = digest_response([event], [], period="daily")
    assert response["period"] == "daily"
    assert response["events"][0]["title"] == "Fall Festival"
    assert "markdown" in response


def test_notification_payload_includes_actions() -> None:
    vendor = VendorInfo(app_deadline=date(2026, 10, 1), app_url="https://example.com/apply", origin="explicit", confidence=0.9)
    event = _event(vendor=vendor)
    alert = DeadlineAlert(event=event, alert_kind="deadline", when=date(2026, 9, 23), days=14)
    payload = notification_payload_for_alert(alert, "tag123")
    assert payload["data"]["tag"] == "tag123"
    actions = payload["data"]["actions"]
    assert any(a["action"] == "URI" for a in actions)
    assert any(a["action"] == "EVENT_SCOUT_DISMISS" for a in actions)
    assert any(a["action"] == "EVENT_SCOUT_ADD_CAL" for a in actions)
