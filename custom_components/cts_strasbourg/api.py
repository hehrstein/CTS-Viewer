"""Client for the CTS Strasbourg real-time API."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from typing import Any, Generic, TypeVar

import aiohttp

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import API_BASE_URL, TRAM_LINE_REFS

T = TypeVar("T")
_CACHE_MAX_AGE_RE = re.compile(r"(?:^|,)\s*max-age\s*=\s*\"?(\d+)", re.IGNORECASE)
_ISO_DURATION_RE = re.compile(
    r"^PT(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?$"
)


@dataclass(frozen=True, slots=True)
class CTSApiResult(Generic[T]):
    """Data returned by CTS together with its local cache metadata."""

    data: T
    fetched_at: datetime
    cache_expires_at: datetime | None
    from_cache: bool = False


class CTSApiError(HomeAssistantError):
    """Raised when the CTS API cannot be queried."""


class CTSApiAuthenticationError(CTSApiError):
    """Raised when CTS rejects the API token."""


class CTSApiClient:
    """Small, authenticated client for the CTS API."""

    def __init__(self, hass, token: str) -> None:
        """Initialize the client."""
        self._session = async_get_clientsession(hass)
        self._auth = aiohttp.BasicAuth(login=token, password="")
        self._cache: dict[
            tuple[str, tuple[tuple[str, str], ...]], CTSApiResult[dict[str, Any]]
        ] = {}

    async def _async_get(
        self, path: str, params: dict[str, str | int] | None = None
    ) -> CTSApiResult[dict[str, Any]]:
        """Fetch JSON, respecting CTS's response cache directives."""
        cache_key = (
            path,
            tuple(
                sorted(
                    (str(key), str(value)) for key, value in (params or {}).items()
                )
            ),
        )
        now = dt_util.utcnow()
        cached = self._cache.get(cache_key)
        if cached and cached.cache_expires_at and cached.cache_expires_at > now:
            return CTSApiResult(
                data=cached.data,
                fetched_at=cached.fetched_at,
                cache_expires_at=cached.cache_expires_at,
                from_cache=True,
            )

        try:
            async with self._session.get(
                f"{API_BASE_URL}{path}",
                params=params,
                auth=self._auth,
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status in (401, 403):
                    raise CTSApiAuthenticationError("CTS rejected the API token")
                if response.status != 200:
                    raise CTSApiError(
                        f"CTS API returned HTTP {response.status} for {path}"
                    )
                payload = await response.json(content_type=None)
                fetched_at = dt_util.utcnow()
                cache_expires_at = _cache_expires_at(
                    payload, response.headers.get("Cache-Control"), fetched_at
                )
        except aiohttp.ClientError as err:
            raise CTSApiError("Unable to connect to the CTS API") from err
        except TimeoutError as err:
            raise CTSApiError("CTS API request timed out") from err

        if not isinstance(payload, dict):
            raise CTSApiError("CTS API returned an unexpected response")
        result = CTSApiResult(
            data=payload,
            fetched_at=fetched_at,
            cache_expires_at=cache_expires_at,
        )
        if cache_expires_at and cache_expires_at > fetched_at:
            self._cache[cache_key] = result
        return result

    async def async_get_parkings(self) -> dict[str, dict[str, Any]]:
        """Return P+R data keyed by their CTS designation."""
        return (await self.async_get_parkings_result()).data

    async def async_get_parkings_result(
        self,
    ) -> CTSApiResult[dict[str, dict[str, Any]]]:
        """Return P+R data and the timestamp at which CTS supplied it."""
        response = await self._async_get("/cts/park-and-ride")
        parkings = response.data.get("ParkAndRide", [])
        if not isinstance(parkings, list):
            raise CTSApiError("CTS parking response has an unexpected format")

        return CTSApiResult(
            data={
                designation: parking
                for parking in parkings
                if isinstance(parking, dict)
                and isinstance((designation := parking.get("Designation")), str)
            },
            fetched_at=response.fetched_at,
            cache_expires_at=response.cache_expires_at,
            from_cache=response.from_cache,
        )

    async def async_get_tram_stops(self) -> list[dict[str, Any]]:
        """Discover logical tram stops for the configuration selector."""
        return (await self.async_get_tram_stops_result()).data

    async def async_get_tram_stops_result(self) -> CTSApiResult[list[dict[str, Any]]]:
        """Discover logical tram stops and retain CTS response metadata."""
        response = await self._async_get(
            "/siri/2.0/stoppoints-discovery",
            {"includeLinesDestinations": "true"},
        )
        delivery = _get_delivery(response.data, "StopPointsDelivery")
        raw_stops = _as_list(
            delivery.get("AnnotatedStopPointRef")
            if isinstance(delivery, dict)
            else None
        )

        stops: dict[str, dict[str, Any]] = {}
        for stop in raw_stops:
            if not isinstance(stop, dict):
                continue
            extension = stop.get("Extension")
            if not isinstance(extension, dict):
                continue
            logical_code = extension.get("LogicalStopCode")
            if not isinstance(logical_code, str) or not logical_code:
                continue

            lines = [
                str(line.get("LineRef"))
                for line in _as_list(stop.get("Lines"))
                if isinstance(line, dict)
                and str(line.get("LineRef", "")).upper() in TRAM_LINE_REFS
            ]
            if not lines:
                continue

            name = str(stop.get("StopName") or logical_code)
            existing = stops.setdefault(
                logical_code,
                {"code": logical_code, "name": name, "lines": set()},
            )
            existing["lines"].update(lines)

        return CTSApiResult(
            data=[
                {
                    "code": stop["code"],
                    "name": stop["name"],
                    "lines": sorted(stop["lines"]),
                    "label": (
                        f"{stop['name']} ({stop['code']}) — "
                        f"{', '.join(sorted(stop['lines']))}"
                    ),
                }
                for stop in sorted(
                    stops.values(),
                    key=lambda item: (item["name"].casefold(), item["code"]),
                )
            ],
            fetched_at=response.fetched_at,
            cache_expires_at=response.cache_expires_at,
            from_cache=response.from_cache,
        )

    async def async_get_general_messages(self) -> list[dict[str, Any]]:
        """Return current CTS traffic and works messages.

        CTS messages are scoped to one or more lines (or the whole network),
        rather than to a physical platform. The coordinator matches them to
        the tram lines that serve each selected logical stop.
        """
        return (await self.async_get_general_messages_result()).data

    async def async_get_general_messages_result(
        self,
    ) -> CTSApiResult[list[dict[str, Any]]]:
        """Return current CTS messages and their cache metadata."""
        response = await self._async_get("/siri/2.0/general-message")
        delivery = _get_delivery(response.data, "GeneralMessageDelivery")
        messages = [
            message
            for item in _as_list(delivery)
            if isinstance(item, dict)
            for info_message in _as_list(item.get("InfoMessage"))
            if isinstance(info_message, dict)
            and (message := _normalise_message(info_message)) is not None
        ]
        messages.sort(key=lambda item: (item["priority"], item["title"]))
        return CTSApiResult(
            data=messages,
            fetched_at=response.fetched_at,
            cache_expires_at=response.cache_expires_at,
            from_cache=response.from_cache,
        )

    async def async_get_departures(self, stop_code: str) -> list[dict[str, Any]]:
        """Return the upcoming tram departures for one logical stop."""
        return (await self.async_get_departures_result(stop_code)).data

    async def async_get_departures_result(
        self, stop_code: str
    ) -> CTSApiResult[list[dict[str, Any]]]:
        """Return tram departures and the response cache metadata."""
        response = await self._async_get(
            "/siri/2.0/stop-monitoring",
            {
                "MonitoringRef": stop_code,
                "VehicleMode": "tram",
                "MaximumStopVisits": 20,
            },
        )
        delivery = _get_delivery(response.data, "StopMonitoringDelivery")
        departures = [
            departure
            for visit in _iter_visits(delivery)
            if (departure := _normalise_departure(visit)) is not None
        ]
        departures.sort(key=_departure_sort_key)
        return CTSApiResult(
            data=departures,
            fetched_at=response.fetched_at,
            cache_expires_at=response.cache_expires_at,
            from_cache=response.from_cache,
        )


def _cache_expires_at(
    payload: Any, cache_control: str | None, fetched_at: datetime
) -> datetime | None:
    """Return the first moment at which CTS data should be requested again."""
    cache_control = (cache_control or "").casefold()
    if "no-store" in cache_control or "no-cache" in cache_control:
        return None

    max_age = _CACHE_MAX_AGE_RE.search(cache_control)
    if max_age:
        return fetched_at + timedelta(seconds=int(max_age.group(1)))

    return _payload_cache_expires_at(payload, fetched_at)


def _payload_cache_expires_at(payload: Any, fetched_at: datetime) -> datetime | None:
    """Use SIRI validity metadata when an HTTP cache directive is absent."""
    if not isinstance(payload, dict):
        return None

    candidates: list[datetime] = []
    for delivery in _iter_deliveries_for_cache_metadata(payload):
        valid_until = _parse_api_datetime(delivery.get("ValidUntil"))
        if valid_until and valid_until > fetched_at:
            candidates.append(valid_until)

        cycle = _parse_shortest_possible_cycle(delivery.get("ShortestPossibleCycle"))
        if cycle:
            candidates.append(fetched_at + cycle)

    return min(candidates, default=None)


def _iter_deliveries_for_cache_metadata(
    payload: dict[str, Any],
) -> Iterable[dict[str, Any]]:
    """Yield SIRI delivery objects that can carry freshness metadata."""
    service_delivery = payload.get("ServiceDelivery")
    if isinstance(service_delivery, dict):
        yield service_delivery
        values = service_delivery.values()
    else:
        values = payload.values()

    for value in values:
        for item in _as_list(value):
            if isinstance(item, dict):
                yield item


def _parse_api_datetime(value: Any) -> datetime | None:
    """Parse a CTS ISO-8601 timestamp as UTC."""
    if not isinstance(value, str):
        return None
    parsed = dt_util.parse_datetime(value)
    return dt_util.as_utc(parsed) if parsed else None


def _parse_shortest_possible_cycle(value: Any) -> timedelta | None:
    """Parse the SIRI ``ShortestPossibleCycle`` duration when supplied."""
    if isinstance(value, (int, float)) and value > 0:
        return timedelta(seconds=value)
    if not isinstance(value, str):
        return None

    match = _ISO_DURATION_RE.match(value)
    if not match:
        return None
    seconds = sum(
        float(match.group(name) or 0) * multiplier
        for name, multiplier in (("hours", 3600), ("minutes", 60), ("seconds", 1))
    )
    return timedelta(seconds=seconds) if seconds > 0 else None


def _get_delivery(payload: dict[str, Any], key: str) -> dict[str, Any] | list[Any]:
    """Get a SIRI delivery from CTS's current or documented response shape."""
    service_delivery = payload.get("ServiceDelivery")
    if isinstance(service_delivery, dict) and key in service_delivery:
        return service_delivery[key]
    return payload.get(key, {})


def _as_list(value: Any) -> list[Any]:
    """Return a scalar, a list, or None as a list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _iter_visits(delivery: dict[str, Any] | list[Any]) -> Iterable[dict[str, Any]]:
    """Yield visits from both SIRI response formats currently used by CTS."""
    for item in _as_list(delivery):
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("MonitoredVehicleJourney"), dict):
            yield item
            continue
        for visit in _as_list(item.get("MonitoredStopVisit")):
            if isinstance(visit, dict):
                yield visit


def _normalise_departure(visit: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a CTS SIRI visit to data suitable for Home Assistant."""
    journey = visit.get("MonitoredVehicleJourney")
    if not isinstance(journey, dict):
        return None
    monitored_call = journey.get("MonitoredCall")
    if not isinstance(monitored_call, dict):
        monitored_call = {}

    expected_departure = (
        monitored_call.get("ExpectedDepartureTime")
        or monitored_call.get("AimedDepartureTime")
        or journey.get("ExpectedDepartureTime")
    )
    if not isinstance(expected_departure, str):
        return None

    extension = monitored_call.get("Extension")
    realtime = extension.get("IsRealTime") if isinstance(extension, dict) else None
    return {
        "line": journey.get("PublishedLineName") or journey.get("LineRef"),
        # CTS documents DirectionRef (0 or 1) as the stable way to distinguish
        # the two directions of a line. Destination names may vary for short
        # workings, so retain both values for dashboard rendering.
        "direction_ref": journey.get("DirectionRef"),
        "destination": journey.get("DestinationName"),
        "via": journey.get("Via"),
        "expected_departure": expected_departure,
        "is_realtime": realtime,
        "stop_name": monitored_call.get("StopPointName"),
        "stop_point_ref": monitored_call.get("StopPointRef"),
        "recorded_at": visit.get("RecordedAtTime"),
    }


def _normalise_message(info_message: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a CTS general message into a display-ready data structure."""
    content = info_message.get("Content")
    if not isinstance(content, dict):
        return None

    texts_by_zone: dict[str, str] = {}
    for message in _as_list(content.get("Message")):
        if not isinstance(message, dict):
            continue
        zone = str(message.get("MessageZoneRef") or "details").casefold()
        text = _pick_french_text(message.get("MessageText"))
        if text:
            texts_by_zone[zone] = text

    title = texts_by_zone.get("title") or texts_by_zone.get("details")
    if not title:
        return None

    lines = sorted(
        {
            str(line).upper()
            for line in _as_list(content.get("ImpactedLineRef"))
            if isinstance(line, str) and line
        }
    )
    return {
        "id": info_message.get("ItemIdentifier"),
        "updated_id": info_message.get("InfoMessageIdentifier"),
        "channel": info_message.get("InfoChannelRef"),
        "priority": content.get("Priority") or "Normal",
        "lines": lines,
        "network_wide": content.get("ImpactedGroupOfLinesRef") == "CTS",
        "title": title,
        "details": texts_by_zone.get("details"),
        "period": texts_by_zone.get("period"),
        "impact_start": content.get("ImpactStartDateTime"),
        "impact_end": content.get("ImpactEndDateTime"),
        "recorded_at": info_message.get("RecordedAtTime"),
        "valid_until": info_message.get("ValidUntilTime"),
    }


def _pick_french_text(value: Any) -> str | None:
    """Pick French text first, then the first non-empty translation."""
    translations = [item for item in _as_list(value) if isinstance(item, dict)]
    for translation in translations:
        language = str(translation.get("Lang") or "").casefold()
        text = translation.get("Value")
        if isinstance(text, str) and text and language.startswith("fr"):
            return text
    for translation in translations:
        text = translation.get("Value")
        if isinstance(text, str) and text:
            return text
    return None


def _departure_sort_key(departure: dict[str, Any]) -> datetime:
    """Sort malformed timestamps last without breaking the coordinator."""
    try:
        return datetime.fromisoformat(
            str(departure["expected_departure"]).replace("Z", "+00:00")
        )
    except (KeyError, TypeError, ValueError):
        return datetime.max
