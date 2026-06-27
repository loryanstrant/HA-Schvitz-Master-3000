# Schvitz Master 3000

Runs your sauna session end-to-end: warm-up → rounds → breaks → end.

## Per-session controls (entities)

- **number**: round count, round duration, break duration, warm-up target temp
- **select**: media player, playlist (from Music Assistant), session profile
- **switch**: warm-up wait enabled
- **button**: start, stop, next round, extend (+5 min), skip warm-up
- **sensor**: session state, current round, time remaining, session water, avg/max
  heart rate, peak temp, last-session water (charted)
- **binary_sensor**: session active, heating, in-round, break

## Services

| Service | What it does |
|---|---|
| `schvitz_master.start_session` | Start a session (optional rounds/durations/media overrides) |
| `schvitz_master.end_session` | End the current session |
| `schvitz_master.next_round` | Skip to the next round / break |
| `schvitz_master.extend_round` | Add minutes to the current phase |
| `schvitz_master.set_rounds` | Change the round count |
| `schvitz_master.skip_warmup` | Stop waiting for warm-up and begin round 1 |
| `schvitz_master.log_water` | Manually log water for a session |
| `schvitz_master.apply_profile` | Apply a built-in session profile |

## Events

Outbound: `schvitz_master_session_started`, `_round_started`, `_round_ended`,
`_break_started`, `_session_ended`. Inbound commands (for the ESPHome panel):
`schvitz_master_cmd_start` / `_stop` / `_next` / `_extend`.
