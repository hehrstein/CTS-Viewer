"""Constants for the CTS Strasbourg integration."""

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "cts_strasbourg"
API_BASE_URL: Final = "https://api.cts-strasbourg.eu/v1"
DATA_ATTRIBUTION: Final = "Données issues de CTS — API Open Data CTS"
LOVELACE_CARD_URL: Final = f"/{DOMAIN}/cts-departures-card.js"
DATA_LOVELACE_CARD_REGISTERED: Final = "lovelace_card_registered"

CONF_API_TOKEN: Final = "api_token"
CONF_TRAM_STOPS: Final = "tram_stops"
CONF_PARKINGS: Final = "parkings"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_SCAN_INTERVAL_MINUTES: Final = 1
DEFAULT_UPDATE_INTERVAL: Final = timedelta(
    minutes=DEFAULT_SCAN_INTERVAL_MINUTES
)
MIN_SCAN_INTERVAL_MINUTES: Final = 1
MAX_SCAN_INTERVAL_MINUTES: Final = 15

TRAM_LINE_REFS: Final = frozenset({"A", "B", "C", "D", "E", "F"})
PLATFORMS: Final = [Platform.SENSOR]
