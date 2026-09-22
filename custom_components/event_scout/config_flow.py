"""Config flow for Event Scout: hub entry, options, and source subentries."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlowWithReload,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CATEGORIES,
    CONF_CATEGORIES,
    CONF_DIGEST_TIME,
    CONF_HORIZON_DAYS,
    CONF_NOTIFY_SERVICE,
    CONF_RADIUS_MILES,
    CONF_RECONNAISSANCE_DAYS,
    CONF_TARGET_CALENDAR,
    CONF_UPDATE_INTERVAL_HOURS,
    CONF_VENDOR_LEAD_DAYS,
    DEFAULT_DIGEST_TIME,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_RADIUS_MILES,
    DEFAULT_RECONNAISSANCE_DAYS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DEFAULT_VENDOR_LEAD_DAYS,
    DOMAIN,
    MIN_UPDATE_INTERVAL_HOURS,
    SOURCE_KIND_EVENTBRITE,
    SOURCE_KIND_ICS,
    SOURCE_KIND_JSONLD,
    SOURCE_KIND_MANUAL,
    SOURCE_KIND_SOCRATA,
    SOURCE_KIND_TICKETMASTER,
    SOURCE_KINDS,
    SOURCE_TYPE,
)
from .sources import SourceContext, SourceValidationError, get_source

HUB_SCHEMA = vol.Schema(
    {
        vol.Required("name", default="Event Scout"): str,
        vol.Optional("latitude"): vol.Coerce(float),
        vol.Optional("longitude"): vol.Coerce(float),
        vol.Optional(CONF_RADIUS_MILES, default=DEFAULT_RADIUS_MILES): vol.Coerce(int),
        vol.Optional(CONF_HORIZON_DAYS, default=DEFAULT_HORIZON_DAYS): vol.Coerce(int),
        vol.Optional(CONF_UPDATE_INTERVAL_HOURS, default=DEFAULT_UPDATE_INTERVAL_HOURS): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_UPDATE_INTERVAL_HOURS)
        ),
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NOTIFY_SERVICE, default=""): str,
        vol.Optional(CONF_VENDOR_LEAD_DAYS, default=DEFAULT_VENDOR_LEAD_DAYS): [vol.Coerce(int)],
        vol.Optional(CONF_RECONNAISSANCE_DAYS, default=DEFAULT_RECONNAISSANCE_DAYS): vol.Coerce(int),
        vol.Optional(CONF_DIGEST_TIME, default=DEFAULT_DIGEST_TIME): str,
        vol.Optional(CONF_CATEGORIES, default=CATEGORIES): [vol.In(CATEGORIES)],
        vol.Optional(CONF_TARGET_CALENDAR, default=""): str,
    }
)

_SOURCE_KIND_SCHEMA = vol.Schema({vol.Required("source_kind"): vol.In(SOURCE_KINDS)})

_SOURCE_ARG_SCHEMAS: dict[str, vol.Schema] = {
    SOURCE_KIND_ICS: vol.Schema(
        {
            vol.Required("name"): str,
            vol.Required("url"): str,
            vol.Required("category", default="other"): vol.In(CATEGORIES),
            vol.Optional("username"): str,
            vol.Optional("password"): str,
        }
    ),
    SOURCE_KIND_JSONLD: vol.Schema(
        {
            vol.Required("name"): str,
            vol.Required("url"): str,
            vol.Required("category", default="other"): vol.In(CATEGORIES),
            vol.Optional("vendor_probe", default=False): bool,
        }
    ),
    SOURCE_KIND_TICKETMASTER: vol.Schema(
        {
            vol.Required("name"): str,
            vol.Required("api_key"): str,
            vol.Optional("segments", default=[]): [str],
            vol.Optional("keyword"): str,
        }
    ),
    SOURCE_KIND_SOCRATA: vol.Schema(
        {
            vol.Required("name"): str,
            vol.Required("domain"): str,
            vol.Required("dataset_id"): str,
            vol.Required("category", default="other"): vol.In(CATEGORIES),
            vol.Optional("field_title", default="title"): str,
            vol.Optional("field_start", default="start_date"): str,
            vol.Optional("field_end"): str,
            vol.Optional("field_url"): str,
            vol.Optional("field_venue"): str,
            vol.Optional("app_token"): str,
        }
    ),
    SOURCE_KIND_MANUAL: vol.Schema(
        {
            vol.Required("name"): str,
            vol.Required("title"): str,
            vol.Required("category", default="other"): vol.In(CATEGORIES),
            vol.Required("month"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
            vol.Optional("day"): vol.All(vol.Coerce(int), vol.Range(min=1, max=31)),
            vol.Optional("weekday"): vol.All(vol.Coerce(int), vol.Range(min=0, max=6)),
            vol.Optional("nth"): vol.All(vol.Coerce(int), vol.Range(min=-1, max=5)),
            vol.Optional("city"): str,
            vol.Optional("vendor_open"): str,
            vol.Optional("vendor_deadline"): str,
            vol.Optional("vendor_url"): str,
        }
    ),
    SOURCE_KIND_EVENTBRITE: vol.Schema(
        {
            vol.Required("name"): str,
            vol.Required("token"): str,
            vol.Required("organization_ids"): str,
            vol.Optional("venue_ids"): str,
            vol.Required("category", default="other"): vol.In(CATEGORIES),
        }
    ),
}


class EventScoutConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for the Event Scout hub entry."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect the hub configuration."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input["name"].strip().lower())
            self._abort_if_unique_id_configured()
            data = dict(user_input)
            data.setdefault("latitude", self.hass.config.latitude)
            data.setdefault("longitude", self.hass.config.longitude)
            return self.async_create_entry(title=user_input["name"], data=data)

        return self.async_show_form(step_id="user", data_schema=HUB_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> EventScoutOptionsFlow:
        """Create the options flow."""
        return EventScoutOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the subentry types this integration supports."""
        return {SOURCE_TYPE: SourceSubentryFlow}


