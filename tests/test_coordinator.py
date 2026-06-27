"""Unit tests for the Schvitz Master 3000 session state machine."""
from types import SimpleNamespace

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.schvitz_master import const as C
from custom_components.schvitz_master.coordinator import SchvitzCoordinator, _to_ml


def _entry(**data):
    base = {C.CONF_NAME: "Sauna", C.CONF_DEFAULT_ROUNDS: 2,
            C.CONF_DEFAULT_ROUND_MIN: 15, C.CONF_DEFAULT_BREAK_MIN: 8}
    base.update(data)
    return MockConfigEntry(domain=C.DOMAIN, data=base, entry_id="test1")


async def _new(hass, **data):
    entry = _entry(**data)
    entry.add_to_hass(hass)
    coord = SchvitzCoordinator(hass, entry)
    await coord.async_initialize()
    return coord


def _water_event(value, unit="mL"):
    return SimpleNamespace(
        data={"new_state": SimpleNamespace(state=str(value), attributes={"unit_of_measurement": unit})}
    )


def _hr_event(value):
    return SimpleNamespace(
        data={"new_state": SimpleNamespace(state=str(value), attributes={})}
    )


async def test_manual_round_flow(hass):
    """start → round1 → break → round2 → end → idle, with a history record."""
    coord = await _new(hass)
    coord.warmup_wait_enabled = False  # no temp sensor configured anyway

    await coord.async_start_session()
    assert coord.state == C.STATE_IN_ROUND
    assert coord.current_round == 1

    await coord.async_next_round()
    assert coord.state == C.STATE_BREAK

    await coord.async_next_round()
    assert coord.state == C.STATE_IN_ROUND
    assert coord.current_round == 2

    await coord.async_next_round()  # last round done
    assert coord.state == C.STATE_IDLE
    assert coord.current_round == 0
    assert len(coord.history) == 1
    assert coord.history[0]["rounds"] == 2


async def test_double_start_is_ignored(hass):
    coord = await _new(hass)
    coord.warmup_wait_enabled = False
    await coord.async_start_session()
    state_before = coord.state
    round_before = coord.current_round
    await coord.async_start_session()  # should no-op
    assert coord.state == state_before
    assert coord.current_round == round_before


async def test_auto_phase_advance(hass):
    """Firing the phase boundary auto-advances round→break→round→end."""
    coord = await _new(hass)
    coord.warmup_wait_enabled = False
    await coord.async_start_session()
    assert coord.state == C.STATE_IN_ROUND

    await coord._on_phase_elapsed(None)  # round 1 over
    assert coord.state == C.STATE_BREAK
    await coord._on_phase_elapsed(None)  # break over
    assert coord.state == C.STATE_IN_ROUND
    assert coord.current_round == 2
    await coord._on_phase_elapsed(None)  # last round over → end
    assert coord.state == C.STATE_IDLE


async def test_warmup_then_skip(hass):
    """With a cold temp sensor, the session waits in warmup until skipped."""
    hass.states.async_set("sensor.t", "20", {"unit_of_measurement": "°C"})
    coord = await _new(hass, **{C.CONF_TEMP_SENSOR: "sensor.t"})
    assert coord.warmup_wait_enabled is True
    await coord.async_start_session()
    assert coord.state == C.STATE_WARMUP
    await coord.async_skip_warmup()
    assert coord.state == C.STATE_IN_ROUND


async def test_warmup_auto_begins_when_hot(hass):
    """If already at target temp, warm-up immediately yields to round 1."""
    hass.states.async_set("sensor.t", "85", {"unit_of_measurement": "°C"})
    coord = await _new(hass, **{C.CONF_TEMP_SENSOR: "sensor.t", C.CONF_WARMUP_TARGET_TEMP: 80})
    await coord.async_start_session()
    assert coord.state == C.STATE_IN_ROUND


async def test_water_delta_tracking(hass):
    hass.states.async_set("sensor.water", "50", {"unit_of_measurement": "mL"})
    coord = await _new(hass, **{C.CONF_WATER_SENSOR: "sensor.water",
                                C.CONF_WATER_SOURCE_MODE: C.SOURCE_MODE_DELTA})
    coord.warmup_wait_enabled = False
    await coord.async_start_session()  # baseline = 50
    await coord._handle_water(_water_event(120))  # +70
    await coord._handle_water(_water_event(140))  # +20
    assert round(coord.session_water_ml) == 90


