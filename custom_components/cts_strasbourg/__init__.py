"""The CTS Strasbourg integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DATA_LOVELACE_CARD_REGISTERED,
    DOMAIN,
    LOVELACE_CARD_URL,
    PLATFORMS,
)
from .coordinator import CTSDataUpdateCoordinator

_LOVELACE_CARD_PATH = Path(__file__).parent / "frontend" / "cts-departures-card.js"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up CTS Strasbourg from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get(DATA_LOVELACE_CARD_REGISTERED):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    LOVELACE_CARD_URL,
                    str(_LOVELACE_CARD_PATH),
                    cache_headers=False,
                )
            ]
        )
        domain_data[DATA_LOVELACE_CARD_REGISTERED] = True

    coordinator = CTSDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    domain_data[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a CTS Strasbourg config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entities after selected stops, P+R, or interval change."""
    await hass.config_entries.async_reload(entry.entry_id)
