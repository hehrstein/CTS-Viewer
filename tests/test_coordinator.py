"""Tests for the CTS data coordinator."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from homeassistant.util import dt as dt_util

from custom_components.cts_strasbourg import coordinator as coordinator_module
from custom_components.cts_strasbourg.api import CTSApiResult
from custom_components.cts_strasbourg.const import (
    CONF_API_TOKEN,
    CONF_PARKINGS,
    CONF_SCAN_INTERVAL,
    CONF_TRAM_STOPS,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


class FakeCTSApiClient:
    """CTS API client whose calls can be asserted without a real token."""

    def __init__(self, *args: Any) -> None:
        """Initialize call counters and cache metadata."""
        self.parkings_calls = 0
        self.messages_calls = 0
        self.departures_calls: list[str] = []
        now = dt_util.utcnow()
        self._metadata = {
            "fetched_at": now,
            "cache_expires_at": now + timedelta(minutes=1),
        }

    async def async_get_tram_stops(self) -> list[dict[str, Any]]:
        """Return one configured tram stop."""
        return [{"code": "123", "name": "Test", "lines": ["A"]}]

    async def async_get_parkings_result(
        self,
    ) -> CTSApiResult[dict[str, dict[str, Any]]]:
        """Return one P+R result when it is configured."""
        self.parkings_calls += 1
        return CTSApiResult(
            {"P+R Test": {"Designation": "P+R Test"}}, **self._metadata
        )

    async def async_get_general_messages_result(
        self,
    ) -> CTSApiResult[list[dict[str, Any]]]:
        """Return an empty traffic message list."""
        self.messages_calls += 1
        return CTSApiResult([], **self._metadata)

    async def async_get_departures_result(
        self, stop_code: str
    ) -> CTSApiResult[list[dict[str, Any]]]:
        """Return one departure for the configured stop."""
        self.departures_calls.append(stop_code)
        return CTSApiResult(
            [
                {
                    "line": "A",
                    "direction_ref": "1",
                    "destination": "Illkirch Graffenstaden",
                }
            ],
            **self._metadata,
        )


def make_entry(stops: list[str], parkings: list[str]) -> SimpleNamespace:
    """Create the minimal config-entry shape needed by the coordinator."""
    return SimpleNamespace(
        entry_id="test-entry",
        data={
            CONF_API_TOKEN: "test-token",
            CONF_TRAM_STOPS: stops,
            CONF_PARKINGS: parkings,
            CONF_SCAN_INTERVAL: 1,
        },
        options={},
    )


async def test_coordinator_skips_parkings_without_parking_selection(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No P+R request is made when a user selected only tram stops."""
    client = FakeCTSApiClient()
    monkeypatch.setattr(coordinator_module, "CTSApiClient", lambda *args: client)
    coordinator = coordinator_module.CTSDataUpdateCoordinator(
        hass, make_entry(["123"], [])
    )

    data = await coordinator._async_update_data()

    assert client.parkings_calls == 0
    assert client.messages_calls == 1
    assert client.departures_calls == ["123"]
    assert data["metadata"]["departures"]["123"]["from_cache"] is False
    assert data["metadata"]["departures"]["123"]["cache_expires_at"]


async def test_coordinator_skips_tram_requests_without_stop_selection(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No tram or traffic request is made when a user selected only P+R."""
    client = FakeCTSApiClient()
    monkeypatch.setattr(coordinator_module, "CTSApiClient", lambda *args: client)
    coordinator = coordinator_module.CTSDataUpdateCoordinator(
        hass, make_entry([], ["P+R Test"])
    )

    data = await coordinator._async_update_data()

    assert client.parkings_calls == 1
    assert client.messages_calls == 0
    assert client.departures_calls == []
    assert data["parkings"] == {"P+R Test": {"Designation": "P+R Test"}}
