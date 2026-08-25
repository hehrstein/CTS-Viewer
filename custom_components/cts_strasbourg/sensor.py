"""Sensors for CTS Strasbourg tram departures and P+R availability."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DATA_ATTRIBUTION, DOMAIN
from .coordinator import CTSDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CTS sensors from a config entry."""
    coordinator: CTSDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        CTSNextTramSensor(coordinator, entry, stop_code)
        for stop_code in coordinator.tram_stops
    ]
    entities.extend(
        CTSDeparturesByDirectionSensor(coordinator, entry, stop_code)
        for stop_code in coordinator.tram_stops
    )
    entities.extend(
        CTSStopInformationSensor(coordinator, entry, stop_code)
        for stop_code in coordinator.tram_stops
    )
    entities.extend(
        CTSParkingAvailabilitySensor(coordinator, entry, parking)
        for parking in coordinator.parkings
    )
    async_add_entities(entities)


class CTSCoordinatorEntity(CoordinatorEntity[CTSDataUpdateCoordinator]):
    """Base entity bound to the CTS shared coordinator."""

    _attr_attribution = DATA_ATTRIBUTION

    def _freshness_attributes(
        self, *source_metadata: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Return the same source and cache metadata for every entity."""
        sources = [metadata for metadata in source_metadata if metadata]
        fetched_at = [
            str(metadata["fetched_at"])
            for metadata in sources
            if metadata.get("fetched_at")
        ]
        cache_expires_at = [
            str(metadata["cache_expires_at"])
            for metadata in sources
            if metadata.get("cache_expires_at")
        ]
        return {
            "data_source": DATA_ATTRIBUTION,
            "data_updated_at": min(fetched_at, default=None),
            "data_cache_expires_at": min(cache_expires_at, default=None),
            "data_from_cache": bool(sources) and all(
                bool(metadata.get("from_cache")) for metadata in sources
            ),
        }


class CTSNextTramSensor(CTSCoordinatorEntity, SensorEntity):
    """Expose the next real-time tram departure at a selected station."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:tram"
    _attr_has_entity_name = True
    _attr_name = "Prochains trams"

    def __init__(
        self, coordinator: CTSDataUpdateCoordinator, entry: ConfigEntry, stop_code: str
    ) -> None:
        """Initialize a tram sensor."""
        super().__init__(coordinator)
        self._stop_code = stop_code
        self._attr_unique_id = f"{entry.entry_id}_tram_{stop_code.casefold()}"
        initial_departures = coordinator.data.get("departures", {}).get(stop_code, [])
        stop_name = (
            initial_departures[0].get("stop_name")
            if initial_departures
            else coordinator.data.get("stop_metadata", {})
            .get(stop_code, {})
            .get("name")
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"tram_stop_{stop_code}")},
            name=f"CTS — arrêt tram {stop_name or stop_code}",
            manufacturer="CTS Strasbourg",
            entry_type=dr.DeviceEntryType.SERVICE,
            configuration_url="https://api.cts-strasbourg.eu/",
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the departure timestamp of the first upcoming tram."""
        departure = self._next_departure
        if departure is None:
            return None
        return dt_util.parse_datetime(departure["expected_departure"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the next departures so a dashboard needs no extra requests."""
        departures = self.coordinator.data.get("departures", {}).get(
            self._stop_code, []
        )
        first = departures[0] if departures else {}
        board_rows = _departure_board_rows(departures)
        metadata = self.coordinator.data.get("metadata", {})
        return {
            **self._freshness_attributes(
                metadata.get("departures", {}).get(self._stop_code),
                metadata.get("messages"),
            ),
            "stop_code": self._stop_code,
            "stop_name": first.get("stop_name"),
            "line": first.get("line"),
            "destination": first.get("destination"),
            "via": first.get("via"),
            "is_realtime": first.get("is_realtime"),
            "recorded_at": first.get("recorded_at"),
            "next_departures": departures,
            "next_departures_by_direction": _departures_by_direction(departures),
            # One row per CTS line and direction, ready for a departure-board
            # card: the next passage and the following one.
            "board_rows": board_rows,
            "traffic_information": self._traffic_information,
        }

    @property
    def _next_departure(self) -> dict[str, Any] | None:
        """Return the first departure, if CTS has one in its look-ahead window."""
        departures = self.coordinator.data.get("departures", {}).get(
            self._stop_code, []
        )
        return departures[0] if departures else None

    @property
    def _traffic_information(self) -> list[dict[str, Any]]:
        """Return active line or network information for this stop."""
        return self.coordinator.data.get("stop_messages", {}).get(self._stop_code, [])