async def test_water_absolute_with_unit_conversion(hass):
    hass.states.async_set("sensor.water", "0", {"unit_of_measurement": "mL"})
    coord = await _new(hass, **{C.CONF_WATER_SENSOR: "sensor.water",
                                C.CONF_WATER_SOURCE_MODE: C.SOURCE_MODE_ABSOLUTE})
    coord.warmup_wait_enabled = False
    await coord.async_start_session()  # baseline 0
    await coord._handle_water(_water_event(0.5, unit="L"))  # 500 mL absolute
    assert round(coord.session_water_ml) == 500


async def test_heart_rate_avg_max(hass):
    hass.states.async_set("sensor.hr", "60", {})
    coord = await _new(hass, **{C.CONF_HR_SENSOR: "sensor.hr"})
    coord.warmup_wait_enabled = False
    await coord.async_start_session()
    for v in (100, 120, 140):
        await coord._handle_hr(_hr_event(v))
    assert coord.avg_heart_rate == 120
    assert coord.hr_max == 140


async def test_graceful_absence_of_optional_sensors(hass):
    """No water/HR sensors → tracking stays None, nothing raises."""
    coord = await _new(hass)
    coord.warmup_wait_enabled = False
    await coord.async_start_session()
    assert coord.avg_heart_rate is None
    await coord.async_end_session()
    assert coord.history[0]["water_ml"] is None
    assert coord.history[0]["avg_hr"] is None


async def test_log_water_manual(hass):
    coord = await _new(hass)
    coord.warmup_wait_enabled = False
    await coord.async_start_session()
    await coord.async_log_water(250, C.UNIT_ML)
    await coord.async_log_water(0.25, C.UNIT_L)
    assert round(coord.session_water_ml) == 500


async def test_apply_profile(hass):
    coord = await _new(hass)
    await coord.async_apply_profile("Long 3×15")
    assert coord.round_count == 3
    assert coord.round_duration_min == 15
    assert coord.break_duration_min == 10


async def test_extend_round(hass):
    coord = await _new(hass)
    coord.warmup_wait_enabled = False
    await coord.async_start_session()
    before = coord.time_remaining
    await coord.async_extend(5)
    assert coord.time_remaining >= (before or 0)


async def test_resume_after_restart_advances_past_phase(hass):
    """A round whose end is in the past resumes into the break on restart."""
    from homeassistant.util import dt as dt_util
    from datetime import timedelta

    coord = await _new(hass)
    coord.state = C.STATE_IN_ROUND
    coord.current_round = 1
    coord.round_count = 2
    coord.phase_ends_at = dt_util.utcnow() - timedelta(seconds=5)
    await coord._resume_after_restart()
    assert coord.state == C.STATE_BREAK


async def test_music_starts_at_round_by_default(hass):
    coord = await _new(hass)
    coord.warmup_wait_enabled = False
    plays = []
    coord._play_media = lambda: plays.append(1) or _async_none()
    await coord.async_start_session()  # round 1 begins → music plays once
    assert coord._music_started is True
    assert len(plays) == 1


async def test_music_starts_at_temp_when_configured(hass):
    hass.states.async_set("sensor.t", "20", {"unit_of_measurement": "°C"})
    coord = await _new(hass, **{C.CONF_TEMP_SENSOR: "sensor.t",
                                C.CONF_MUSIC_START_MODE: C.MUSIC_START_TEMP,
                                C.CONF_MUSIC_START_TEMP: 50,
                                C.CONF_WARMUP_TARGET_TEMP: 80})
    plays = []
    coord._play_media = lambda: plays.append(1) or _async_none()
    await coord.async_start_session()  # warmup, cold → no music yet
    assert coord.state == C.STATE_WARMUP
    assert coord._music_started is False
    # temp climbs past the music-start temp (but below warm-up target) → music starts
    await coord._handle_temp(_temp_event(55))
    assert coord._music_started is True
    assert len(plays) == 1
    assert coord.state == C.STATE_WARMUP  # still warming (target is 80)


def _async_none():
    async def _n():
        return None
    return _n()


def _temp_event(value):
    return SimpleNamespace(
        data={"new_state": SimpleNamespace(state=str(value), attributes={"unit_of_measurement": "°C"})}
    )


def test_to_ml_units():
    assert _to_ml(1, "L") == 1000.0
    assert round(_to_ml(1, "fl_oz"), 2) == 29.57
    assert _to_ml(250, "mL") == 250
