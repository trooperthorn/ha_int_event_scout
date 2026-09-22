"""The Event Scout integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_CATEGORIES,
    ATTR_PERIOD,
    ATTR_UID,
    CONF_TARGET_CALENDAR,
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DIGEST_PERIOD_DAILY,
    DIGEST_PERIOD_WEEKLY,
    DOMAIN,
    EVENT_SCOUT_ADD_CAL,
    EVENT_SCOUT_DISMISS,
    PLATFORMS,
    SERVICE_GET_DIGEST,
    SERVICE_REFRESH,
    SERVICE_SEND_ALERTS,
    SERVICE_SEND_DIGEST,
    SERVICE_SET_VENDOR_INFO,
    VENDOR_ORIGIN_MANUAL,
)
from .coordinator import EventScoutCoordinator
from .digest import deadlines_for_period, digest_response, events_for_period, notification_payload_for_alert
from .models import VendorInfo

type EventScoutConfigEntry = ConfigEntry[EventScoutCoordinator]

_DIGEST_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PERIOD): vol.In([DIGEST_PERIOD_DAILY, DIGEST_PERIOD_WEEKLY]),
        vol.Optional(ATTR_CATEGORIES): [str],
    }
)

_SET_VENDOR_INFO_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_UID): str,
        vol.Optional("available"): vol.In(["yes", "no", "unknown"]),
        vol.Optional("app_open"): cv.date,
        vol.Optional("app_deadline"): cv.date,
        vol.Optional("app_url"): str,
        vol.Optional("booth_fee_text"): str,
        vol.Optional("jury_fee_text"): str,
    }
)


def _find_entry(hass: HomeAssistant, call: ServiceCall) -> EventScoutConfigEntry:
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("No Event Scout config entry is configured")
    return entries[0]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register Event Scout services."""

    async def _get_digest(call: ServiceCall) -> ServiceResponse:
        entry = _find_entry(hass, call)
        coordinator = entry.runtime_data
        period = call.data[ATTR_PERIOD]
        categories = call.data.get(ATTR_CATEGORIES)
        events = events_for_period(coordinator.data.events, period=period, categories=categories)
        deadlines = deadlines_for_period(coordinator.data.deadlines, period=period)
        return digest_response(events, deadlines, period=period)

    async def _send_digest(call: ServiceCall) -> None:
        entry = _find_entry(hass, call)
        coordinator = entry.runtime_data
        notify_service = entry.options.get("notify_service")
        if not notify_service:
            raise ServiceValidationError("No notify_service is configured in Event Scout options")
        period = call.data[ATTR_PERIOD]
        categories = call.data.get(ATTR_CATEGORIES)
        events = events_for_period(coordinator.data.events, period=period, categories=categories)
        deadlines = deadlines_for_period(coordinator.data.deadlines, period=period)
        response = digest_response(events, deadlines, period=period)
        await hass.services.async_call(
            "notify",
            notify_service,
            {"title": f"Event Scout {period} digest", "message": response["markdown"]},
            blocking=True,
        )

    async def _send_alerts(call: ServiceCall) -> None:
        entry = _find_entry(hass, call)
        coordinator = entry.runtime_data
        notify_service = entry.options.get("notify_service")
        if not notify_service:
            raise ServiceValidationError("No notify_service is configured in Event Scout options")
        for alert in coordinator.data.deadlines:
            tag = f"event_scout_{alert.event.uid}_{alert.alert_kind}_{alert.days}"
            payload = notification_payload_for_alert(alert, tag)
            await hass.services.async_call(
                "notify", notify_service, {"title": payload["title"], "message": payload["message"], "data": payload["data"]}, blocking=True
            )

    async def _set_vendor_info(call: ServiceCall) -> None:
        entry = _find_entry(hass, call)
        coordinator = entry.runtime_data
        uid = call.data[ATTR_UID]
        vendor = VendorInfo(
            available=call.data.get("available", "unknown"),
            app_open=call.data.get("app_open"),
            app_deadline=call.data.get("app_deadline"),
            app_url=call.data.get("app_url"),
            booth_fee_text=call.data.get("booth_fee_text"),
            jury_fee_text=call.data.get("jury_fee_text"),
            origin=VENDOR_ORIGIN_MANUAL,
            confidence=1.0,
        )
        coordinator.store.set_override(uid, vendor)
        await coordinator.store.async_save()
        await coordinator.async_request_refresh()

    async def _refresh(call: ServiceCall) -> None:
        entry = _find_entry(hass, call)
        await entry.runtime_data.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_GET_DIGEST, _get_digest, schema=_DIGEST_SCHEMA, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, SERVICE_SEND_DIGEST, _send_digest, schema=_DIGEST_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SEND_ALERTS, _send_alerts, schema=vol.Schema({}))
    hass.services.async_register(DOMAIN, SERVICE_SET_VENDOR_INFO, _set_vendor_info, schema=_SET_VENDOR_INFO_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _refresh, schema=vol.Schema({}))

    return True


async def async_setup_entry(hass: HomeAssistant, entry: EventScoutConfigEntry) -> bool:
    """Set up Event Scout from a config entry."""
    update_interval_hours = entry.data.get(CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS)
    coordinator = EventScoutCoordinator(hass, entry, update_interval=timedelta(hours=update_interval_hours))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def _handle_notification_action(event: Any) -> None:
        action = event.data.get("action")
        action_data = event.data.get("action_data", {})
        tag = action_data.get("tag")
        if not tag:
            return
        if action == EVENT_SCOUT_DISMISS:
            coordinator.store.dismiss(tag)
            hass.async_create_task(coordinator.store.async_save())
        elif action == EVENT_SCOUT_ADD_CAL:
            uid = action_data.get("uid")
            target_calendar = entry.options.get(CONF_TARGET_CALENDAR)
            if target_calendar and uid:
                matching = [e for e in coordinator.data.events if e.uid == uid]
                if matching:
                    event_obj = matching[0]
                    if event_obj.all_day:
                        end = event_obj.end or (event_obj.start_date + timedelta(days=1))
                        service_data = {"entity_id": target_calendar, "summary": event_obj.title, "start_date": event_obj.start, "end_date": end}
                    else:
                        end = event_obj.end or event_obj.start
                        service_data = {
                            "entity_id": target_calendar,
                            "summary": event_obj.title,
                            "start_date_time": event_obj.start,
                            "end_date_time": end,
                        }
                    hass.async_create_task(
                        hass.services.async_call(
                            "calendar",
                            "create_event",
                            service_data,
                            blocking=False,
                        )
                    )

    entry.async_on_unload(hass.bus.async_listen("mobile_app_notification_action", _handle_notification_action))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: EventScoutConfigEntry) -> bool:
    """Unload an Event Scout config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