class CTSDeparturesByDirectionSensor(CTSCoordinatorEntity, SensorEntity):
    """Expose a human-readable list of departures grouped by direction."""

    _attr_icon = "mdi:tram-side"
    _attr_has_entity_name = True
    _attr_name = "Passages par direction"

    def __init__(
        self, coordinator: CTSDataUpdateCoordinator, entry: ConfigEntry, stop_code: str
    ) -> None:
        """Initialize the direction-summary sensor."""
        super().__init__(coordinator)
        self._stop_code = stop_code
        self._attr_unique_id = f"{entry.entry_id}_tram_directions_{stop_code.casefold()}"
        stop_name = coordinator.data.get("stop_metadata", {}).get(stop_code, {}).get(
            "name", stop_code
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"tram_stop_{stop_code}")},
            name=f"CTS — arrêt tram {stop_name}",
            manufacturer="CTS Strasbourg",
            entry_type=dr.DeviceEntryType.SERVICE,
            configuration_url="https://api.cts-strasbourg.eu/",
        )

    @property
    def native_value(self) -> str:
        """Return an at-a-glance list for an entities card."""
        departures = self.coordinator.data.get("departures", {}).get(
            self._stop_code, []
        )
        return _format_direction_summary(_departures_by_direction(departures))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the complete, unabridged direction groups."""
        departures = self.coordinator.data.get("departures", {}).get(
            self._stop_code, []
        )
        return {
            **self._freshness_attributes(
                self.coordinator.data.get("metadata", {})
                .get("departures", {})
                .get(self._stop_code)
            ),
            "stop_code": self._stop_code,
            "directions": _departures_by_direction(departures),
            "board_rows": _departure_board_rows(departures),
        }


class CTSStopInformationSensor(CTSCoordinatorEntity, SensorEntity):
    """Expose CTS traffic information relevant to a selected tram stop."""

    _attr_icon = "mdi:information-outline"
    _attr_has_entity_name = True
    _attr_name = "Informations trafic"

    def __init__(
        self, coordinator: CTSDataUpdateCoordinator, entry: ConfigEntry, stop_code: str
    ) -> None:
        """Initialize the traffic-information sensor."""
        super().__init__(coordinator)
        self._stop_code = stop_code
        self._attr_unique_id = f"{entry.entry_id}_tram_info_{stop_code.casefold()}"
        stop_name = coordinator.data.get("stop_metadata", {}).get(stop_code, {}).get(
            "name", stop_code
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"tram_stop_{stop_code}")},
            name=f"CTS — arrêt tram {stop_name}",
            manufacturer="CTS Strasbourg",
            entry_type=dr.DeviceEntryType.SERVICE,
            configuration_url="https://api.cts-strasbourg.eu/",
        )

    @property
    def native_value(self) -> str:
        """Return the first traffic title while keeping full messages in attributes."""
        messages = self._messages
        if not messages:
            return "Aucune information"
        return _truncate_state(str(messages[0].get("title") or "Information CTS"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose all current works and traffic messages for this stop."""
        return {
            **self._freshness_attributes(
                self.coordinator.data.get("metadata", {}).get("messages")
            ),
            "stop_code": self._stop_code,
            "lines_served": self.coordinator.data.get("stop_metadata", {})
            .get(self._stop_code, {})
            .get("lines", []),
            "messages": self._messages,
        }

    @property
    def _messages(self) -> list[dict[str, Any]]:
        """Return messages relevant to this sensor's stop."""
        return self.coordinator.data.get("stop_messages", {}).get(self._stop_code, [])


