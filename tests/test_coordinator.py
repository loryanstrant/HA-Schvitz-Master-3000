"""Unit tests for the Schvitz Master 3000 session state machine (v0.3)."""
from datetime import timedelta
from types import SimpleNamespace

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.schvitz_master import const as C
from custom_components.schvitz_master.coordinator import SchvitzCoordinator, _to_ml


def _entry(**data):
    base = {C.CONF_NAME: "Sauna", C.CONF_DEFAULT_ROUNDS: 2, C.CONF_DEFAULT_ROUND_MIN: 15}
    base.update(data)
    return MockConfigEntry(domain=C.DOMAIN, data=base, entry_id="test1")


async def _new(hass, **data):
    entry = _entry(**data)
    entry.add_to_hass(hass)
    coord = SchvitzCoordinator(hass, entry)
    await coord.async_initialize()
    return coord


def _ev(value, unit=None):
    attrs = {"unit_of_measurement": unit} if unit else {}
    return SimpleNamespace(data={"new_state": SimpleNamespace(state=str(value), attributes=attrs)})


def _async_none():
    async def _n():
        return None
    return _n()


# ---- core flow ----------------------------------------------------------
async def test_start_enters_heating_then_manual_round(hass):
    coord = await _new(hass)
    await coord.async_start_session()
    assert coord.state == C.STATE_HEATING        # waits for you to get in
    assert coord.current_round == 0
    await coord.async_start_round()
    assert coord.state == C.STATE_IN_ROUND
    assert coord.current_round == 1


async def test_full_manual_flow(hass):
    coord = await _new(hass)
    await coord.async_start_session()
    await coord.async_start_round()              # round 1
    await coord.async_next_round()               # -> break
    assert coord.state == C.STATE_BREAK
    await coord.async_next_round()               # -> round 2
    assert coord.current_round == 2
    await coord.async_next_round()               # last round -> end
    assert coord.state == C.STATE_IDLE
    assert coord.history[0]["rounds"] == 2


async def test_open_ended_break_has_no_timer(hass):
    coord = await _new(hass)  # no break duration -> open-ended
    await coord.async_start_session()
    await coord.async_start_round()
    await coord.async_next_round()
    assert coord.state == C.STATE_BREAK
    assert coord.phase_ends_at is None           # open-ended: waits for Next
    assert coord.time_remaining is None
    await coord.async_start_round()              # back from cold shower
    assert coord.state == C.STATE_IN_ROUND
    assert coord.current_round == 2


async def test_timed_break_auto_advances(hass):
    coord = await _new(hass, **{C.CONF_DEFAULT_BREAK_MIN: 8})
    await coord.async_start_session()
    await coord.async_start_round()
    await coord._on_phase_elapsed(None)          # round 1 timer ends -> break
    assert coord.state == C.STATE_BREAK
    assert coord.phase_ends_at is not None
    await coord._on_phase_elapsed(None)          # break timer ends -> round 2
    assert coord.state == C.STATE_IN_ROUND


async def test_double_start_ignored(hass):
    coord = await _new(hass)
    await coord.async_start_session()
    await coord.async_start_session()
    assert coord.state == C.STATE_HEATING


# ---- heater trigger -----------------------------------------------------
async def test_heater_switch_triggers_session(hass):
    # Core turn_on/off always exist in production; register no-ops for the test.
    hass.services.async_register("homeassistant", "turn_on", lambda call: None)
    hass.services.async_register("homeassistant", "turn_off", lambda call: None)
    coord = await _new(hass, **{C.CONF_HEATER_SWITCH: "input_boolean.schvitz"})
    await coord._on_heater_change(_ev("on"))
    assert coord.state == C.STATE_HEATING
    await coord._on_heater_change(_ev("off"))
    assert coord.state == C.STATE_IDLE


# ---- ready notification (manual start, no auto-begin) -------------------
async def test_ready_notifies_but_does_not_auto_start(hass):
    hass.states.async_set("sensor.t", "20", {"unit_of_measurement": "°C"})
    coord = await _new(hass, **{C.CONF_TEMP_SENSOR: "sensor.t", C.CONF_WARMUP_TARGET_TEMP: 80})
    notes = []
    coord._notify = lambda t, m: notes.append((t, m))
    await coord.async_start_session()
    await coord._handle_temp(_ev(85, "°C"))      # reaches target
    assert coord._ready_notified is True
    assert coord.state == C.STATE_HEATING         # still waiting for the user
    assert any("ready" in t.lower() for t, _ in notes)


