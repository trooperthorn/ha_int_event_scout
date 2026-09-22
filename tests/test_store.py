"""Tests for store.py."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.event_scout.models import VendorInfo
from custom_components.event_scout.store import EventScoutStore


@pytest.mark.asyncio
async def test_store_round_trips_aliases_and_overrides(hass) -> None:  # noqa: ANN001
    store = EventScoutStore(hass, "entry1")
    await store.async_load()
    store.record_alias("ics:a:1", "uid-1")
    vendor = VendorInfo(app_deadline=date(2026, 10, 1), origin="manual", confidence=1.0)
    store.set_override("uid-1", vendor)
    store.set_series_offset("series-1", deadline_offset_days=-60, open_offset_days=-120)
    store.dismiss("tag-1")
    await store.async_save()

    reloaded = EventScoutStore(hass, "entry1")
    await reloaded.async_load()
    assert reloaded.resolve_uid("ics:a:1") == "uid-1"
    assert reloaded.get_override("uid-1").app_deadline == date(2026, 10, 1)
    assert reloaded.get_series_offset("series-1")["deadline_offset_days"] == -60
    assert reloaded.is_dismissed("tag-1")


@pytest.mark.asyncio
async def test_store_prune_dismissed_drops_stale_tags(hass) -> None:  # noqa: ANN001
    store = EventScoutStore(hass, "entry2")
    await store.async_load()
    store.dismiss("keep-me")
    store.dismiss("drop-me")
    store.prune_dismissed({"keep-me"})
    assert store.is_dismissed("keep-me")
    assert not store.is_dismissed("drop-me")


@pytest.mark.asyncio
async def test_store_diagnostics_summary(hass) -> None:  # noqa: ANN001
    store = EventScoutStore(hass, "entry3")
    await store.async_load()
    store.record_alias("a", "b")
    diagnostics = store.as_diagnostics()
    assert diagnostics["uid_alias_count"] == 1


@pytest.mark.asyncio
async def test_store_county_cache_distinguishes_missing_from_unresolved(hass) -> None:  # noqa: ANN001
    from custom_components.event_scout.store import MISSING

    store = EventScoutStore(hass, "entry4")
    await store.async_load()

    assert store.get_county(30.5, -97.6) is MISSING

    store.set_county(30.5, -97.6, None)
    assert store.get_county(30.5, -97.6) is None

    store.set_county(30.5001, -97.6001, "Williamson")
    # Rounds to the same key as 30.5, -97.6 (three decimals).
    assert store.get_county(30.5, -97.6) == "Williamson"


@pytest.mark.asyncio
async def test_store_route_cache_round_trips_and_diagnostics(hass) -> None:  # noqa: ANN001
    store = EventScoutStore(hass, "entry5")
    await store.async_load()

    assert store.get_route(30.5, -97.6) is None

    store.set_route(30.5, -97.6, drive_miles=12.3, drive_minutes=20.1)
    cached = store.get_route(30.5, -97.6)
    assert cached is not None
    assert cached["drive_miles"] == 12.3

    await store.async_save()
    reloaded = EventScoutStore(hass, "entry5")
    await reloaded.async_load()
    assert reloaded.get_route(30.5, -97.6)["drive_minutes"] == 20.1
    assert reloaded.as_diagnostics()["route_cache_count"] == 1
