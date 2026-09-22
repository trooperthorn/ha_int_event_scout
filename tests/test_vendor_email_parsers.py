"""Tests for sources/vendor_email_parsers.py against each vendor's fixture."""

from __future__ import annotations

from custom_components.event_scout.sources.vendor_email_parsers import (
    html_to_text,
    parse_festivalnet,
    parse_generic,
    parse_zapp,
)
from tests.conftest import load_fixture_text


def test_parse_zapp_text_fixture() -> None:
    body = load_fixture_text("zapp_digest.txt")
    events = parse_zapp(body, from_domain="zapplication.org", message_id="<z1>", ctx_name="ZAPP", category="festival")
    assert len(events) == 2
    assert events[0].title == "Austin Fine Arts Festival"
    assert events[0].vendor.app_deadline.isoformat() == "2026-11-15"
    assert events[0].vendor.jury_fee_text == "$35.00"
    assert events[1].vendor.jury_fee_text is None


def test_parse_zapp_html_fixture() -> None:
    body = html_to_text(load_fixture_text("zapp_digest.html"))
    events = parse_zapp(body, from_domain="zapplication.org", message_id="<z1>", ctx_name="ZAPP", category="festival")
    assert len(events) == 2


def test_parse_zapp_returns_empty_on_mismatch() -> None:
    assert parse_zapp("Nothing here.", from_domain="zapplication.org", message_id="<z9>", ctx_name="ZAPP", category="festival") == []


def test_parse_festivalnet_fixture() -> None:
    body = load_fixture_text("festivalnet_newsletter.txt")
    events = parse_festivalnet(body, from_domain="festivalnet.com", message_id="<f1>", ctx_name="FestivalNet", category="festival")
    assert len(events) == 2
    assert events[0].title == "Hill Country Arts Fair"
    assert events[0].state == "TX"


def test_parse_festivalnet_returns_empty_on_mismatch() -> None:
    result = parse_festivalnet("Nothing here.", from_domain="festivalnet.com", message_id="<f9>", ctx_name="FestivalNet", category="festival")
    assert result == []


def test_parse_generic_fixture() -> None:
    body = load_fixture_text("generic_email.txt")
    events = parse_generic(body, from_domain="cedarcreekmarket.example", message_id="<g1>", ctx_name="Generic", category="festival")
    assert len(events) == 1
    assert events[0].vendor.confidence == 0.5
    assert events[0].vendor.app_deadline.isoformat() == "2026-12-05"


def test_parse_generic_returns_empty_without_trigger_words() -> None:
    result = parse_generic(
        "Just a friendly newsletter with no dates.", from_domain="x.example", message_id="<g9>", ctx_name="Generic", category="festival"
    )
    assert result == []


def test_parse_generic_ignores_trigger_without_nearby_date() -> None:
    body = "Some Event\n" + ("filler " * 60) + "deadline " + ("filler " * 60)
    result = parse_generic(body, from_domain="x.example", message_id="<g10>", ctx_name="Generic", category="festival")
    assert result == []
