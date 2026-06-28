"""Config + options flow for Schvitz Master 3000.

Five grouped, explained screens (with Next buttons + an "N of 5" counter in each
title via strings.json):
  1. sauna     — the physical sauna (temperature, door/vent, plug power)
  2. power      — heater trigger, switches, and the start scene
  3. session    — rounds, durations (break optional), ready temp, safety timeouts
  4. media      — speaker, playlist (picked from Music Assistant), volume, music start
  5. tracking   — optional water/heart-rate sensors and notifications
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from . import const as C


# --------------------------------------------------------------------- helpers
def _num(min_v, max_v, step, unit=None):
    cfg = {"min": min_v, "max": max_v, "step": step, "mode": selector.NumberSelectorMode.BOX}
    if unit is not None:
        cfg["unit_of_measurement"] = unit
    return selector.NumberSelector(selector.NumberSelectorConfig(**cfg))


def _add_entity(schema: dict, key: str, defaults: dict, *, required: bool = False, **cfg) -> None:
    entity = selector.EntitySelector(selector.EntitySelectorConfig(**cfg))
    existing = defaults.get(key)
    if required:
        marker = vol.Required(key, default=existing) if existing else vol.Required(key)
    elif existing:
        marker = vol.Optional(key, default=existing)
    else:
        marker = vol.Optional(key)
    schema[marker] = entity


async def _ma_playlists(hass: HomeAssistant) -> list[tuple[str, str]]:
    """(name, uri) of Music Assistant playlists, via its get_library service."""
    try:
        entries = hass.config_entries.async_entries("music_assistant")
        if not entries or not hass.services.has_service("music_assistant", "get_library"):
            return []
        resp = await hass.services.async_call(
            "music_assistant", "get_library",
            {"config_entry_id": entries[0].entry_id, "media_type": "playlist", "limit": 500},
            blocking=True, return_response=True,
        )
        items = None
        if isinstance(resp, dict):
            items = resp.get("items")
            if items is None:
                for v in resp.values():
                    if isinstance(v, list):
                        items = v
                        break
        return [
            (it["name"], it["uri"])
            for it in (items or [])
            if isinstance(it, dict) and it.get("name") and it.get("uri")
        ]
    except Exception:  # pragma: no cover - MA shape is version-fragile
        return []


# --------------------------------------------------------- per-step schemas
def _schema_sauna(hass: HomeAssistant, d: dict) -> vol.Schema:
    schema: dict[Any, Any] = {
        vol.Required(C.CONF_NAME, default=d.get(C.CONF_NAME, "Sauna")): str,
    }
    _add_entity(schema, C.CONF_TEMP_SENSOR, d, required=True, domain="sensor", device_class="temperature")
    _add_entity(schema, C.CONF_SEAT_TEMP_SENSOR, d, domain="sensor", device_class="temperature")
    _add_entity(schema, C.CONF_DOOR_SENSOR, d, domain="binary_sensor", device_class="door")
    _add_entity(schema, C.CONF_VENT_SENSOR, d, domain="binary_sensor")
    _add_entity(schema, C.CONF_POWER_SENSOR, d, domain="sensor", device_class="power")
    _add_entity(schema, C.CONF_OPERATION_SENSOR, d, domain="sensor")
    return vol.Schema(schema)


def _schema_power(hass: HomeAssistant, d: dict) -> vol.Schema:
    schema: dict[Any, Any] = {
        vol.Optional(C.CONF_TRIGGER_ON_HEATER, default=d.get(C.CONF_TRIGGER_ON_HEATER, True)): bool,
    }
    _add_entity(schema, C.CONF_HEATER_SWITCH, d, domain=["switch", "input_boolean"])
    _add_entity(schema, C.CONF_PLUG_SWITCH, d, domain="switch")
    _add_entity(schema, C.CONF_START_SCENE, d, domain="scene")
    _add_entity(schema, C.CONF_PRE_SWITCHES, d, domain=["switch", "light", "input_boolean"], multiple=True)
    _add_entity(schema, C.CONF_END_OFF_SWITCHES, d, domain=["switch", "light", "input_boolean"], multiple=True)
    return vol.Schema(schema)


def _schema_session(hass: HomeAssistant, d: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(C.CONF_DEFAULT_ROUNDS, default=d.get(C.CONF_DEFAULT_ROUNDS, C.DEFAULT_ROUNDS)): _num(1, 6, 1),
            vol.Required(C.CONF_DEFAULT_ROUND_MIN, default=d.get(C.CONF_DEFAULT_ROUND_MIN, C.DEFAULT_ROUND_MIN)): _num(3, 30, 1, "min"),
            vol.Optional(C.CONF_DEFAULT_BREAK_MIN, default=d.get(C.CONF_DEFAULT_BREAK_MIN, 0)): _num(0, 30, 1, "min"),
            vol.Optional(C.CONF_WARMUP_TARGET_TEMP, default=d.get(C.CONF_WARMUP_TARGET_TEMP, C.DEFAULT_WARMUP_TARGET_TEMP)): _num(40, 110, 1, "°C"),
            vol.Optional(C.CONF_IDLE_HEATING_TIMEOUT, default=d.get(C.CONF_IDLE_HEATING_TIMEOUT, C.DEFAULT_IDLE_HEATING_TIMEOUT)): _num(0, 180, 5, "min"),
            vol.Optional(C.CONF_DOOR_OPEN_TIMEOUT, default=d.get(C.CONF_DOOR_OPEN_TIMEOUT, C.DEFAULT_DOOR_OPEN_TIMEOUT)): _num(0, 30, 1, "min"),
        }
    )


def _schema_media(hass: HomeAssistant, d: dict, playlists: list[tuple[str, str]]) -> vol.Schema:
    schema: dict[Any, Any] = {}
    _add_entity(schema, C.CONF_MEDIA_PLAYER, d, domain="media_player")

    # Playlist: a dropdown of Music Assistant playlists (value = uri, label = name);
    # custom_value lets you still paste a media id if MA isn't reachable.
    opts = [selector.SelectOptionDict(value=uri, label=name) for name, uri in playlists]
    pl_cfg = selector.SelectSelectorConfig(
        options=opts, custom_value=True, sort=True, mode=selector.SelectSelectorMode.DROPDOWN,
    )
    existing_pl = d.get(C.CONF_DEFAULT_PLAYLIST)
    pl_marker = vol.Optional(C.CONF_DEFAULT_PLAYLIST, default=existing_pl) if existing_pl else vol.Optional(C.CONF_DEFAULT_PLAYLIST)
    schema[pl_marker] = selector.SelectSelector(pl_cfg)

    schema[vol.Optional(C.CONF_DEFAULT_VOLUME, default=d.get(C.CONF_DEFAULT_VOLUME, C.DEFAULT_VOLUME))] = _num(0, 1, 0.05)
    schema[
        vol.Required(C.CONF_MUSIC_START_MODE, default=d.get(C.CONF_MUSIC_START_MODE, C.MUSIC_START_ROUND))
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=C.MUSIC_START_MODES, translation_key="music_start_mode",
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )
    schema[vol.Optional(C.CONF_MUSIC_START_TEMP, default=d.get(C.CONF_MUSIC_START_TEMP, C.DEFAULT_MUSIC_START_TEMP))] = _num(30, 110, 1, "°C")
    return vol.Schema(schema)


def _schema_tracking(hass: HomeAssistant, d: dict) -> vol.Schema:
    schema: dict[Any, Any] = {}
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

    notify_services = sorted(f"notify.{n}" for n in hass.services.async_services().get("notify", {}))
    notify_cfg = selector.SelectSelectorConfig(
        options=notify_services, custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN,
    )
    existing_notify = d.get(C.CONF_NOTIFY_SERVICE)
    n_marker = vol.Optional(C.CONF_NOTIFY_SERVICE, default=existing_notify) if existing_notify else vol.Optional(C.CONF_NOTIFY_SERVICE)
    schema[n_marker] = selector.SelectSelector(notify_cfg)
    return vol.Schema(schema)


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    for key in (C.CONF_DEFAULT_PLAYLIST, C.CONF_NOTIFY_SERVICE):
        if not data.get(key):
            data.pop(key, None)
    return data


# ------------------------------------------------------------ shared steps
class _StepsMixin:
    """The 5-screen sequence, shared by the config and options flows."""

    _data: dict[str, Any]

    async def async_step_sauna(self, user_input=None):
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_power()
        return self.async_show_form(step_id="sauna", data_schema=_schema_sauna(self.hass, self._data), last_step=False)

    async def async_step_power(self, user_input=None):
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_session()
        return self.async_show_form(step_id="power", data_schema=_schema_power(self.hass, self._data), last_step=False)

    async def async_step_session(self, user_input=None):
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_media()
        return self.async_show_form(step_id="session", data_schema=_schema_session(self.hass, self._data), last_step=False)

    async def async_step_media(self, user_input=None):
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_tracking()
        playlists = await _ma_playlists(self.hass)
        return self.async_show_form(
            step_id="media", data_schema=_schema_media(self.hass, self._data, playlists), last_step=False
        )

    async def async_step_tracking(self, user_input=None):
        if user_input is not None:
            self._data.update(user_input)
            return await self._finish()
        return self.async_show_form(step_id="tracking", data_schema=_schema_tracking(self.hass, self._data), last_step=True)

    async def _finish(self):  # pragma: no cover - overridden
        raise NotImplementedError


class SchvitzConfigFlow(_StepsMixin, config_entries.ConfigFlow, domain=C.DOMAIN):
    """Initial setup — one config entry per sauna, across grouped screens."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input=None):
        return await self.async_step_sauna(user_input)

    async def _finish(self):
        name = self._data[C.CONF_NAME].strip()
        await self.async_set_unique_id(f"{C.DOMAIN}_{name.lower().replace(' ', '_')}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=name, data=_clean(dict(self._data)))

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "SchvitzOptionsFlow":
        return SchvitzOptionsFlow(config_entry)


class SchvitzOptionsFlow(_StepsMixin, config_entries.OptionsFlow):
    """Edit an existing sauna through the same grouped screens."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry
        self._data: dict[str, Any] = {**config_entry.data, **config_entry.options}

    async def async_step_init(self, user_input=None):
        return await self.async_step_sauna(user_input)

    async def _finish(self):
        return self.async_create_entry(title="", data=_clean(dict(self._data)))
