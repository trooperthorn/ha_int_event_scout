"""Tests for sources/vendor_email.py: a fake IMAP client stands in for aioimaplib."""

from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any

import pytest

from custom_components.event_scout.sources.base import SourceContext, SourceValidationError
from custom_components.event_scout.sources.vendor_email import VendorEmailSource
from tests.conftest import load_fixture_text
from tests.fake_session import FakeSession


@dataclass
class FakeImapResponse:
    """A minimal stand-in for aioimaplib's Response."""

    result: str
    lines: list[Any] = field(default_factory=list)


class FakeImapClient:
    """A minimal stand-in for aioimaplib.IMAP4_SSL, injected via VendorEmailSource.client_factory."""

    def __init__(self, messages: dict[str, bytes], *, login_ok: bool = True, examine_ok: bool = True) -> None:
        """Store the fixture messages this fake mailbox will serve."""
        self.messages = messages
        self.login_ok = login_ok
        self.examine_ok = examine_ok
        self.store_calls: list[tuple[str, str, str]] = []
        self.logged_out = False
        self.examined_folder: str | None = None
        self.last_search: str | None = None

    async def wait_hello_from_server(self) -> None:
        """No-op like the real handshake."""

    async def login(self, username: str, password: str) -> FakeImapResponse:
        """Return OK unless configured to fail."""
        return FakeImapResponse("OK" if self.login_ok else "NO")

    async def examine(self, folder: str) -> FakeImapResponse:
        """Record the selected folder and return OK unless configured to fail."""
        self.examined_folder = folder
        return FakeImapResponse("OK" if self.examine_ok else "NO")

    async def search(self, criteria: str) -> FakeImapResponse:
        """Return every fixture message id, space-separated, like a real SEARCH response."""
        self.last_search = criteria
        ids = " ".join(self.messages.keys()).encode()
        return FakeImapResponse("OK", [ids])

    async def fetch(self, message_id: str, parts: str) -> FakeImapResponse:
        """Return the raw RFC822 bytes for one fixture message."""
        raw = self.messages.get(message_id)
        if raw is None:
            return FakeImapResponse("NO", [])
        return FakeImapResponse("OK", [b"1 FETCH (RFC822 {%d}" % len(raw), raw, b")"])

    async def store(self, message_id: str, flag_op: str, flags: str) -> FakeImapResponse:
        """Record a STORE call; the source must never call this unless mark_seen is set."""
        self.store_calls.append((message_id, flag_op, flags))
        return FakeImapResponse("OK", [])

    async def logout(self) -> FakeImapResponse:
        """Record logout."""
        self.logged_out = True
        return FakeImapResponse("OK", [])


def _make_message(*, from_addr: str, message_id: str, body: str, html: bool = False) -> bytes:
    message = EmailMessage()
    message["From"] = from_addr
    message["To"] = "me@example.com"
    message["Subject"] = "Deadline digest"
    message["Message-Id"] = message_id
    if html:
        message.add_header("Content-Type", "text/html", charset="utf-8")
        message.set_payload(body, charset="utf-8")
    else:
        message.set_content(body)
    return bytes(message)


def _source(**overrides) -> VendorEmailSource:  # noqa: ANN003
    data = dict(
        name="Vendor mail",
        server="imap.example.com",
        port=993,
        username="user@example.com",
        password="app-password",
        folder="INBOX",
        senders=["zapplication.org", "festivalnet.com"],
        lookback_days=14,
        parsers=["zapp", "festivalnet", "generic"],
        mark_seen=False,
        category="festival",
    )
    data.update(overrides)
    return VendorEmailSource(data)


def _ctx() -> SourceContext:
    return SourceContext(subentry_id="s1", name="Vendor mail", category="festival")


async def test_validate_selects_folder_read_only_and_never_writes() -> None:
    source = _source()
    client = FakeImapClient({})
    source.client_factory = lambda server, port: client

    await source.async_validate(FakeSession(), _ctx())

    assert client.examined_folder == "INBOX"
    assert client.store_calls == []
    assert client.logged_out is True


async def test_validate_raises_on_login_failure() -> None:
    source = _source()
    client = FakeImapClient({}, login_ok=False)
    source.client_factory = lambda server, port: client

    with pytest.raises(SourceValidationError):
        await source.async_validate(FakeSession(), _ctx())


async def test_sender_filtering_excludes_non_matching_domains() -> None:
    messages = {
        "1": _make_message(from_addr="digest@zapplication.org", message_id="<z1@zapplication.org>", body=load_fixture_text("zapp_digest.txt")),
        "2": _make_message(from_addr="newsletter@unrelated.example", message_id="<u1@unrelated.example>", body="Deadline: January 1, 2027"),
    }
    source = _source()
    client = FakeImapClient(messages)
    source.client_factory = lambda server, port: client

    events = await source.async_fetch(FakeSession(), _ctx())

    assert len(events) == 2  # both ZAPP events from message 1
    assert all(e.source_event_id.startswith("<z1@zapplication.org>") for e in events)


