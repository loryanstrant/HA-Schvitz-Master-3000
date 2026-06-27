"""Buttons for Schvitz Master 3000 — the actions the ESPHome panel maps onto."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.components.button import ButtonEntity
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
            _Button(coord, "start", "Start session", "mdi:play",
                    lambda c: c.async_start_session()),
            _Button(coord, "stop", "Stop session", "mdi:stop",
                    lambda c: c.async_end_session(reason="button")),
            _Button(coord, "next_round", "Next round", "mdi:skip-next",
                    lambda c: c.async_next_round()),
            _Button(coord, "extend", "Extend +5 min", "mdi:plus",
                    lambda c: c.async_extend(5)),
            _Button(coord, "skip_warmup", "Skip warm-up", "mdi:fast-forward",
                    lambda c: c.async_skip_warmup()),
        ]
    )


class _Button(SchvitzBaseEntity, ButtonEntity):
    def __init__(
        self,
        coord: SchvitzCoordinator,
        key: str,
        name: str,
        icon: str,
        action: Callable[[SchvitzCoordinator], Awaitable[None]],
    ) -> None:
        super().__init__(coord, "button", key, name)
        self._attr_icon = icon
        self._action = action

    async def async_press(self) -> None:
        await self._action(self._coordinator)
