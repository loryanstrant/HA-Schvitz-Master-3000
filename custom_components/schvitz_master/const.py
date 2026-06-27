"""Constants for Schvitz Master 5000.

One config-flow custom integration that owns a sauna *session* end-to-end:
warm-up → rounds (the times you sit) → breaks → end, with full orchestration of
switches, media (Music Assistant), and per-session sensor tracking.
"""
from __future__ import annotations

DOMAIN = "schvitz_master"
PLATFORMS = ["binary_sensor", "sensor", "number", "select", "button", "switch"]

# Short prefix for entity IDs (e.g. sensor.schvitz_sauna_session_state).
# Keeps the integration's entities grouped and easy to filter.
ENTITY_ID_PREFIX = "schvitz"

# --- Config keys (durable wiring; per-session knobs are runtime entities) -----
CONF_NAME = "name"
CONF_TEMP_SENSOR = "temp_sensor"
CONF_SEAT_TEMP_SENSOR = "seat_temp_sensor"
CONF_DOOR_SENSOR = "door_sensor"
CONF_VENT_SENSOR = "vent_sensor"
CONF_HEATER_SWITCH = "heater_switch"
CONF_PLUG_SWITCH = "plug_switch"
CONF_PRE_SWITCHES = "pre_switches"
CONF_POST_SWITCHES = "post_switches"
CONF_MEDIA_PLAYER = "media_player"
CONF_DEFAULT_PLAYLIST = "default_playlist"
CONF_DEFAULT_VOLUME = "default_volume"
CONF_WATER_SENSOR = "water_sensor"
CONF_WATER_SOURCE_MODE = "water_source_mode"
CONF_HR_SENSOR = "hr_sensor"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_DEFAULT_ROUNDS = "default_rounds"
CONF_DEFAULT_ROUND_MIN = "default_round_min"
CONF_DEFAULT_BREAK_MIN = "default_break_min"
CONF_WARMUP_TARGET_TEMP = "warmup_target_temp"

# --- Defaults (grounded in the real production setup) -------------------------
DEFAULT_ROUNDS = 2
DEFAULT_ROUND_MIN = 15
DEFAULT_BREAK_MIN = 8
DEFAULT_WARMUP_TARGET_TEMP = 80.0
DEFAULT_VOLUME = 0.5
# Max wall-clock to wait for warm-up before proceeding anyway (safety net).
WARMUP_TIMEOUT_MIN = 45

# --- Water source modes (mirrors PHM) -----------------------------------------
SOURCE_MODE_DELTA = "delta"
SOURCE_MODE_ABSOLUTE = "absolute"
SOURCE_MODES = [SOURCE_MODE_DELTA, SOURCE_MODE_ABSOLUTE]

# --- Session states -----------------------------------------------------------
STATE_IDLE = "idle"
STATE_WARMUP = "warmup"
STATE_IN_ROUND = "in_round"
STATE_BREAK = "break"
STATE_ENDING = "ending"
SESSION_STATES = [STATE_IDLE, STATE_WARMUP, STATE_IN_ROUND, STATE_BREAK, STATE_ENDING]
# States in which a session is considered active (running).
ACTIVE_STATES = {STATE_WARMUP, STATE_IN_ROUND, STATE_BREAK, STATE_ENDING}

# --- Services -----------------------------------------------------------------
SERVICE_START_SESSION = "start_session"
SERVICE_END_SESSION = "end_session"
SERVICE_NEXT_ROUND = "next_round"
SERVICE_EXTEND_ROUND = "extend_round"
SERVICE_SET_ROUNDS = "set_rounds"
SERVICE_SKIP_WARMUP = "skip_warmup"
SERVICE_LOG_WATER = "log_water"
SERVICE_APPLY_PROFILE = "apply_profile"

# --- Events -------------------------------------------------------------------
# Outbound (fired by the coordinator for the panel / blueprints / voice).
EVENT_SESSION_STARTED = f"{DOMAIN}_session_started"
EVENT_ROUND_STARTED = f"{DOMAIN}_round_started"
EVENT_ROUND_ENDED = f"{DOMAIN}_round_ended"
EVENT_BREAK_STARTED = f"{DOMAIN}_break_started"
EVENT_SESSION_ENDED = f"{DOMAIN}_session_ended"
# Inbound command events (low-friction path for the ESPHome panel).
EVENT_CMD_START = f"{DOMAIN}_cmd_start"
EVENT_CMD_STOP = f"{DOMAIN}_cmd_stop"
EVENT_CMD_NEXT = f"{DOMAIN}_cmd_next"
EVENT_CMD_EXTEND = f"{DOMAIN}_cmd_extend"

# --- Service / event attributes -----------------------------------------------
ATTR_TARGET = "target"
ATTR_ROUNDS = "rounds"
ATTR_ROUND_MINUTES = "round_minutes"
ATTR_BREAK_MINUTES = "break_minutes"
ATTR_MEDIA_PLAYER = "media_player"
ATTR_PLAYLIST = "playlist"
ATTR_MINUTES = "minutes"
ATTR_VOLUME = "volume"
ATTR_UNIT = "unit"
ATTR_REASON = "reason"
ATTR_PROFILE = "profile"

# --- Units (water) ------------------------------------------------------------
UNIT_ML = "mL"
UNIT_L = "L"
UNIT_FL_OZ = "fl_oz"
UNITS = [UNIT_ML, UNIT_L, UNIT_FL_OZ]
_ML_PER_FL_OZ = 29.5735

# --- Built-in session profiles (bulk-set the round numbers) -------------------
PROFILE_NONE = "Custom"
SESSION_PROFILES: dict[str, dict[str, int]] = {
    "Classic 2×15": {"rounds": 2, "round_min": 15, "break_min": 8},
    "Quick 2×10": {"rounds": 2, "round_min": 10, "break_min": 5},
    "Long 3×15": {"rounds": 3, "round_min": 15, "break_min": 10},
}

# --- Storage / dispatcher -----------------------------------------------------
STORAGE_VERSION = 1
STORAGE_KEY_FMT = "schvitz_master.{entry_id}"
SIGNAL_UPDATE_FMT = "schvitz_master_update_{entry_id}"
HISTORY_MAX = 50


def to_ml(volume: float, unit: str) -> float:
    """Convert a volume in any supported unit to millilitres."""
    if unit == UNIT_L:
        return volume * 1000.0
    if unit == UNIT_FL_OZ:
        return volume * _ML_PER_FL_OZ
    return volume
