"""Shared fixtures for Event Scout tests."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):  # noqa: ANN001
    """Enable custom integration loading for every test."""
    yield


@pytest.fixture(autouse=True)
def frozen_today(freezer):  # noqa: ANN001
    """Pin "today" inside the window the fixture events fall in.

    The fixtures carry fixed 2026 dates and the sources keep only events between
    today and the configured horizon, so the suite would start failing once those
    dates passed.
    """
    freezer.move_to("2026-09-20 12:00:00")


def load_fixture_text(name: str) -> str:
    """Return the text content of a fixture file."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def load_fixture_bytes(name: str) -> bytes:
    """Return the byte content of a fixture file."""
    return (FIXTURES / name).read_bytes()
