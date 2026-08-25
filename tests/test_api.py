"""Tests for CTS API parsing and cache handling."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from homeassistant.util import dt as dt_util

from custom_components.cts_strasbourg.api import (
    CTSApiClient,
    CTSApiResult,
    _cache_expires_at,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


class FakeResponse:
    """Minimal aiohttp response used to test the local cache."""

    status = 200

    def __init__(self, payload: dict[str, Any], cache_control: str) -> None:
        """Initialize the fake response."""
        self.headers = {"Cache-Control": cache_control}
        self._payload = payload

    async def __aenter__(self) -> FakeResponse:
        """Enter the asynchronous response context."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit the asynchronous response context."""

    async def json(self, content_type: str | None = None) -> dict[str, Any]:
        """Return the configured JSON payload."""
        return self._payload


class FakeSession:
    """Minimal aiohttp session that records HTTP requests."""

    def __init__(self) -> None:
        """Initialize the fake session."""
        self.request_count = 0

    def get(self, *args: Any, **kwargs: Any) -> FakeResponse:
        """Return the same cacheable response for each request."""
        self.request_count += 1
        return FakeResponse({"payload": "cached"}, "public, max-age=60")


async def test_client_reuses_response_until_cache_expiry(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CTS cache directive prevents an identical second API call."""
    session = FakeSession()
    monkeypatch.setattr(
        "custom_components.cts_strasbourg.api.async_get_clientsession",
        lambda hass: session,
    )
    client = CTSApiClient(hass, "test-token")

    first = await client._async_get("/example", {"line": "A"})
    second = await client._async_get("/example", {"line": "A"})

    assert first.from_cache is False
    assert second.from_cache is True
    assert second.fetched_at == first.fetched_at
    assert session.request_count == 1


def test_cache_falls_back_to_siri_validity_metadata() -> None:
    """SIRI validity metadata is used when CTS omits Cache-Control."""
    fetched_at = dt_util.utcnow()
    valid_until = fetched_at + timedelta(minutes=2)
    payload = {
        "ServiceDelivery": {
            "StopMonitoringDelivery": [
                {"ValidUntil": valid_until.isoformat()}
            ]
        }
    }

    assert _cache_expires_at(payload, None, fetched_at) == valid_until


def test_cache_falls_back_to_shortest_possible_cycle() -> None:
    """SIRI's shortest polling cycle becomes the cache duration."""
    fetched_at = dt_util.utcnow()
    payload = {
        "ServiceDelivery": {
            "StopMonitoringDelivery": [{"ShortestPossibleCycle": "PT30S"}]
        }
    }

    assert _cache_expires_at(payload, None, fetched_at) == fetched_at + timedelta(
        seconds=30
    )


async def test_departures_preserve_line_direction_and_realtime_metadata(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A normalized departure retains values needed by the departure board."""
    monkeypatch.setattr(
        "custom_components.cts_strasbourg.api.async_get_clientsession",
        lambda hass: FakeSession(),
    )
    client = CTSApiClient(hass, "test-token")
    fetched_at = dt_util.utcnow()
    payload = {
        "ServiceDelivery": {
            "StopMonitoringDelivery": {
                "MonitoredStopVisit": [
                    {
                        "RecordedAtTime": "2030-01-01T10:00:00Z",
                        "MonitoredVehicleJourney": {
                            "PublishedLineName": "A",
                            "DirectionRef": "1",
                            "DestinationName": "Illkirch Graffenstaden",
                            "MonitoredCall": {
                                "ExpectedDepartureTime": "2030-01-01T10:08:00Z",
                                "StopPointName": "Langstross Grand Rue",
                                "Extension": {"IsRealTime": True},
                            },
                        },
                    }
                ]
            }
        }
    }

    async def fake_get(*args: Any, **kwargs: Any) -> CTSApiResult[dict[str, Any]]:
        """Return a recorded CTS response without using the network."""
        return CTSApiResult(payload, fetched_at, None)

    monkeypatch.setattr(client, "_async_get", fake_get)
    result = await client.async_get_departures_result("123")

    assert result.data == [
        {
            "line": "A",
            "direction_ref": "1",
            "destination": "Illkirch Graffenstaden",
            "via": None,
            "expected_departure": "2030-01-01T10:08:00Z",
            "is_realtime": True,
            "stop_name": "Langstross Grand Rue",
            "stop_point_ref": None,
            "recorded_at": "2030-01-01T10:00:00Z",
        }
    ]
