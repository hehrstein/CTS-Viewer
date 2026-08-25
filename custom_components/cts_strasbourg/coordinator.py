"""Data coordinator for CTS Strasbourg."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CTSApiAuthenticationError, CTSApiClient, CTSApiError, CTSApiResult
from .const import (
    CONF_API_TOKEN,
    CONF_PARKINGS,
    CONF_SCAN_INTERVAL,
    CONF_TRAM_STOPS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class CTSDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch the selected CTS real-time datasets at a shared interval."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        interval_minutes = _configured_value(
            entry, CONF_SCAN_INTERVAL, DEFAULT_UPDATE_INTERVAL.total_seconds() / 60
        )
        try:
            update_interval = timedelta(minutes=max(1, int(interval_minutes)))
        except (TypeError, ValueError):
            update_interval = DEFAULT_UPDATE_INTERVAL

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
            config_entry=entry,
        )
        self._client = CTSApiClient(hass, entry.data[CONF_API_TOKEN])
        self._tram_stops = _as_string_list(
            _configured_value(entry, CONF_TRAM_STOPS, [])
        )
        self._parkings = _as_string_list(_configured_value(entry, CONF_PARKINGS, []))
        self._stop_metadata: dict[str, dict[str, Any]] = {}

    @property
    def tram_stops(self) -> list[str]:
        """Return the selected logical tram-stop codes."""
        return self._tram_stops

    @property
    def parkings(self) -> list[str]:
        """Return the selected P+R designations."""
        return self._parkings

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all configured data; one failure makes data unavailable."""
        try:
            if self._tram_stops and not self._stop_metadata:
                stops = await self._client.async_get_tram_stops()
                self._stop_metadata = {
                    stop["code"]: {
                        "name": stop.get("name"),
                        "lines": _as_string_list(stop.get("lines", [])),
                    }
                    for stop in stops
                    if isinstance(stop.get("code"), str)
                    and stop["code"] in self._tram_stops
                }

            request_keys: list[tuple[str, str | None]] = []
            requests: list[Any] = []
            if self._parkings:
                request_keys.append(("parkings", None))
                requests.append(self._client.async_get_parkings_result())
            if self._tram_stops:
                request_keys.append(("messages", None))
                requests.append(self._client.async_get_general_messages_result())
                for stop_code in self._tram_stops:
                    request_keys.append(("departures", stop_code))
                    requests.append(self._client.async_get_departures_result(stop_code))

            results = await asyncio.gather(*requests)
        except CTSApiAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "CTS API token is no longer accepted"
            ) from err
        except CTSApiError as err:
            raise UpdateFailed(str(err)) from err

        parking_result: CTSApiResult[dict[str, dict[str, Any]]] | None = None
        messages_result: CTSApiResult[list[dict[str, Any]]] | None = None
        departure_results: dict[str, CTSApiResult[list[dict[str, Any]]]] = {}
        for (request_type, key), result in zip(request_keys, results, strict=True):
            if request_type == "parkings":
                parking_result = result
            elif request_type == "messages":
                messages_result = result
            elif key is not None:
                departure_results[key] = result

        all_parkings = parking_result.data if parking_result else {}
        messages = messages_result.data if messages_result else []
        selected_parkings = {
            name: all_parkings[name] for name in self._parkings if name in all_parkings
        }
        departures = {
            stop_code: departure_results[stop_code].data
            for stop_code in self._tram_stops
            if stop_code in departure_results
        }
        return {
            "parkings": selected_parkings,
            "departures": departures,
            "stop_metadata": self._stop_metadata,
            "stop_messages": {
                stop_code: _messages_for_stop(
                    messages,
                    self._stop_metadata.get(stop_code, {}).get("lines", []),
                    departures.get(stop_code, []),
                )
                for stop_code in self._tram_stops
            },
            "metadata": {
                "parkings": _result_metadata(parking_result),
                "messages": _result_metadata(messages_result),
                "departures": {
                    stop_code: _result_metadata(departure_results.get(stop_code))
                    for stop_code in self._tram_stops
                },
            },
        }


def _configured_value(entry: ConfigEntry, key: str, default: Any) -> Any:
    """Read options first so options-flow updates take effect after reload."""
    return entry.options.get(key, entry.data.get(key, default))


def _as_string_list(value: Any) -> list[str]:
    """Normalize config-flow selector output."""
    if not isinstance(value, list):
        value = [value] if value else []
    return list(dict.fromkeys(str(item) for item in value if item))


def _result_metadata(result: CTSApiResult[Any] | None) -> dict[str, Any]:
    """Expose a consistent freshness contract to every sensor."""
    if result is None:
        return {}
    return {
        "fetched_at": result.fetched_at.isoformat(),
        "cache_expires_at": (
            result.cache_expires_at.isoformat()
            if result.cache_expires_at is not None
            else None
        ),
        "from_cache": result.from_cache,
    }


def _messages_for_stop(
    messages: list[dict[str, Any]],
    stop_lines: list[str],
    departures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return CTS messages relevant to the selected stop's tram lines."""
    served_lines = {line.upper() for line in stop_lines}
    served_lines.update(
        str(departure.get("line")).upper()
        for departure in departures
        if departure.get("line")
    )
    return [
        message
        for message in messages
        if message.get("network_wide")
        or bool(served_lines.intersection(message.get("lines", [])))
    ]
