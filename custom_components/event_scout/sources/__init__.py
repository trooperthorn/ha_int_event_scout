"""Registry of Event Scout source plugins."""

from __future__ import annotations

from ..const import (
    SOURCE_KIND_EVENTBRITE,
    SOURCE_KIND_ICS,
    SOURCE_KIND_JSONLD,
    SOURCE_KIND_MANUAL,
    SOURCE_KIND_MEETUP,
    SOURCE_KIND_SOCRATA,
    SOURCE_KIND_TICKETMASTER,
    SOURCE_KIND_VENDOR_EMAIL,
)
from .base import Source, SourceContext, SourceValidationError
from .eventbrite import EventbriteSource
from .ics import IcsSource
from .jsonld import JsonLdSource
from .manual import ManualSource
from .meetup import MeetupSource
from .socrata import SocrataSource
from .ticketmaster import TicketmasterSource
from .vendor_email import VendorEmailSource

SOURCES: dict[str, type[Source]] = {
    SOURCE_KIND_ICS: IcsSource,
    SOURCE_KIND_JSONLD: JsonLdSource,
    SOURCE_KIND_TICKETMASTER: TicketmasterSource,
    SOURCE_KIND_SOCRATA: SocrataSource,
    SOURCE_KIND_MANUAL: ManualSource,
    SOURCE_KIND_EVENTBRITE: EventbriteSource,
    SOURCE_KIND_MEETUP: MeetupSource,
    SOURCE_KIND_VENDOR_EMAIL: VendorEmailSource,
}


def get_source(kind: str, data: dict) -> Source:
    """Instantiate the source class registered for a given kind."""
    source_cls = SOURCES[kind]
    return source_cls(data)


__all__ = ["SOURCES", "Source", "SourceContext", "SourceValidationError", "get_source"]
