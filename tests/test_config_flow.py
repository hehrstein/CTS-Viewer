"""Tests for the CTS Strasbourg configuration and options flows."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.data_entry_flow import FlowResultType

from custom_components.cts_strasbourg import config_flow
from custom_components.cts_strasbourg.const import (
    CONF_API_TOKEN,
    CONF_PARKINGS,
    CONF_SCAN_INTERVAL,
    CONF_TRAM_STOPS,
    DOMAIN,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def test_options_flow_opens_for_an_existing_entry(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Options use the config entry provided by Home Assistant's base flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_TOKEN: "test-token",
            CONF_SCAN_INTERVAL: 1,
            CONF_TRAM_STOPS: ["123"],
            CONF_PARKINGS: [],
        },
    )
    entry.add_to_hass(hass)

    async def fake_load_choices(
        _hass: Any, _token: str
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        """Avoid a CTS API request while opening the options form."""
        return ([{"value": "123", "label": "Test tram"}], [])

    monkeypatch.setattr(config_flow, "_async_load_choices", fake_load_choices)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
