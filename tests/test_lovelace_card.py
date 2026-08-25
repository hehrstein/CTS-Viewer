"""Tests for the CTS Lovelace card distribution."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.cts_strasbourg as integration
from custom_components.cts_strasbourg.const import DOMAIN, LOVELACE_CARD_URL

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


class FakeCoordinator:
    """Coordinator stub that avoids CTS calls during integration setup."""

    def __init__(self, hass, entry) -> None:
        """Accept the same arguments as the production coordinator."""

    async def async_config_entry_first_refresh(self) -> None:
        """Simulate a successful initial refresh."""


async def test_setup_serves_lovelace_card_once(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The card JavaScript is exposed once, even if the entry is reloaded."""
    static_paths = AsyncMock()
    forward_setups = AsyncMock()
    monkeypatch.setattr(integration, "CTSDataUpdateCoordinator", FakeCoordinator)
    monkeypatch.setattr(
        hass,
        "http",
        SimpleNamespace(async_register_static_paths=static_paths),
    )
    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", forward_setups
    )

    first_entry = MockConfigEntry(domain=DOMAIN, entry_id="first")
    second_entry = MockConfigEntry(domain=DOMAIN, entry_id="second")

    assert await integration.async_setup_entry(hass, first_entry)
    assert await integration.async_setup_entry(hass, second_entry)

    static_paths.assert_awaited_once()
    static_path = static_paths.await_args.args[0][0]
    assert static_path.url_path == LOVELACE_CARD_URL
    assert static_path.cache_headers is False
    assert Path(static_path.path).name == "cts-departures-card.js"
    assert Path(static_path.path).is_file()
    assert forward_setups.await_count == 2


def test_lovelace_card_registers_its_custom_element() -> None:
    """The distributed module registers the documented Lovelace card type."""
    card = Path(integration.__file__).parent / "frontend" / "cts-departures-card.js"

    content = card.read_text(encoding="utf-8")

    assert 'const CARD_TYPE = "cts-departures-card"' in content
    assert "customElements.define(CARD_TYPE, CTSDeparturesCard)" in content
