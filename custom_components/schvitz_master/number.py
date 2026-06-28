"""Per-session number knobs for Schvitz Master 3000."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import const as C
from .coordinator import SchvitzCoordinator
from .entity import SchvitzBaseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coord: SchvitzCoordinator = hass.data[C.DOMAIN][entry.entry_id]
    async_add_entities(
        [
            _Knob(coord, "round_count", "Round count", 1, 6, 1, None, "mdi:counter",
                  lambda c: c.round_count, lambda c, v: c.async_set_round_count(v)),
            _Knob(coord, "round_duration", "Round duration", 3, 30, 1, "min", "mdi:timer",
                  lambda c: c.round_duration_min, lambda c, v: c.async_set_round_duration(v)),
            _Knob(coord, "break_duration", "Break duration", 0, 30, 1, "min", "mdi:timer-pause",
                  lambda c: c.break_duration_min, lambda c, v: c.async_set_break_duration(v)),
            _Knob(coord, "ready_temp", "Ready temperature", 40, 110, 1,
                  UnitOfTemperature.CELSIUS, "mdi:thermometer-chevron-up",
                  lambda c: c.ready_target_temp, lambda c, v: c.async_set_ready_temp(v)),
        ]
    )


class _Knob(SchvitzBaseEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coord: SchvitzCoordinator,
        key: str,
        name: str,
        min_v: float,
        max_v: float,
        step: float,
        unit: str | None,
        icon: str,
        getter: Callable[[SchvitzCoordinator], float],
        setter: Callable[[SchvitzCoordinator, float], Awaitable[None]],
    ) -> None:
        super().__init__(coord, "number", key, name)
        self._attr_native_min_value = min_v
        self._attr_native_max_value = max_v
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._getter = getter
        self._setter = setter

    @property
    def native_value(self) -> float:
        return self._getter(self._coordinator)

    async def async_set_native_value(self, value: float) -> None:
        await self._setter(self._coordinator, value)
