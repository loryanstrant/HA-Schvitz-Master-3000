"""Config + options flow for Schvitz Master 3000.

Holds only the *durable wiring* (which physical entities this sauna uses). The
per-session knobs (round count, durations, media/playlist) are runtime entities so
they can be changed each session without reconfiguring.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from . import const as C


def _num(min_v, max_v, step, unit=None):
    cfg = {"min": min_v, "max": max_v, "step": step, "mode": selector.NumberSelectorMode.BOX}
    if unit is not None:
        cfg["unit_of_measurement"] = unit
    return selector.NumberSelector(selector.NumberSelectorConfig(**cfg))


def _add_entity(schema: dict, key: str, defaults: dict, *, required: bool = False, **cfg) -> None:
    """Add an EntitySelector field, only attaching a default when one exists.

    An empty-string default fails EntitySelector validation, so for optional
    fields with no configured value we omit the default entirely.
    """
    entity_cfg = selector.EntitySelector(selector.EntitySelectorConfig(**cfg))
    existing = defaults.get(key)
    if required:
        marker = vol.Required(key, default=existing) if existing else vol.Required(key)
    elif existing:
        marker = vol.Optional(key, default=existing)
    else:
        marker = vol.Optional(key)
    schema[marker] = entity_cfg


def _sauna_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    schema: dict[Any, Any] = {
        vol.Required(C.CONF_NAME, default=d.get(C.CONF_NAME, "Sauna")): str,
    }
    _add_entity(schema, C.CONF_TEMP_SENSOR, d, required=True, domain="sensor", device_class="temperature")
    _add_entity(schema, C.CONF_SEAT_TEMP_SENSOR, d, domain="sensor", device_class="temperature")
    _add_entity(schema, C.CONF_DOOR_SENSOR, d, required=True, domain="binary_sensor", device_class="door")
    _add_entity(schema, C.CONF_VENT_SENSOR, d, domain="binary_sensor")
    _add_entity(schema, C.CONF_HEATER_SWITCH, d, required=True, domain=["switch", "input_boolean"])
    _add_entity(schema, C.CONF_PLUG_SWITCH, d, domain="switch")
    _add_entity(schema, C.CONF_PRE_SWITCHES, d, domain=["switch", "light", "input_boolean"], multiple=True)
    _add_entity(schema, C.CONF_POST_SWITCHES, d, domain=["switch", "light", "input_boolean"], multiple=True)
    _add_entity(schema, C.CONF_MEDIA_PLAYER, d, domain="media_player")

    schema[vol.Optional(C.CONF_DEFAULT_PLAYLIST, default=d.get(C.CONF_DEFAULT_PLAYLIST, ""))] = str
    schema[vol.Optional(C.CONF_DEFAULT_VOLUME, default=d.get(C.CONF_DEFAULT_VOLUME, C.DEFAULT_VOLUME))] = _num(0, 1, 0.05)

    _add_entity(schema, C.CONF_WATER_SENSOR, d, domain="sensor")
    schema[
        vol.Optional(C.CONF_WATER_SOURCE_MODE, default=d.get(C.CONF_WATER_SOURCE_MODE, C.SOURCE_MODE_DELTA))
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=C.SOURCE_MODES, translation_key="source_mode",
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )
    _add_entity(schema, C.CONF_HR_SENSOR, d, domain="sensor")

    schema[vol.Optional(C.CONF_NOTIFY_SERVICE, default=d.get(C.CONF_NOTIFY_SERVICE, ""))] = str
    schema[vol.Required(C.CONF_DEFAULT_ROUNDS, default=d.get(C.CONF_DEFAULT_ROUNDS, C.DEFAULT_ROUNDS))] = _num(1, 6, 1)
    schema[vol.Required(C.CONF_DEFAULT_ROUND_MIN, default=d.get(C.CONF_DEFAULT_ROUND_MIN, C.DEFAULT_ROUND_MIN))] = _num(3, 30, 1, "min")
    schema[vol.Required(C.CONF_DEFAULT_BREAK_MIN, default=d.get(C.CONF_DEFAULT_BREAK_MIN, C.DEFAULT_BREAK_MIN))] = _num(2, 30, 1, "min")
    schema[vol.Optional(C.CONF_WARMUP_TARGET_TEMP, default=d.get(C.CONF_WARMUP_TARGET_TEMP, C.DEFAULT_WARMUP_TARGET_TEMP))] = _num(40, 110, 1, "°C")

    return vol.Schema(schema)


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    """Drop empty optional strings so they don't persist as ""."""
    for key in (C.CONF_DEFAULT_PLAYLIST, C.CONF_NOTIFY_SERVICE):
        if not user_input.get(key):
            user_input.pop(key, None)
    return user_input


class SchvitzConfigFlow(config_entries.ConfigFlow, domain=C.DOMAIN):
    """Initial setup flow — one config entry per sauna."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            name = user_input[C.CONF_NAME].strip()
            await self.async_set_unique_id(f"{C.DOMAIN}_{name.lower().replace(' ', '_')}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=name, data=_clean(user_input))
        return self.async_show_form(step_id="user", data_schema=_sauna_schema())

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "SchvitzOptionsFlow":
        return SchvitzOptionsFlow(config_entry)


class SchvitzOptionsFlow(config_entries.OptionsFlow):
    """Edit an existing sauna's wiring."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        # HA 2024.12+ made OptionsFlow.config_entry a read-only property; assigning
        # it raises AttributeError surfaced as a 500. Store under a private name.
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=_clean(user_input))
        merged = {**self._entry.data, **self._entry.options}
        return self.async_show_form(step_id="init", data_schema=_sauna_schema(merged))
