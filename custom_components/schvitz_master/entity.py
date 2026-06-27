"""Shared base entity wiring for Schvitz Master 3000 platforms."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .coordinator import SchvitzCoordinator

# Inlined (not imported from const) for partial-update resilience, mirroring PHM.
ENTITY_ID_PREFIX = "schvitz"
DOMAIN = "schvitz_master"


class SchvitzBaseEntity(Entity):
    """Common base — pins entity_id, shares the device, wires dispatcher updates."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: SchvitzCoordinator, platform: str, key: str, name: str
    ) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry_id}_{key}"
        self._attr_name = name
        self.entity_id = f"{platform}.{ENTITY_ID_PREFIX}_{coordinator.slug}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            name=coordinator.name,
            manufacturer="Loryan Strant",
            model="Schvitz Master 3000",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._coordinator.signal, self._refresh)
        )

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()
