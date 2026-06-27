"""Switch for Schvitz Master 3000: the per-session warm-up-wait toggle."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import const as C
from .coordinator import SchvitzCoordinator
from .entity import SchvitzBaseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coord: SchvitzCoordinator = hass.data[C.DOMAIN][entry.entry_id]
    async_add_entities([WarmupWaitSwitch(coord)])


class WarmupWaitSwitch(SchvitzBaseEntity, SwitchEntity):
    """When on, a session waits for the sauna to reach the target temp before
    starting round 1 (monitor only — HA cannot control the thermostat)."""

    _attr_icon = "mdi:thermometer-check"

    def __init__(self, coord: SchvitzCoordinator) -> None:
        super().__init__(coord, "switch", "warmup_wait", "Warm-up wait")

    @property
    def is_on(self) -> bool:
        return self._coordinator.warmup_wait_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._coordinator.async_set_warmup_wait(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._coordinator.async_set_warmup_wait(False)
