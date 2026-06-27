"""Schvitz Master 3000 — sauna session orchestration integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv

from . import const as C
from .blueprints_install import async_install_blueprints
from .coordinator import SchvitzCoordinator
from .frontend import async_register_frontend

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(C.DOMAIN)

_TARGET = {vol.Optional(C.ATTR_TARGET): cv.string}

START_SCHEMA = vol.Schema(
    {
        **_TARGET,
        vol.Optional(C.ATTR_ROUNDS): vol.Coerce(int),
        vol.Optional(C.ATTR_ROUND_MINUTES): vol.Coerce(int),
        vol.Optional(C.ATTR_BREAK_MINUTES): vol.Coerce(int),
        vol.Optional(C.ATTR_MEDIA_PLAYER): cv.string,
        vol.Optional(C.ATTR_PLAYLIST): cv.string,
    }
)
END_SCHEMA = vol.Schema({**_TARGET, vol.Optional(C.ATTR_REASON, default="manual"): cv.string})
SIMPLE_SCHEMA = vol.Schema(_TARGET)
EXTEND_SCHEMA = vol.Schema({**_TARGET, vol.Optional(C.ATTR_MINUTES, default=5): vol.Coerce(int)})
SET_ROUNDS_SCHEMA = vol.Schema({**_TARGET, vol.Required(C.ATTR_ROUNDS): vol.Coerce(int)})
LOG_WATER_SCHEMA = vol.Schema(
    {
        **_TARGET,
        vol.Required(C.ATTR_VOLUME): vol.Coerce(float),
        vol.Optional(C.ATTR_UNIT, default=C.UNIT_ML): vol.In(C.UNITS),
    }
)
APPLY_PROFILE_SCHEMA = vol.Schema({**_TARGET, vol.Required(C.ATTR_PROFILE): cv.string})


def _resolve_coordinator(hass: HomeAssistant, target: str | None) -> SchvitzCoordinator | None:
    """Match a target (entry_id or name slug) to a coordinator.

    With no target and a single configured sauna, return that one.
    """
    coordinators: dict[str, SchvitzCoordinator] = hass.data.get(C.DOMAIN, {})
    if not coordinators:
        return None
    if target is None:
        if len(coordinators) == 1:
            return next(iter(coordinators.values()))
        return None
    if target in coordinators:
        return coordinators[target]
    slug = target.lower().replace(" ", "_")
    for coord in coordinators.values():
        if coord.slug == slug:
            return coord
    return None


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register services, inbound command events, frontend, and blueprints."""
    hass.data.setdefault(C.DOMAIN, {})
    await async_register_frontend(hass)
    await async_install_blueprints(hass)

    def _coord(call: ServiceCall) -> SchvitzCoordinator | None:
        coord = _resolve_coordinator(hass, call.data.get(C.ATTR_TARGET))
        if coord is None:
            _LOGGER.warning("schvitz_master: no sauna matched target %r", call.data.get(C.ATTR_TARGET))
        return coord

    async def handle_start(call: ServiceCall) -> None:
        if coord := _coord(call):
            await coord.async_start_session(
                rounds=call.data.get(C.ATTR_ROUNDS),
                round_minutes=call.data.get(C.ATTR_ROUND_MINUTES),
                break_minutes=call.data.get(C.ATTR_BREAK_MINUTES),
                media_player=call.data.get(C.ATTR_MEDIA_PLAYER),
                playlist=call.data.get(C.ATTR_PLAYLIST),
            )

    async def handle_end(call: ServiceCall) -> None:
        if coord := _coord(call):
            await coord.async_end_session(reason=call.data.get(C.ATTR_REASON, "manual"))

    async def handle_next(call: ServiceCall) -> None:
        if coord := _coord(call):
            await coord.async_next_round()

    async def handle_extend(call: ServiceCall) -> None:
        if coord := _coord(call):
            await coord.async_extend(minutes=call.data.get(C.ATTR_MINUTES, 5))

    async def handle_set_rounds(call: ServiceCall) -> None:
        if coord := _coord(call):
            await coord.async_set_rounds(call.data[C.ATTR_ROUNDS])

    async def handle_skip_warmup(call: ServiceCall) -> None:
        if coord := _coord(call):
            await coord.async_skip_warmup()

    async def handle_log_water(call: ServiceCall) -> None:
        if coord := _coord(call):
            await coord.async_log_water(call.data[C.ATTR_VOLUME], call.data[C.ATTR_UNIT])

    async def handle_apply_profile(call: ServiceCall) -> None:
        if coord := _coord(call):
            await coord.async_apply_profile(call.data[C.ATTR_PROFILE])

    services = (
        (C.SERVICE_START_SESSION, handle_start, START_SCHEMA),
        (C.SERVICE_END_SESSION, handle_end, END_SCHEMA),
        (C.SERVICE_NEXT_ROUND, handle_next, SIMPLE_SCHEMA),
        (C.SERVICE_EXTEND_ROUND, handle_extend, EXTEND_SCHEMA),
        (C.SERVICE_SET_ROUNDS, handle_set_rounds, SET_ROUNDS_SCHEMA),
        (C.SERVICE_SKIP_WARMUP, handle_skip_warmup, SIMPLE_SCHEMA),
        (C.SERVICE_LOG_WATER, handle_log_water, LOG_WATER_SCHEMA),
        (C.SERVICE_APPLY_PROFILE, handle_apply_profile, APPLY_PROFILE_SCHEMA),
    )
    for name, handler, schema in services:
        hass.services.async_register(C.DOMAIN, name, handler, schema=schema)

    # Inbound command events — the low-friction path for the ESPHome panel.
    @callback
    def _on_cmd(event) -> None:
        coord = _resolve_coordinator(hass, event.data.get(C.ATTR_TARGET))
        if coord is None:
            return
        et = event.event_type
        if et == C.EVENT_CMD_START:
            hass.async_create_task(coord.async_start_session())
        elif et == C.EVENT_CMD_STOP:
            hass.async_create_task(coord.async_end_session(reason="panel"))
        elif et == C.EVENT_CMD_NEXT:
            hass.async_create_task(coord.async_next_round())
        elif et == C.EVENT_CMD_EXTEND:
            hass.async_create_task(coord.async_extend(int(event.data.get(C.ATTR_MINUTES, 5))))

    for evt in (C.EVENT_CMD_START, C.EVENT_CMD_STOP, C.EVENT_CMD_NEXT, C.EVENT_CMD_EXTEND):
        hass.bus.async_listen(evt, _on_cmd)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one sauna config entry."""
    hass.data.setdefault(C.DOMAIN, {})

    # async_setup() may have run before Lovelace finished loading; both helpers
    # dedupe, so re-running here is cheap and closes the cold-start race.
    await async_register_frontend(hass)
    await async_install_blueprints(hass)

    coordinator = SchvitzCoordinator(hass, entry)
    await coordinator.async_initialize()
    hass.data[C.DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, C.PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, C.PLATFORMS)
    if unloaded:
        coord: SchvitzCoordinator = hass.data[C.DOMAIN].pop(entry.entry_id)
        await coord.async_shutdown()
    return unloaded