async def test_lookback_days_used_in_search_since_clause() -> None:
    source = _source(lookback_days=7)
    client = FakeImapClient({})
    source.client_factory = lambda server, port: client

    await source.async_fetch(FakeSession(), _ctx())

    assert client.last_search.startswith("SINCE ")


async def test_zapp_parser_via_full_fetch() -> None:
    messages = {"1": _make_message(from_addr="digest@zapplication.org", message_id="<z1>", body=load_fixture_text("zapp_digest.txt"))}
    source = _source(senders=["zapplication.org"])
    client = FakeImapClient(messages)
    source.client_factory = lambda server, port: client

    events = await source.async_fetch(FakeSession(), _ctx())
    assert len(events) == 2
    assert events[0].vendor.origin == "explicit"
    assert events[0].vendor.confidence == 0.8


async def test_zapp_html_parser_via_full_fetch() -> None:
    messages = {
        "1": _make_message(from_addr="digest@zapplication.org", message_id="<z1>", body=load_fixture_text("zapp_digest.html"), html=True)
    }
    source = _source(senders=["zapplication.org"])
    client = FakeImapClient(messages)
    source.client_factory = lambda server, port: client

    events = await source.async_fetch(FakeSession(), _ctx())
    assert len(events) == 2


async def test_festivalnet_parser_via_full_fetch() -> None:
    messages = {"1": _make_message(from_addr="news@festivalnet.com", message_id="<f1>", body=load_fixture_text("festivalnet_newsletter.txt"))}
    source = _source(senders=["festivalnet.com"])
    client = FakeImapClient(messages)
    source.client_factory = lambda server, port: client

    events = await source.async_fetch(FakeSession(), _ctx())
    assert len(events) == 2
    assert events[0].city == "Georgetown"


async def test_generic_parser_via_full_fetch() -> None:
    messages = {"1": _make_message(from_addr="team@cedarcreekmarket.example", message_id="<g1>", body=load_fixture_text("generic_email.txt"))}
    source = _source(senders=[], parsers=["generic"])
    client = FakeImapClient(messages)
    source.client_factory = lambda server, port: client

    events = await source.async_fetch(FakeSession(), _ctx())
    assert len(events) == 1
    assert events[0].vendor.confidence == 0.5


async def test_message_id_based_idempotence_across_two_refreshes() -> None:
    messages = {"1": _make_message(from_addr="digest@zapplication.org", message_id="<z1>", body=load_fixture_text("zapp_digest.txt"))}
    source = _source(senders=["zapplication.org"])
    client = FakeImapClient(messages)
    source.client_factory = lambda server, port: client

    events_first = await source.async_fetch(FakeSession(), _ctx())
    events_second = await source.async_fetch(FakeSession(), _ctx())

    assert {e.source_event_id for e in events_first} == {e.source_event_id for e in events_second}


async def test_mark_seen_off_never_issues_a_store_call() -> None:
    messages = {"1": _make_message(from_addr="digest@zapplication.org", message_id="<z1>", body=load_fixture_text("zapp_digest.txt"))}
    source = _source(senders=["zapplication.org"], mark_seen=False)
    client = FakeImapClient(messages)
    source.client_factory = lambda server, port: client

    await source.async_fetch(FakeSession(), _ctx())
    assert client.store_calls == []


async def test_mark_seen_on_issues_a_store_call_for_matched_messages() -> None:
    messages = {"1": _make_message(from_addr="digest@zapplication.org", message_id="<z1>", body=load_fixture_text("zapp_digest.txt"))}
    source = _source(senders=["zapplication.org"], mark_seen=True)
    client = FakeImapClient(messages)
    source.client_factory = lambda server, port: client

    await source.async_fetch(FakeSession(), _ctx())
    assert client.store_calls == [("1", "+FLAGS", "(\\Seen)")]


async def test_unparseable_message_is_skipped_without_raising() -> None:
    messages = {"1": _make_message(from_addr="digest@zapplication.org", message_id="<z1>", body="Nothing useful here.")}
    source = _source(senders=["zapplication.org"])
    client = FakeImapClient(messages)
    source.client_factory = lambda server, port: client

    events = await source.async_fetch(FakeSession(), _ctx())
    assert events == []


async def test_fake_client_never_exposes_copy_move_or_expunge() -> None:
    # FakeImapClient intentionally implements only the read-only surface
    # (login, examine, search, fetch, store, logout), so a source that tried
    # to copy, move, or expunge a message would fail with AttributeError
    # rather than silently succeeding against a fake that allowed it.
    client = FakeImapClient({})
    assert not hasattr(client, "copy")
    assert not hasattr(client, "move")
    assert not hasattr(client, "expunge")
