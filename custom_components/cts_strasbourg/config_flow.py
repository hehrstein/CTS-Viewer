"""Config flow for CTS Strasbourg."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .api import CTSApiAuthenticationError, CTSApiClient, CTSApiError
from .const import (
    CONF_API_TOKEN,
    CONF_PARKINGS,
    CONF_SCAN_INTERVAL,
    CONF_TRAM_STOPS,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)


class CTSStrasbourgConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for CTS Strasbourg."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow state."""
        self._token: str | None = None
        self._scan_interval = DEFAULT_SCAN_INTERVAL_MINUTES
        self._stop_options: list[dict[str, str]] = []
        self._parking_options: list[dict[str, str]] = []
        self._reauth_entry: config_entries.ConfigEntry | None = None
        self._reconfigure_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Validate credentials and load CTS choices."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._token = user_input[CONF_API_TOKEN].strip()
            self._scan_interval = user_input[CONF_SCAN_INTERVAL]
            try:
                self._stop_options, self._parking_options = await _async_load_choices(
                    self.hass, self._token
                )
            except CTSApiAuthenticationError:
                errors["base"] = "invalid_auth"
            except CTSApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return await self.async_step_select()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_TOKEN): str,
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL_MINUTES
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_SCAN_INTERVAL_MINUTES,
                            max=MAX_SCAN_INTERVAL_MINUTES,
                        ),
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user select the tram stops and P+R sensors to create."""
        if user_input is not None:
            return self.async_create_entry(
                title="CTS Strasbourg",
                data={
                    CONF_API_TOKEN: self._token,
                    CONF_SCAN_INTERVAL: self._scan_interval,
                    CONF_TRAM_STOPS: _as_string_list(user_input.get(CONF_TRAM_STOPS)),
                    CONF_PARKINGS: _as_string_list(user_input.get(CONF_PARKINGS)),
                },
            )

        return self.async_show_form(
            step_id="select",
            data_schema=_selection_schema(self._stop_options, self._parking_options),
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Start token renewal after CTS has rejected the current token."""
        self._reauth_entry = self._get_reauth_entry()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Validate and save a replacement CTS API token."""
        assert self._reauth_entry is not None
        return await self._async_step_update_token(
            self._reauth_entry, "reauth_confirm", "reauth_successful", user_input
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Allow a user to replace the CTS token before it expires."""
        if self._reconfigure_entry is None:
            self._reconfigure_entry = self._get_reconfigure_entry()
        return await self._async_step_update_token(
            self._reconfigure_entry,
            "reconfigure",
            "reconfigure_successful",
            user_input,
        )

    async def _async_step_update_token(
        self,
        entry: config_entries.ConfigEntry,
        step_id: str,
        success_reason: str,
        user_input: dict[str, Any] | None,
    ) -> FlowResult:
        """Validate a token and update an existing config entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_API_TOKEN].strip()
            try:
                await CTSApiClient(self.hass, token).async_get_parkings()
            except CTSApiAuthenticationError:
                errors["base"] = "invalid_auth"
            except CTSApiError:
                errors["base"] = "cannot_connect"
            else:
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_API_TOKEN: token}
                )
                return self.async_abort(reason=success_reason)

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({vol.Required(CONF_API_TOKEN): str}),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> CTSStrasbourgOptionsFlow:
        """Return the options flow for this integration."""
        return CTSStrasbourgOptionsFlow()


class CTSStrasbourgOptionsFlow(config_entries.OptionsFlow):
    """Handle changes to selected CTS stops, P+R, and refresh interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the current CTS selections and save new ones."""
        errors: dict[str, str] = {}
        if not hasattr(self, "_stop_options"):
            try:
                self._stop_options, self._parking_options = await _async_load_choices(
                    self.hass, self.config_entry.data[CONF_API_TOKEN]
                )
            except CTSApiAuthenticationError:
                errors["base"] = "invalid_auth"
            except CTSApiError:
                errors["base"] = "cannot_connect"

        if user_input is not None and not errors:
            return self.async_create_entry(
                title="",
                data={
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    CONF_TRAM_STOPS: _as_string_list(user_input.get(CONF_TRAM_STOPS)),
                    CONF_PARKINGS: _as_string_list(user_input.get(CONF_PARKINGS)),
                },
            )

        current_stops = self.config_entry.options.get(
            CONF_TRAM_STOPS, self.config_entry.data.get(CONF_TRAM_STOPS, [])
        )
        current_parkings = self.config_entry.options.get(
            CONF_PARKINGS, self.config_entry.data.get(CONF_PARKINGS, [])
        )
        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(
                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
            ),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=_selection_schema(
                self._stop_options,
                self._parking_options,
                _as_string_list(current_stops),
                _as_string_list(current_parkings),
                current_interval,
            ),
            errors=errors,
        )


async def _async_load_choices(
    hass: HomeAssistant, token: str
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Load choices at setup time rather than every coordinator update."""
    client = CTSApiClient(hass, token)
    stops, parkings = await asyncio.gather(
        client.async_get_tram_stops(), client.async_get_parkings()
    )
    return (
        [{"value": stop["code"], "label": stop["label"]} for stop in stops],
        [
            {"value": designation, "label": designation}
            for designation in sorted(parkings, key=str.casefold)
        ],
    )


def _selection_schema(
    stop_options: list[dict[str, str]],
    parking_options: list[dict[str, str]],
    selected_stops: list[str] | None = None,
    selected_parkings: list[str] | None = None,
    scan_interval: int | None = None,
) -> vol.Schema:
    """Build the common configurable selector form."""
    schema: dict[Any, Any] = {
        vol.Optional(
            CONF_TRAM_STOPS, default=selected_stops or []
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(options=stop_options, multiple=True)
        ),
        vol.Optional(
            CONF_PARKINGS, default=selected_parkings or []
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(options=parking_options, multiple=True)
        ),
    }
    if scan_interval is not None:
        schema[
            vol.Required(CONF_SCAN_INTERVAL, default=scan_interval)
        ] = vol.All(
            vol.Coerce(int),
            vol.Range(
                min=MIN_SCAN_INTERVAL_MINUTES, max=MAX_SCAN_INTERVAL_MINUTES
            ),
        )
    return vol.Schema(schema)


def _as_string_list(value: Any) -> list[str]:
    """Normalize empty, scalar, and multi-select values."""
    if not isinstance(value, list):
        value = [value] if value else []
    return list(dict.fromkeys(str(item) for item in value if item))
