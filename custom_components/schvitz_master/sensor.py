"""Sensors for Schvitz Master 3000."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
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
            SessionStateSensor(coord),
            CurrentRoundSensor(coord),
            TimeRemainingSensor(coord),
            SessionWaterSensor(coord),
            AvgHeartRateSensor(coord),
            MaxHeartRateSensor(coord),
            PeakTempSensor(coord),
            LastSessionWaterSensor(coord),
        ]
    )


class _Base(SchvitzBaseEntity, SensorEntity):
    def __init__(self, coord, key, name):
        super().__init__(coord, "sensor", key, name)


class SessionStateSensor(_Base):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = C.SESSION_STATES
    _attr_icon = "mdi:state-machine"

    def __init__(self, coord):
        super().__init__(coord, "session_state", "Session state")

    @property
    def native_value(self) -> str:
        return self._coordinator.state

    @property
    def extra_state_attributes(self) -> dict:
        c = self._coordinator
        return {
            "started_at": c.started_at,
            "current_round": c.current_round,
            "total_rounds": c.round_count,
            "phase_ends_at": c.phase_ends_at.isoformat() if c.phase_ends_at else None,
        }


class CurrentRoundSensor(_Base):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:counter"

    def __init__(self, coord):
        super().__init__(coord, "current_round", "Current round")

    @property
    def native_value(self) -> int:
        return self._coordinator.current_round

    @property
    def extra_state_attributes(self) -> dict:
        return {"total_rounds": self._coordinator.round_count}


class TimeRemainingSensor(_Base):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coord):
        super().__init__(coord, "time_remaining", "Time remaining")

    @property
    def native_value(self) -> int | None:
        return self._coordinator.time_remaining


class SessionWaterSensor(_Base):
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "mL"
    _attr_device_class = SensorDeviceClass.WATER
    _attr_icon = "mdi:cup-water"

    def __init__(self, coord):
        super().__init__(coord, "session_water", "Session water")

    @property
    def native_value(self) -> float | None:
        # Show the figure when a water sensor is wired OR water was logged
        # manually; otherwise stay unknown (graceful absence).
        if not self._coordinator.water_sensor and not self._coordinator.session_water_ml:
            return None
        return round(self._coordinator.session_water_ml, 1)


class AvgHeartRateSensor(_Base):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "bpm"
    _attr_icon = "mdi:heart-pulse"

    def __init__(self, coord):
        super().__init__(coord, "avg_heart_rate", "Average heart rate")

    @property
    def native_value(self) -> float | None:
        if not self._coordinator.hr_sensor:
            return None
        return self._coordinator.avg_heart_rate


class MaxHeartRateSensor(_Base):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "bpm"
    _attr_icon = "mdi:heart-flash"

    def __init__(self, coord):
        super().__init__(coord, "max_heart_rate", "Max heart rate")

    @property
    def native_value(self) -> float | None:
        if not self._coordinator.hr_sensor:
            return None
        return self._coordinator.hr_max


class PeakTempSensor(_Base):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer-high"

    def __init__(self, coord):
        super().__init__(coord, "peak_temp", "Peak temperature")

    @property
    def native_value(self) -> float | None:
        return self._coordinator.peak_temp


class LastSessionWaterSensor(_Base):
    """One value per completed session — gives a per-session history chart."""

    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "mL"
    _attr_device_class = SensorDeviceClass.WATER
    _attr_icon = "mdi:history"

    def __init__(self, coord):
        super().__init__(coord, "last_session_water", "Last session water")

    @property
    def native_value(self) -> float | None:
        return self._coordinator.last_session_water_ml

    @property
    def extra_state_attributes(self) -> dict:
        # Return a fresh copy each read. The coordinator mutates its history
        # list in place (insert), so handing HA the live reference would alias
        # the previously-stored State and defeat change detection.
        return {"history": [dict(h) for h in self._coordinator.history]}
