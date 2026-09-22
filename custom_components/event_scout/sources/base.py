"""Base class and shared context for Event Scout source plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import aiohttp

from ..models import ScoutEvent


@dataclass(frozen=True, kw_only=True)
class SourceContext:
    """Runtime context passed to every source's fetch and validate calls."""

    subentry_id: str
    name: str
    category: str
    latitude: float | None = None
    longitude: float | None = None
    radius_miles: float | None = None
    horizon_days: int = 90


class SourceValidationError(Exception):
    """Raised by validate() when the subentry's arguments do not work."""


class Source(ABC):
    """A single event source plugin."""

    kind: str

    def __init__(self, data: dict) -> None:
        """Store the subentry's own arguments."""
        self.data = data

    @abstractmethod
    async def async_fetch(self, session: aiohttp.ClientSession, ctx: SourceContext) -> list[ScoutEvent]:
        """Fetch and normalize events from this source."""

    async def async_validate(self, session: aiohttp.ClientSession, ctx: SourceContext) -> None:
        """Validate the subentry's arguments by fetching once.

        Raises SourceValidationError on failure. The default implementation
        calls async_fetch and lets any exception surface as a generic
        validation failure; sources with cheaper checks may override this.
        """
        try:
            await self.async_fetch(session, ctx)
        except SourceValidationError:
            raise
        except Exception as err:  # noqa: BLE001 - normalized into one error type for the flow
            raise SourceValidationError(str(err)) from err
