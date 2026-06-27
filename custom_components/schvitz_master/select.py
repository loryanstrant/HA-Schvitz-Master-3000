"""Selects for Schvitz Master 3000: media player, playlist, session profile."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import const as C
from .coordinator import SchvitzCoordinator
from .entity import SchvitzBaseEntity

_NONE = "None"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coord: SchvitzCoordinator = hass.data[C.DOMAIN][entry.entry_id]
    async_add_entities(
        [MediaPlayerSelect(coord), PlaylistSelect(coord), SessionProfileSelect(coord)]
    )


class _Base(SchvitzBaseEntity, SelectEntity):
    def __init__(self, coord, key, name):
        super().__init__(coord, "select", key, name)


class MediaPlayerSelect(_Base):
    _attr_icon = "mdi:speaker"

    def __init__(self, coord: SchvitzCoordinator) -> None:
        super().__init__(coord, "media_player", "Media player")

    @property
    def options(self) -> list[str]:
        players = sorted(self.hass.states.async_entity_ids("media_player"))
        cur = self._coordinator.selected_media_player
        if cur and cur not in players:
            players.insert(0, cur)
        return [_NONE, *players]

    @property
    def current_option(self) -> str:
        return self._coordinator.selected_media_player or _NONE

    async def async_select_option(self, option: str) -> None:
        await self._coordinator.async_set_media_player(None if option == _NONE else option)


class PlaylistSelect(_Base):
    """Playlist picker, populated best-effort from Music Assistant."""

    _attr_icon = "mdi:playlist-music"

    def __init__(self, coord: SchvitzCoordinator) -> None:
        super().__init__(coord, "playlist", "Playlist")

    @property
    def options(self) -> list[str]:
        labels = sorted(self._coordinator.playlist_map.keys())
        return [_NONE, *labels]

    @property
    def current_option(self) -> str:
        cur = self._coordinator.selected_playlist
        if not cur:
            return _NONE
        for label, uri in self._coordinator.playlist_map.items():
            if uri == cur:
                return label
        # Selected URI isn't in the (possibly empty) MA map — show it verbatim.
        return cur

    async def async_select_option(self, option: str) -> None:
        if option == _NONE:
            await self._coordinator.async_set_playlist(None)
        else:
            uri = self._coordinator.playlist_map.get(option, option)
            await self._coordinator.async_set_playlist(uri)


class SessionProfileSelect(_Base):
    _attr_icon = "mdi:tune-vertical"

    def __init__(self, coord: SchvitzCoordinator) -> None:
        super().__init__(coord, "session_profile", "Session profile")

    @property
    def options(self) -> list[str]:
        return [C.PROFILE_NONE, *C.SESSION_PROFILES.keys()]

    @property
    def current_option(self) -> str:
        return self._coordinator.selected_profile

    async def async_select_option(self, option: str) -> None:
        await self._coordinator.async_apply_profile(option)