class CTSParkingAvailabilitySensor(CTSCoordinatorEntity, SensorEntity):
    """Expose the number of free spaces at one CTS P+R."""

    _attr_icon = "mdi:parking"
    _attr_has_entity_name = True
    _attr_name = "Places disponibles"

    def __init__(
        self, coordinator: CTSDataUpdateCoordinator, entry: ConfigEntry, parking: str
    ) -> None:
        """Initialize a P+R availability sensor."""
        super().__init__(coordinator)
        self._parking = parking
        self._attr_unique_id = f"{entry.entry_id}_parking_{parking.casefold()}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"parking_{parking.casefold()}")},
            name=f"CTS — P+R {parking}",
            manufacturer="CTS Strasbourg",
            entry_type=dr.DeviceEntryType.SERVICE,
            configuration_url="https://api.cts-strasbourg.eu/",
        )

    @property
    def native_value(self) -> int | None:
        """Return the current free-space count."""
        parking = self._parking_data
        if parking is None:
            return None
        try:
            return int(parking["AvailableParkingSpots"])
        except (KeyError, TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose capacity, live status, and CTS's timestamp."""
        parking = self._parking_data
        if parking is None:
            return {"parking": self._parking}

        total = _as_int(parking.get("TotalParkingSpots"))
        available = _as_int(parking.get("AvailableParkingSpots"))
        occupancy = (
            round((total - available) / total * 100, 1)
            if total and available is not None
            else None
        )
        return {
            **self._freshness_attributes(
                self.coordinator.data.get("metadata", {}).get("parkings")
            ),
            "parking": self._parking,
            "total_capacity": total,
            "occupancy_percentage": occupancy,
            "is_open": parking.get("Open"),
            "variation": parking.get("Variation"),
            "last_update": parking.get("LastUpdate"),
            "access_information": parking.get("AccessInformation_FR"),
            "latitude": parking.get("Latitude"),
            "longitude": parking.get("Longitude"),
        }

    @property
    def _parking_data(self) -> dict[str, Any] | None:
        """Return the selected P+R data."""
        parking = self.coordinator.data.get("parkings", {}).get(self._parking)
        return parking if isinstance(parking, dict) else None


def _as_int(value: Any) -> int | None:
    """Convert CTS numeric values safely."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _departures_by_direction(
    departures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group upcoming trams by line and CTS's stable direction reference."""
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for departure in departures:
        line = str(departure.get("line") or "Tram")
        direction_ref = departure.get("direction_ref")
        direction = (
            departure.get("destination")
            or departure.get("via")
            or "Direction non renseignée"
        )
        # DirectionRef is the official stable identifier. The destination is
        # only used as a fallback for the uncommon responses without it.
        key = (
            line,
            str(direction_ref) if direction_ref is not None else str(direction),
        )
        group = grouped.setdefault(
            key,
            {
                "line": line,
                "direction": str(direction),
                "direction_ref": direction_ref,
                "departures": [],
            },
        )
        group["departures"].append(departure)
    return list(grouped.values())


def _departure_board_rows(departures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return display-ready rows for a two-column CTS departure board."""
    rows: list[dict[str, Any]] = []
    for group in _departures_by_direction(departures):
        passages = group["departures"][:2]
        rows.append(
            {
                "line": group["line"],
                "direction": group["direction"],
                "direction_ref": group["direction_ref"],
                "next": _board_departure(passages[0]) if passages else None,
                "following": _board_departure(passages[1]) if len(passages) > 1 else None,
            }
        )
    return rows


def _board_departure(departure: dict[str, Any]) -> dict[str, Any]:
    """Add local display values to one raw CTS departure."""
    expected_departure = str(departure.get("expected_departure") or "")
    expected = dt_util.parse_datetime(expected_departure)
    if expected is None:
        return {
            "expected_departure": expected_departure or None,
            "time": None,
            "minutes": None,
            "is_realtime": departure.get("is_realtime"),
        }

    local_expected = dt_util.as_local(expected)
    minutes = max(0, round((expected - dt_util.utcnow()).total_seconds() / 60))
    return {
        "expected_departure": expected_departure,
        "time": local_expected.strftime("%H:%M"),
        "minutes": minutes,
        "is_realtime": departure.get("is_realtime"),
    }


def _format_direction_summary(directions: list[dict[str, Any]]) -> str:
    """Build a compact, readable state for the entity list and dashboard cards."""
    if not directions:
        return "Aucun passage à venir"

    summaries: list[str] = []
    for group in directions:
        departures = group.get("departures", [])
        if not isinstance(departures, list):
            continue
        passages = ", ".join(
            _format_departure(departure)
            for departure in departures[:4]
            if isinstance(departure, dict)
        )
        if passages:
            summaries.append(f"{group.get('direction')}: {passages}")
    return _truncate_state(" | ".join(summaries) or "Aucun passage à venir")


def _format_departure(departure: dict[str, Any]) -> str:
    """Render one departure as a line and a local departure time."""
    line = str(departure.get("line") or "Tram")
    expected = dt_util.parse_datetime(str(departure.get("expected_departure") or ""))
    if expected is None:
        return line
    return f"{line} {dt_util.as_local(expected):%H:%M}"


def _truncate_state(value: str) -> str:
    """Keep sensor states within Home Assistant's 255-character limit."""
    return value if len(value) <= 255 else f"{value[:252]}..."
