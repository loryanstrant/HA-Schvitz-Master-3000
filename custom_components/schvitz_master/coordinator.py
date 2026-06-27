"""Coordinator that runs the sauna session state machine for one sauna.

Mirrors the ownership/persistence/dispatch pattern of Personal Hydration Manager's
``HydrationCoordinator`` but, instead of passively tracking one number, it runs an
active state machine and orchestrates real devices:

    idle → warmup → in_round → break → … → ending → idle

- Round/break countdowns use ``async_track_point_in_time`` for precise auto-advance,
  plus a 1 s ``async_track_time_interval`` (only while active) to keep the
  ``time_remaining`` sensor fresh for the card/panel countdown.
- Optional water + heart-rate source sensors are tracked per session with the same
  guarded handler PHM uses (ignore unknown/unavailable, unit-convert, delta/absolute).
- Everything persists to a ``Store`` so a restart mid-session resumes (or records).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import const as C

_LOGGER = logging.getLogger(__name__)

_UNAVAILABLE = ("unknown", "unavailable", "none", "", None)


def _to_ml(value: float, unit: str | None) -> float:
    """Best-effort convert a source-sensor reading to millilitres."""
    u = (unit or "").lower()
    if u in ("l", "liter", "liters", "litre", "litres"):
        return value * 1000.0
    if u in ("fl_oz", "floz", "oz", "fl oz"):
        return value * 29.5735
    return value


class SchvitzCoordinator:
    """Owns the session state, timers, persistence and orchestration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.entry_id = entry.entry_id
        self._store = Store(
            hass, C.STORAGE_VERSION, C.STORAGE_KEY_FMT.format(entry_id=entry.entry_id)
        )

        # Unsub handles.
        self._unsub_phase = None          # round/break/warmup-safety point-in-time
        self._unsub_tick = None           # 1 s display refresh while active
        self._unsub_sources: list = []    # water/hr/temp state-change listeners
        self._unsub_post_off = None       # scheduled post-switch turn-off

        cfg = {**entry.data, **entry.options}

        # --- Durable wiring ---------------------------------------------------
        self.name: str = cfg.get(C.CONF_NAME, "Sauna")
        self.slug: str = self.name.lower().replace(" ", "_")
        self.temp_sensor: str | None = cfg.get(C.CONF_TEMP_SENSOR) or None
        self.seat_temp_sensor: str | None = cfg.get(C.CONF_SEAT_TEMP_SENSOR) or None
        self.door_sensor: str | None = cfg.get(C.CONF_DOOR_SENSOR) or None
        self.vent_sensor: str | None = cfg.get(C.CONF_VENT_SENSOR) or None
        self.heater_switch: str | None = cfg.get(C.CONF_HEATER_SWITCH) or None
        self.plug_switch: str | None = cfg.get(C.CONF_PLUG_SWITCH) or None
        self.pre_switches: list[str] = list(cfg.get(C.CONF_PRE_SWITCHES) or [])
        self.post_switches: list[str] = list(cfg.get(C.CONF_POST_SWITCHES) or [])
        self.media_player_cfg: str | None = cfg.get(C.CONF_MEDIA_PLAYER) or None
        self.default_playlist: str | None = cfg.get(C.CONF_DEFAULT_PLAYLIST) or None
        self.default_volume: float = float(cfg.get(C.CONF_DEFAULT_VOLUME, C.DEFAULT_VOLUME))
        self.water_sensor: str | None = cfg.get(C.CONF_WATER_SENSOR) or None
        self.water_source_mode: str = cfg.get(C.CONF_WATER_SOURCE_MODE, C.SOURCE_MODE_DELTA)
        self.hr_sensor: str | None = cfg.get(C.CONF_HR_SENSOR) or None
        self.notify_service: str | None = cfg.get(C.CONF_NOTIFY_SERVICE) or None

        # --- Per-session knobs (runtime entities; persisted) ------------------
        self.round_count: int = int(cfg.get(C.CONF_DEFAULT_ROUNDS, C.DEFAULT_ROUNDS))
        self.round_duration_min: int = int(cfg.get(C.CONF_DEFAULT_ROUND_MIN, C.DEFAULT_ROUND_MIN))
        self.break_duration_min: int = int(cfg.get(C.CONF_DEFAULT_BREAK_MIN, C.DEFAULT_BREAK_MIN))
        self.warmup_target_temp: float = float(
            cfg.get(C.CONF_WARMUP_TARGET_TEMP, C.DEFAULT_WARMUP_TARGET_TEMP)
        )
        self.warmup_wait_enabled: bool = True
        self.selected_media_player: str | None = self.media_player_cfg
        self.selected_playlist: str | None = self.default_playlist
        self.selected_volume: float = self.default_volume
        self.selected_profile: str = C.PROFILE_NONE
        self.music_start_mode: str = cfg.get(C.CONF_MUSIC_START_MODE, C.MUSIC_START_ROUND)
        self.music_start_temp: float = float(
            cfg.get(C.CONF_MUSIC_START_TEMP, C.DEFAULT_MUSIC_START_TEMP)
        )

        # --- Live session state ----------------------------------------------
        self.state: str = C.STATE_IDLE
        self.current_round: int = 0
        self.started_at: str | None = None
        self.phase_ends_at: datetime | None = None

        # --- Per-session accumulators ----------------------------------------
        self.session_water_ml: float = 0.0
        self._water_baseline: float | None = None
        self._last_water_value: float | None = None
        self.hr_sum: float = 0.0
        self.hr_count: int = 0
        self.hr_max: float | None = None
        self.peak_temp: float | None = None

        self.history: list[dict[str, Any]] = []
        # Backing value for the "last session water" charted sensor.
        self.last_session_water_ml: float | None = None
        self._post_off_at: str | None = None
        # Whether this session's media has been started yet (so the temp trigger
        # and the round-1 fallback don't double up).
        self._music_started: bool = False

        # label -> media_id, best-effort from Music Assistant for the playlist select.
        self.playlist_map: dict[str, str] = {}

    # ------------------------------------------------------------------ utils
    @property
    def signal(self) -> str:
        return C.SIGNAL_UPDATE_FMT.format(entry_id=self.entry_id)

    @property
    def is_active(self) -> bool:
        return self.state in C.ACTIVE_STATES

    @property
    def time_remaining(self) -> int | None:
        """Seconds left in the current timed phase, else None."""
        if self.phase_ends_at is None or self.state not in (C.STATE_IN_ROUND, C.STATE_BREAK):
            return None
        delta = (self.phase_ends_at - dt_util.utcnow()).total_seconds()
        return max(0, int(round(delta)))

    @property
    def avg_heart_rate(self) -> float | None:
        if not self.hr_count:
            return None
        return round(self.hr_sum / self.hr_count, 0)

    def _read_float(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        st = self.hass.states.get(entity_id)
        if st is None or str(st.state).lower() in _UNAVAILABLE:
            return None
        try:
            return float(st.state)
        except (TypeError, ValueError):
            return None

    def _start_switches(self) -> list[str]:
        out = []
        for e in (self.heater_switch, self.plug_switch, *self.pre_switches):
            if e and e not in out:
                out.append(e)
        return out

    # ------------------------------------------------------------- lifecycle
    async def async_initialize(self) -> None:
        """Load persisted state and resume/record any in-flight session."""
        stored = await self._store.async_load()
        if stored:
            self._restore(stored)

        await self.async_refresh_playlists()

        if self.is_active:
            self._attach_listeners()
            self._start_tick()
            await self._resume_after_restart()

        self._dispatch()

    async def async_shutdown(self) -> None:
        self._cancel_phase()
        self._stop_tick()
        self._detach_listeners()
        if self._unsub_post_off:
            self._unsub_post_off()
            self._unsub_post_off = None
        await self._save()

    def _restore(self, s: dict[str, Any]) -> None:
        self.round_count = int(s.get("round_count", self.round_count))
        self.round_duration_min = int(s.get("round_duration_min", self.round_duration_min))
        self.break_duration_min = int(s.get("break_duration_min", self.break_duration_min))
        self.warmup_target_temp = float(s.get("warmup_target_temp", self.warmup_target_temp))
        self.warmup_wait_enabled = bool(s.get("warmup_wait_enabled", self.warmup_wait_enabled))
        self.selected_media_player = s.get("selected_media_player", self.selected_media_player)
        self.selected_playlist = s.get("selected_playlist", self.selected_playlist)
        self.selected_volume = float(s.get("selected_volume", self.selected_volume))
        self.selected_profile = s.get("selected_profile", self.selected_profile)
        self.state = s.get("state", C.STATE_IDLE)
        self.current_round = int(s.get("current_round", 0))
        self.started_at = s.get("started_at")
        ends = s.get("phase_ends_at")
        self.phase_ends_at = dt_util.parse_datetime(ends) if ends else None
        self.session_water_ml = float(s.get("session_water_ml", 0.0))
        self._water_baseline = s.get("water_baseline")
        self._last_water_value = s.get("last_water_value")
        self.hr_sum = float(s.get("hr_sum", 0.0))
        self.hr_count = int(s.get("hr_count", 0))
        self.hr_max = s.get("hr_max")
        self.peak_temp = s.get("peak_temp")
        self.history = list(s.get("history", []))
        self.last_session_water_ml = s.get("last_session_water_ml")
        self._post_off_at = s.get("post_off_at")
        self._music_started = bool(s.get("music_started", False))

    async def _resume_after_restart(self) -> None:
        """Advance the state machine to account for time spent while HA was down."""
        now = dt_util.utcnow()
        if self.state in (C.STATE_IN_ROUND, C.STATE_BREAK):
            if self.phase_ends_at and now >= self.phase_ends_at:
                await self._on_phase_elapsed(now)
            elif self.phase_ends_at:
                self._unsub_phase = async_track_point_in_time(
                    self.hass, self._on_phase_elapsed, self.phase_ends_at
                )
        elif self.state == C.STATE_WARMUP:
            # Re-arm the safety timeout (or begin immediately if already hot).
            await self._check_warmup()
            if self.state == C.STATE_WARMUP:
                self._unsub_phase = async_track_point_in_time(
                    self.hass,
                    self._on_phase_elapsed,
                    now + timedelta(minutes=C.WARMUP_TIMEOUT_MIN),
                )
        elif self.state == C.STATE_ENDING:
            await self.async_end_session(reason="restart")

    # --------------------------------------------------------------- timers
    def _cancel_phase(self) -> None:
        if self._unsub_phase:
            self._unsub_phase()
            self._unsub_phase = None
        self.phase_ends_at = None

    def _schedule_phase_end(self, seconds: int) -> None:
        self._cancel_phase()
        self.phase_ends_at = dt_util.utcnow() + timedelta(seconds=seconds)
        self._unsub_phase = async_track_point_in_time(
            self.hass, self._on_phase_elapsed, self.phase_ends_at
        )

    def _start_tick(self) -> None:
        if self._unsub_tick is None:
            self._unsub_tick = async_track_time_interval(
                self.hass, self._tick, timedelta(seconds=1)
            )

    def _stop_tick(self) -> None:
        if self._unsub_tick:
            self._unsub_tick()
            self._unsub_tick = None

    @callback
    def _tick(self, _now: datetime) -> None:
        self._dispatch()

    async def _on_phase_elapsed(self, _now: datetime) -> None:
        """A scheduled phase boundary was reached."""
        self._unsub_phase = None
        if self.state == C.STATE_WARMUP:
            await self._begin_round()
        elif self.state == C.STATE_IN_ROUND:
            if self.current_round >= self.round_count:
                await self.async_end_session(reason="completed")
            else:
                await self._begin_break()
        elif self.state == C.STATE_BREAK:
            await self._begin_round()

    # ------------------------------------------------------- source tracking
    def _attach_listeners(self) -> None:
        self._detach_listeners()
        if self.water_sensor:
            self._unsub_sources.append(
                async_track_state_change_event(
                    self.hass, [self.water_sensor], self._handle_water
                )
            )
        if self.hr_sensor:
            self._unsub_sources.append(
                async_track_state_change_event(
                    self.hass, [self.hr_sensor], self._handle_hr
                )
            )
        if self.temp_sensor:
            self._unsub_sources.append(
                async_track_state_change_event(
                    self.hass, [self.temp_sensor], self._handle_temp
                )
            )

    def _detach_listeners(self) -> None:
        for unsub in self._unsub_sources:
            unsub()
        self._unsub_sources = []

    async def _handle_water(self, event) -> None:
        new = event.data.get("new_state")
        if new is None or str(new.state).lower() in _UNAVAILABLE:
            return
        try:
            value = float(new.state)
        except (TypeError, ValueError):
            return
        value = _to_ml(value, new.attributes.get("unit_of_measurement"))
        if self.water_source_mode == C.SOURCE_MODE_ABSOLUTE:
            base = self._water_baseline if self._water_baseline is not None else value
            self.session_water_ml = max(0.0, value - base)
        else:  # delta — sum positive increases
            if self._last_water_value is not None and value >= self._last_water_value:
                self.session_water_ml += value - self._last_water_value
            self._last_water_value = value
        await self._commit()

    async def _handle_hr(self, event) -> None:
        new = event.data.get("new_state")
        if new is None or str(new.state).lower() in _UNAVAILABLE:
            return
        try:
            value = float(new.state)
        except (TypeError, ValueError):
            return
        self.hr_sum += value
        self.hr_count += 1
        self.hr_max = value if self.hr_max is None else max(self.hr_max, value)
        await self._commit()

    async def _handle_temp(self, event) -> None:
        new = event.data.get("new_state")
        if new is None or str(new.state).lower() in _UNAVAILABLE:
            return
        try:
            value = float(new.state)
        except (TypeError, ValueError):
            return
        self.peak_temp = value if self.peak_temp is None else max(self.peak_temp, value)
        # Temp-triggered music: start the playlist the first time the sauna is
        # hot enough (e.g. while still warming up), rather than at round 1.
        if (
            self.music_start_mode == C.MUSIC_START_TEMP
            and not self._music_started
            and self.is_active
            and value >= self.music_start_temp
        ):
            await self._play_media()
            self._music_started = True
        if self.state == C.STATE_WARMUP:
            await self._check_warmup()
        else:
            await self._commit()

    async def _check_warmup(self) -> None:
        if self.state != C.STATE_WARMUP:
            return
        t = self._read_float(self.temp_sensor)
        if t is not None and t >= self.warmup_target_temp:
            await self._begin_round()

    # --------------------------------------------------------- orchestration
    async def _turn_on(self, entities: list[str]) -> None:
        for entity_id in entities:
            await self.hass.services.async_call(
                "homeassistant", "turn_on", {"entity_id": entity_id}, blocking=False
            )

    async def _turn_off(self, entities: list[str]) -> None:
        for entity_id in entities:
            await self.hass.services.async_call(
                "homeassistant", "turn_off", {"entity_id": entity_id}, blocking=False
            )

    async def _play_media(self) -> None:
        player = self.selected_media_player
        playlist = self.selected_playlist
        if not player or not playlist:
            return
        try:
            if self.hass.services.has_service("music_assistant", "play_media"):
                await self.hass.services.async_call(
                    "music_assistant",
                    "play_media",
                    {
                        "entity_id": player,
                        "media_id": playlist,
                        "media_type": "playlist",
                    },
                    blocking=False,
                )
            else:
                await self.hass.services.async_call(
                    "media_player",
                    "play_media",
                    {
                        "entity_id": player,
                        "media_content_id": playlist,
                        "media_content_type": "playlist",
                    },
                    blocking=False,
                )
            if self.selected_volume is not None:
                await self.hass.services.async_call(
                    "media_player",
                    "volume_set",
                    {"entity_id": player, "volume_level": self.selected_volume},
                    blocking=False,
                )
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.warning("Could not start media on %s: %s", player, err)

    async def _pause_media(self) -> None:
        if self.selected_media_player:
            await self.hass.services.async_call(
                "media_player",
                "media_pause",
                {"entity_id": self.selected_media_player},
                blocking=False,
            )

    async def _stop_media(self) -> None:
        if self.selected_media_player:
            await self.hass.services.async_call(
                "media_player",
                "media_stop",
                {"entity_id": self.selected_media_player},
                blocking=False,
            )

    def _notify(self, title: str, message: str) -> None:
        if not self.notify_service:
            return
        service = self.notify_service
        domain, _, name = service.partition(".")
        if not name:
            domain, name = "notify", service
        self.hass.async_create_task(
            self.hass.services.async_call(
                domain, name, {"title": title, "message": message}, blocking=False
            )
        )

    def _fire(self, event_type: str, extra: dict | None = None) -> None:
        data = {
            "entry_id": self.entry_id,
            "slug": self.slug,
            "name": self.name,
            "state": self.state,
            "round": self.current_round,
            "total_rounds": self.round_count,
        }
        if extra:
            data.update(extra)
        self.hass.bus.async_fire(event_type, data)

    # ------------------------------------------------------------ transitions
    def _reset_accumulators(self) -> None:
        self.session_water_ml = 0.0
        self._water_baseline = self._read_float(self.water_sensor)
        self._last_water_value = self._water_baseline
        self.hr_sum = 0.0
        self.hr_count = 0
        self.hr_max = None
        self.peak_temp = self._read_float(self.temp_sensor)
        self._music_started = False

    async def async_start_session(
        self,
        rounds: int | None = None,
        round_minutes: int | None = None,
        break_minutes: int | None = None,
        media_player: str | None = None,
        playlist: str | None = None,
    ) -> None:
        if self.state != C.STATE_IDLE:
            _LOGGER.debug("start_session ignored — already in state %s", self.state)
            return
        if rounds is not None:
            self.round_count = int(rounds)
        if round_minutes is not None:
            self.round_duration_min = int(round_minutes)
        if break_minutes is not None:
            self.break_duration_min = int(break_minutes)
        if media_player is not None:
            self.selected_media_player = media_player
        if playlist is not None:
            self.selected_playlist = playlist

        self.started_at = dt_util.utcnow().isoformat()
        self.current_round = 0
        self._reset_accumulators()

        await self._turn_on(self._start_switches())
        self._attach_listeners()
        self._start_tick()
        self._fire(C.EVENT_SESSION_STARTED)

        if self.warmup_wait_enabled and self.temp_sensor:
            self.state = C.STATE_WARMUP
            self._notify(f"{self.name}", "Heating up…")
            # Safety timeout so we never wait forever for a missing/cold sensor.
            self._unsub_phase = async_track_point_in_time(
                self.hass,
                self._on_phase_elapsed,
                dt_util.utcnow() + timedelta(minutes=C.WARMUP_TIMEOUT_MIN),
            )
            await self._check_warmup()
        else:
            await self._begin_round()
        await self._commit()

    async def _begin_round(self) -> None:
        self._cancel_phase()
        self.current_round += 1
        self.state = C.STATE_IN_ROUND
        self._schedule_phase_end(self.round_duration_min * 60)
        # Start media now unless the temp trigger already did (or will): in
        # "round" mode this always plays at round 1; in "temp" mode it's the
        # fallback if the sauna never reached the music-start temp.
        if not self._music_started:
            await self._play_media()
            self._music_started = True
        self._fire(C.EVENT_ROUND_STARTED)
        self._notify(
            f"{self.name} — round {self.current_round}/{self.round_count}",
            f"{self.round_duration_min} min. Enjoy the schvitz.",
        )
        await self._commit()

    async def _begin_break(self) -> None:
        self._cancel_phase()
        self.state = C.STATE_BREAK
        self._schedule_phase_end(self.break_duration_min * 60)
        await self._pause_media()
        self._fire(C.EVENT_ROUND_ENDED)
        self._fire(C.EVENT_BREAK_STARTED)
        self._notify(
            f"{self.name} — break",
            f"Round {self.current_round} of {self.round_count} done. "
            f"{self.break_duration_min} min break.",
        )
        await self._commit()

    async def async_end_session(self, reason: str = "manual") -> None:
        if self.state == C.STATE_IDLE:
            return
        self.state = C.STATE_ENDING
        self._cancel_phase()
        self._stop_tick()
        self._detach_listeners()

        record = {
            "ended_at": dt_util.utcnow().isoformat(),
            "started_at": self.started_at,
            "rounds": self.current_round,
            "round_minutes": self.round_duration_min,
            "break_minutes": self.break_duration_min,
            "water_ml": round(self.session_water_ml, 1) if self.water_sensor else None,
            "avg_hr": self.avg_heart_rate,
            "max_hr": self.hr_max,
            "peak_temp": self.peak_temp,
            "reason": reason,
        }
        self.history.insert(0, record)
        del self.history[C.HISTORY_MAX :]
        self.last_session_water_ml = record["water_ml"]

        await self._stop_media()
        await self._turn_off(self._start_switches())
        if self.post_switches:
            await self._turn_on(self.post_switches)

        self._fire(C.EVENT_SESSION_ENDED, {"summary": record})
        self._notify(
            f"{self.name} — session complete",
            f"{self.current_round} round(s)"
            + (f", {record['water_ml']:.0f} mL water" if record["water_ml"] else "")
            + ".",
        )

        # Reset to idle.
        self.state = C.STATE_IDLE
        self.current_round = 0
        self.started_at = None
        self.phase_ends_at = None
        await self._commit()

    async def async_next_round(self) -> None:
        """Advance manually: end the current phase boundary early."""
        if self.state == C.STATE_IN_ROUND:
            if self.current_round >= self.round_count:
                await self.async_end_session(reason="manual_next")
            else:
                await self._begin_break()
        elif self.state in (C.STATE_BREAK, C.STATE_WARMUP):
            await self._begin_round()

    async def async_extend(self, minutes: int = 5) -> None:
        if self.state in (C.STATE_IN_ROUND, C.STATE_BREAK) and self.phase_ends_at:
            remaining = max(0, (self.phase_ends_at - dt_util.utcnow()).total_seconds())
            self._schedule_phase_end(int(remaining + minutes * 60))
            await self._commit()

    async def async_skip_warmup(self) -> None:
        if self.state == C.STATE_WARMUP:
            await self._begin_round()

    async def async_set_rounds(self, rounds: int) -> None:
        self.round_count = max(1, int(rounds))
        await self._commit()

    async def async_log_water(self, volume: float, unit: str = C.UNIT_ML) -> None:
        self.session_water_ml = max(0.0, self.session_water_ml + C.to_ml(float(volume), unit))
        await self._commit()

    async def async_apply_profile(self, profile: str) -> None:
        preset = C.SESSION_PROFILES.get(profile)
        self.selected_profile = profile
        if preset:
            self.round_count = preset["rounds"]
            self.round_duration_min = preset["round_min"]
            self.break_duration_min = preset["break_min"]
        await self._commit()

    # ---- number/select/switch setters (called by platform entities) --------
    async def async_set_round_count(self, value: int) -> None:
        self.round_count = max(1, int(value))
        await self._commit()

    async def async_set_round_duration(self, value: int) -> None:
        self.round_duration_min = max(1, int(value))
        await self._commit()

    async def async_set_break_duration(self, value: int) -> None:
        self.break_duration_min = max(1, int(value))
        await self._commit()

    async def async_set_warmup_target(self, value: float) -> None:
        self.warmup_target_temp = float(value)
        await self._commit()

    async def async_set_warmup_wait(self, enabled: bool) -> None:
        self.warmup_wait_enabled = bool(enabled)
        await self._commit()

    async def async_set_media_player(self, value: str | None) -> None:
        self.selected_media_player = value
        await self._commit()

    async def async_set_playlist(self, value: str | None) -> None:
        self.selected_playlist = value
        await self._commit()

    async def async_refresh_playlists(self) -> None:
        """Best-effort: populate ``playlist_map`` (label -> media_id) from Music
        Assistant. Any failure leaves the map empty — the integration still works
        with the configured default playlist and the start_session override.
        """
        try:
            entries = self.hass.config_entries.async_entries("music_assistant")
            mass = None
            for entry in entries:
                mass = getattr(entry, "runtime_data", None) or mass
            if mass is None:
                return
            playlists = await mass.music.get_library_playlists()
            self.playlist_map = {
                p.name: p.uri for p in playlists if getattr(p, "uri", None)
            }
        except Exception as err:  # pragma: no cover - MA internals are version-fragile
            _LOGGER.debug("Could not enumerate Music Assistant playlists: %s", err)

    # ------------------------------------------------------------ persistence
    async def _save(self) -> None:
        await self._store.async_save(
            {
                "round_count": self.round_count,
                "round_duration_min": self.round_duration_min,
                "break_duration_min": self.break_duration_min,
                "warmup_target_temp": self.warmup_target_temp,
                "warmup_wait_enabled": self.warmup_wait_enabled,
                "selected_media_player": self.selected_media_player,
                "selected_playlist": self.selected_playlist,
                "selected_volume": self.selected_volume,
                "selected_profile": self.selected_profile,
                "state": self.state,
                "current_round": self.current_round,
                "started_at": self.started_at,
                "phase_ends_at": self.phase_ends_at.isoformat() if self.phase_ends_at else None,
                "session_water_ml": self.session_water_ml,
                "water_baseline": self._water_baseline,
                "last_water_value": self._last_water_value,
                "hr_sum": self.hr_sum,
                "hr_count": self.hr_count,
                "hr_max": self.hr_max,
                "peak_temp": self.peak_temp,
                "history": self.history,
                "last_session_water_ml": self.last_session_water_ml,
                "post_off_at": self._post_off_at,
                "music_started": self._music_started,
            }
        )

    @callback
    def _dispatch(self) -> None:
        async_dispatcher_send(self.hass, self.signal)

    async def _commit(self) -> None:
        await self._save()
        self._dispatch()
