"""Data models for the Event Scout integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

VendorAvailable = Literal["yes", "no", "unknown"]
VendorOrigin = Literal["explicit", "heuristic", "manual"]
EventCategory = Literal["festival", "family", "city_anniversary", "community", "other"]


@dataclass(frozen=True, kw_only=True)
class VendorInfo:
    """Vendor application information attached to an event."""

    available: VendorAvailable = "unknown"
    app_open: date | None = None
    app_deadline: date | None = None
    notify_date: date | None = None
    app_url: str | None = None
    booth_fee_text: str | None = None
    jury_fee_text: str | None = None
    categories: tuple[str, ...] = ()
    juried: bool | None = None
    origin: VendorOrigin = "heuristic"
    confidence: float = 0.0

    def as_dict(self) -> dict:
        """Return a JSON-serializable representation."""
        return {
            "available": self.available,
            "app_open": self.app_open.isoformat() if self.app_open else None,
            "app_deadline": self.app_deadline.isoformat() if self.app_deadline else None,
            "notify_date": self.notify_date.isoformat() if self.notify_date else None,
            "app_url": self.app_url,
            "booth_fee_text": self.booth_fee_text,
            "jury_fee_text": self.jury_fee_text,
            "categories": list(self.categories),
            "juried": self.juried,
            "origin": self.origin,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> VendorInfo:
        """Build a VendorInfo from a stored dict."""

        def _date(value: str | None) -> date | None:
            return date.fromisoformat(value) if value else None

        return cls(
            available=data.get("available", "unknown"),
            app_open=_date(data.get("app_open")),
            app_deadline=_date(data.get("app_deadline")),
            notify_date=_date(data.get("notify_date")),
            app_url=data.get("app_url"),
            booth_fee_text=data.get("booth_fee_text"),
            jury_fee_text=data.get("jury_fee_text"),
            categories=tuple(data.get("categories", [])),
            juried=data.get("juried"),
            origin=data.get("origin", "manual"),
            confidence=data.get("confidence", 0.0),
        )

    @property
    def is_estimated(self) -> bool:
        """Return whether these vendor dates are an estimate."""
        return self.origin == "heuristic"


@dataclass(frozen=True, kw_only=True)
class ScoutEvent:
    """A single event pulled from one or more sources."""

    uid: str
    series_key: str
    source_kind: str
    source_name: str
    source_event_id: str
    title: str
    description: str | None = None
    url: str | None = None
    start: date | datetime
    end: date | datetime | None = None
    all_day: bool = True
    venue_name: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    distance_miles: float | None = None
    category: EventCategory = "other"
    is_free: bool | None = None
    cost_text: str | None = None
    organizer_name: str | None = None
    organizer_url: str | None = None
    vendor: VendorInfo | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    @property
    def start_date(self) -> date:
        """Return the start as a plain date."""
        return self.start if isinstance(self.start, date) and not isinstance(self.start, datetime) else self.start.date()

    def with_updates(self, **changes: Any) -> ScoutEvent:
        """Return a copy of this event with the given fields replaced."""
        from dataclasses import replace

        return replace(self, **changes)


@dataclass(frozen=True, kw_only=True)
class DeadlineAlert:
    """A single derived alert on the vendor deadlines calendar."""

    event: ScoutEvent
    alert_kind: str
    when: date
    days: int


@dataclass(kw_only=True)
class SourceStatus:
    """Status of one source subentry after the most recent refresh."""

    subentry_id: str
    name: str
    ok: bool = True
    error: str | None = None
    last_success: datetime | None = None
    event_count: int = 0


@dataclass(kw_only=True)
class ScoutData:
    """Data published by the coordinator on every refresh."""

    events: list[ScoutEvent] = field(default_factory=list)
    deadlines: list[DeadlineAlert] = field(default_factory=list)
    source_status: dict[str, SourceStatus] = field(default_factory=dict)
