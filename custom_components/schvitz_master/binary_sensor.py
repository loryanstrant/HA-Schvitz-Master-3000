"""Binary sensors for Schvitz Master 3000."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    async_add_entities(
        [
            SessionActiveBinarySensor(coord),
            HeatingBinarySensor(coord),
            _StateBinarySensor(coord, "in_round", "In round", {C.STATE_IN_ROUND},
                               BinarySensorDeviceClass.RUNNING),
            _StateBinarySensor(coord, "break_active", "Break", {C.STATE_BREAK}, None),
        ]
    )


class _Base(SchvitzBaseEntity, BinarySensorEntity):
    def __init__(self, coord, key, name):
        super().__init__(coord, "binary_sensor", key, name)


class SessionActiveBinarySensor(_Base):
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:radiator"

    def __init__(self, coord: SchvitzCoordinator) -> None:
        super().__init__(coord, "session_active", "Session active")

    @property
    def is_on(self) -> bool:
        return self._coordinator.is_active

    @property
    def extra_state_attributes(self) -> dict:
        c = self._coordinator
        return {
            "state": c.state,
            "started_at": c.started_at,
            "round": c.current_round,
            "total_rounds": c.round_count,
        }


class HeatingBinarySensor(_Base):
    """Real 'element is heating', derived from the plug power / operation sensor."""

    _attr_device_class = BinarySensorDeviceClass.HEAT
    _attr_icon = "mdi:radiator"

    def __init__(self, coord: SchvitzCoordinator) -> None:
        super().__init__(coord, "heating", "Heating")

    @property
    def is_on(self) -> bool:
        return self._coordinator.is_heating


class _StateBinarySensor(_Base):
    """On when the session is in one of the given states."""

    def __init__(self, coord, key, name, states, device_class):
        super().__init__(coord, key, name)
        self._states = states
        self._attr_device_class = device_class

    @property
    def is_on(self) -> bool:
        return self._coordinator.state in self._states