class EventScoutOptionsFlow(OptionsFlowWithReload):
    """Options flow for hub-level settings; reloads the entry automatically."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the hub options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, self.config_entry.options),
        )


class SourceSubentryFlow(ConfigSubentryFlow):
    """Handle add and reconfigure flows for one source subentry."""

    _kind: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Pick the source kind."""
        if user_input is not None:
            self._kind = user_input["source_kind"]
            return await self.async_step_args()

        return self.async_show_form(step_id="user", data_schema=_SOURCE_KIND_SCHEMA)

    async def async_step_args(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Collect and validate the arguments for the chosen source kind."""
        assert self._kind is not None
        errors: dict[str, str] = {}
        schema = _SOURCE_ARG_SCHEMAS[self._kind]

        if user_input is not None:
            data = dict(user_input)
            session = async_get_clientsession(self.hass)
            source = get_source(self._kind, {k: v for k, v in data.items() if k != "name"})
            ctx = SourceContext(
                subentry_id="pending",
                name=data.get("name", self._kind),
                category=data.get("category", "other"),
                latitude=self.hass.config.latitude,
                longitude=self.hass.config.longitude,
            )
            try:
                await source.async_validate(session, ctx)
            except SourceValidationError as err:
                errors["base"] = "cannot_connect"
                return self.async_show_form(step_id="args", data_schema=schema, errors=errors, description_placeholders={"error": str(err)})

            data["source_kind"] = self._kind
            return self.async_create_entry(title=data.get("name", self._kind), data=data)

        return self.async_show_form(step_id="args", data_schema=schema, errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Reconfigure an existing source subentry."""
        subentry = self._get_reconfigure_subentry()
        self._kind = subentry.data.get("source_kind")
        assert self._kind is not None
        schema = _SOURCE_ARG_SCHEMAS[self._kind]

        if user_input is not None:
            data = dict(user_input)
            data["source_kind"] = self._kind
            return self.async_update_and_abort(self._get_entry(), subentry, title=data.get("name", self._kind), data=data)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(schema, subentry.data),
        )
