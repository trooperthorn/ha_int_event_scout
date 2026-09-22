"""Vendor email source: read-only IMAP ingestion of deadline digest emails.

Connects over TLS only, logs in, selects the configured folder read-only
(IMAP EXAMINE, never SELECT), searches by date and sender, and runs every
configured parser against each candidate message. See
docs/design-optional-sources.md section 2 and docs/decisions.md for why
IMAP, why read-only, and why the parsers tolerate mismatch.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email import message_from_bytes
from email.message import Message
from email.utils import parseaddr
from typing import Any

import aiohttp
from aioimaplib import IMAP4_SSL

from ..const import DEFAULT_VENDOR_EMAIL_PARSERS, LOGGER, SOURCE_KIND_VENDOR_EMAIL
from ..models import ScoutEvent
from .base import Source, SourceContext, SourceValidationError
from .vendor_email_parsers import PARSERS, html_to_text

ImapClientFactory = Callable[[str, int], Any]


def _default_client_factory(server: str, port: int) -> IMAP4_SSL:
    """Build the real aioimaplib client; tests inject a fake client factory instead."""
    return IMAP4_SSL(server, port)


def _extract_body(message: Message) -> str:
    """Return the best-effort plain text body of an email, converting HTML if needed."""
    if message.is_multipart():
        text_part: str | None = None
        html_part: str | None = None
        for part in message.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain" and text_part is None:
                text_part = _decode_payload(part)
            elif content_type == "text/html" and html_part is None:
                html_part = _decode_payload(part)
        if text_part:
            return text_part
        if html_part:
            return html_to_text(html_part)
        return ""

    content_type = message.get_content_type()
    payload = _decode_payload(message)
    if content_type == "text/html":
        return html_to_text(payload)
    return payload


def _decode_payload(part: Message) -> str:
    try:
        raw = part.get_payload(decode=True)
        if not isinstance(raw, bytes):
            return str(part.get_payload())
        charset = part.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")
    except (LookupError, ValueError):
        return str(part.get_payload())


class VendorEmailSource(Source):
    """IMAP-based vendor deadline digest source."""

    kind = SOURCE_KIND_VENDOR_EMAIL

    client_factory: ImapClientFactory = staticmethod(_default_client_factory)

    async def async_validate(self, session: aiohttp.ClientSession, ctx: SourceContext) -> None:
        """Log in and select the configured folder read-only, without fetching any events."""
        client = await self._async_connect()
        try:
            await self._async_examine_folder(client)
        finally:
            await self._async_logout(client)

    async def async_fetch(self, session: aiohttp.ClientSession, ctx: SourceContext) -> list[ScoutEvent]:
        """Fetch and parse deadline digest emails newer than lookback_days from configured senders."""
        client = await self._async_connect()
        try:
            await self._async_examine_folder(client)
            return await self._async_fetch_events(client, ctx)
        finally:
            await self._async_logout(client)

    async def _async_connect(self) -> Any:
        server = self.data["server"]
        port = int(self.data.get("port", 993))
        client = self.client_factory(server, port)
        await client.wait_hello_from_server()
        login_response = await client.login(self.data["username"], self.data["password"])
        if login_response.result != "OK":
            raise SourceValidationError("IMAP login failed")
        return client

    async def _async_examine_folder(self, client: Any) -> None:
        folder = self.data.get("folder", "INBOX")
        examine_response = await client.examine(folder)
        if examine_response.result != "OK":
            raise SourceValidationError(f"IMAP folder {folder} could not be selected")

    async def _async_logout(self, client: Any) -> None:
        try:
            await client.logout()
        except Exception:  # noqa: BLE001 - a logout failure must never mask the real fetch error
            LOGGER.debug("IMAP logout failed for the vendor_email source", exc_info=True)

    async def _async_fetch_events(self, client: Any, ctx: SourceContext) -> list[ScoutEvent]:
        lookback_days = int(self.data.get("lookback_days", 14))
        since = (datetime.now(tz=UTC) - timedelta(days=lookback_days)).strftime("%d-%b-%Y")
        search_response = await client.search(f"SINCE {since}")
        if search_response.result != "OK":
            raise SourceValidationError("IMAP SEARCH failed")

        message_ids = _parse_search_ids(search_response.lines)
        senders = [s.strip().lower() for s in self.data.get("senders", []) if s.strip()]
        parser_names = self.data.get("parsers") or DEFAULT_VENDOR_EMAIL_PARSERS
        mark_seen = bool(self.data.get("mark_seen", False))

        events: list[ScoutEvent] = []
        for message_id in message_ids:
            event_batch = await self._async_process_message(client, message_id, senders, parser_names, ctx, mark_seen=mark_seen)
            events.extend(event_batch)
        return events

    async def _async_process_message(
        self,
        client: Any,
        message_id: str,
        senders: list[str],
        parser_names: list[str],
        ctx: SourceContext,
        *,
        mark_seen: bool,
    ) -> list[ScoutEvent]:
        fetch_response = await client.fetch(message_id, "(RFC822)")
        if fetch_response.result != "OK":
            return []

        raw = _find_message_bytes(fetch_response.lines)
        if raw is None:
            return []
        message = message_from_bytes(raw)

        _, from_address = parseaddr(message.get("From", ""))
        from_domain = from_address.rsplit("@", 1)[-1].lower() if "@" in from_address else ""
        if senders and not any(from_domain == s or from_domain.endswith(f".{s}") for s in senders):
            return []

        body = _extract_body(message)
        message_id_header = message.get("Message-Id") or message_id

        events: list[ScoutEvent] = []
        for parser_name in parser_names:
            parser = PARSERS.get(parser_name)
            if parser is None:
                continue
            try:
                parsed = parser(body, from_domain=from_domain, message_id=message_id_header, ctx_name=ctx.name, category=ctx.category)
            except Exception:  # noqa: BLE001 - one malformed email must never break the whole fetch
                LOGGER.debug("Vendor email parser %s raised on message %s", parser_name, message_id_header, exc_info=True)
                continue
            if parsed:
                events.extend(parsed)
                break

        if not events:
            LOGGER.debug("No vendor_email parser matched message %s from %s", message_id_header, from_domain)

        if events and mark_seen:
            await client.store(message_id, "+FLAGS", "(\\Seen)")

        return events


def _parse_search_ids(lines: list[Any]) -> list[str]:
    if not lines:
        return []
    first = lines[0]
    if isinstance(first, bytes):
        first = first.decode()
    if not first:
        return []
    return [msg_id for msg_id in str(first).split() if msg_id]


def _find_message_bytes(lines: list[Any]) -> bytes | None:
    """Return the RFC822 payload line: the longest bytes entry in a FETCH response.

    aioimaplib represents a FETCH response as a list of lines that includes
    the literal marker line (for example b'1 FETCH (RFC822 {646}') and a
    closing b')', alongside the actual message bytes; the message itself is
    always the longest entry.
    """
    byte_lines = [line for line in lines if isinstance(line, bytes)]
    if not byte_lines:
        return None
    return max(byte_lines, key=len)