# ---- heating from power -------------------------------------------------
async def test_is_heating_from_power(hass):
    hass.states.async_set("sensor.p", "3.5", {"unit_of_measurement": "kW"})
    coord = await _new(hass, **{C.CONF_POWER_SENSOR: "sensor.p"})
    assert coord.is_heating is True
    hass.states.async_set("sensor.p", "0.0", {"unit_of_measurement": "kW"})
    assert coord.is_heating is False


async def test_is_heating_from_operation_sensor(hass):
    hass.states.async_set("sensor.op", "Heating", {})
    coord = await _new(hass, **{C.CONF_OPERATION_SENSOR: "sensor.op"})
    assert coord.is_heating is True
    hass.states.async_set("sensor.op", "Off", {})
    assert coord.is_heating is False


# ---- tracking -----------------------------------------------------------
async def test_water_delta_tracking(hass):
    hass.states.async_set("sensor.water", "50", {"unit_of_measurement": "mL"})
    coord = await _new(hass, **{C.CONF_WATER_SENSOR: "sensor.water",
                                C.CONF_WATER_SOURCE_MODE: C.SOURCE_MODE_DELTA})
    await coord.async_start_session()
    await coord._handle_water(_ev(120, "mL"))
    await coord._handle_water(_ev(140, "mL"))
    assert round(coord.session_water_ml) == 90


async def test_water_absolute_unit_conversion(hass):
    hass.states.async_set("sensor.water", "0", {"unit_of_measurement": "mL"})
    coord = await _new(hass, **{C.CONF_WATER_SENSOR: "sensor.water",
                                C.CONF_WATER_SOURCE_MODE: C.SOURCE_MODE_ABSOLUTE})
    await coord.async_start_session()
    await coord._handle_water(_ev(0.5, "L"))
    assert round(coord.session_water_ml) == 500


async def test_heart_rate_avg_max(hass):
    hass.states.async_set("sensor.hr", "60", {})
    coord = await _new(hass, **{C.CONF_HR_SENSOR: "sensor.hr"})
    await coord.async_start_session()
    for v in (100, 120, 140):
        await coord._handle_hr(_ev(v))
    assert coord.avg_heart_rate == 120
    assert coord.hr_max == 140


async def test_graceful_absence(hass):
    coord = await _new(hass)
    await coord.async_start_session()
    assert coord.avg_heart_rate is None
    await coord.async_end_session()
    assert coord.history[0]["water_ml"] is None
    assert coord.history[0]["avg_hr"] is None


async def test_log_water_manual(hass):
    coord = await _new(hass)
    await coord.async_start_session()
    await coord.async_log_water(250, C.UNIT_ML)
    await coord.async_log_water(0.25, C.UNIT_L)
    assert round(coord.session_water_ml) == 500


async def test_apply_profile(hass):
    coord = await _new(hass)
    await coord.async_apply_profile("Long 3×15")
    assert coord.round_count == 3
    assert coord.break_duration_min == 10


async def test_extend_round(hass):
    coord = await _new(hass, **{C.CONF_DEFAULT_BREAK_MIN: 8})
    await coord.async_start_session()
    await coord.async_start_round()
    before = coord.time_remaining
    await coord.async_extend(5)
    assert coord.time_remaining >= (before or 0)


async def test_resume_after_restart(hass):
    coord = await _new(hass)
    coord.state = C.STATE_IN_ROUND
    coord.current_round = 1
    coord.round_count = 2
    coord.phase_ends_at = dt_util.utcnow() - timedelta(seconds=5)
    await coord._resume_after_restart()
    assert coord.state == C.STATE_BREAK


# ---- music --------------------------------------------------------------
async def test_music_starts_at_round_one(hass):
    coord = await _new(hass)
    plays = []
    coord._play_media = lambda: plays.append(1) or _async_none()
    await coord.async_start_session()            # heating: no music yet (round mode)
    assert coord._music_started is False
    await coord.async_start_round()              # round 1: music plays
    assert coord._music_started is True
    assert len(plays) == 1


async def test_music_starts_at_temp(hass):
    hass.states.async_set("sensor.t", "20", {"unit_of_measurement": "°C"})
    coord = await _new(hass, **{C.CONF_TEMP_SENSOR: "sensor.t",
                                C.CONF_MUSIC_START_MODE: C.MUSIC_START_TEMP,
                                C.CONF_MUSIC_START_TEMP: 50, C.CONF_WARMUP_TARGET_TEMP: 80})
    plays = []
    coord._play_media = lambda: plays.append(1) or _async_none()
    await coord.async_start_session()
    assert coord._music_started is False
    await coord._handle_temp(_ev(55, "°C"))
    assert coord._music_started is True
    assert len(plays) == 1


def test_to_ml_units():
    assert _to_ml(1, "L") == 1000.0
    assert round(_to_ml(1, "fl_oz"), 2) == 29.57
    assert _to_ml(250, "mL") == 250
