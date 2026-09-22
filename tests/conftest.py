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


def load_fixture_text(name: str) -> str:
    """Return the text content of a fixture file."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def load_fixture_bytes(name: str) -> bytes:
    """Return the byte content of a fixture file."""
    return (FIXTURES / name).read_bytes()
