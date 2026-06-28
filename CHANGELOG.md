# Changelog

## 0.3.0
A redesign of how a session runs, from real-world feedback.

### Added
- **Heater switch is the trigger**: enabling your sauna (e.g. `schvitz_mode`) now begins a
  session automatically; the Start button just flips it.
- **Manual round start**: after the sauna heats up you get a **"sauna's ready"** phone
  notification, then tap **Start round** when you get in (no more auto-start).
- **Open-ended breaks**: after a round the sauna waits until you tap **Next** (back from
  your cold shower). Break length is now optional — set it only for a timed break.
- **Heating from power**: real heating status comes from your plug's power / operation
  sensor, not a switch.
- **Start scene**: activate a scene you compose at session start (set lights to exact
  colours), instead of just flipping switches.
- **Safety cut-offs**: auto-end + switch off if left heating too long, or if the door is
  left open during a session.
- **Music Assistant playlist picker**: choose a playlist from a dropdown of your MA
  playlists — no more hunting for IDs.
- Setup screens now show **Next** buttons and a step counter (1 of 5 …).

### Changed
- Door sensor and heater switch are optional (from 0.2.0); break length is now optional too.
- "Skip warm-up" → **Start round**; the warm-up-wait switch was removed.

## 0.2.0

### Added
- The setup screen is now broken into a few short, explained steps (sauna → power →
  session → music → tracking), so each option has context — including what "rounds" are.
- Music can now start **when the sauna reaches a chosen temperature** instead of only at
  round 1 (Music step → "Start the music").
- The notification service is now a **dropdown** of your `notify.*` services (you can
  still type a custom one).

### Changed
- The **door sensor** and the **heater / power switch** are now optional.

## 0.1.0
Initial release.

### Added
- Config-flow integration that runs a sauna session state machine
  (warm-up → rounds → breaks → end) with full orchestration of switches and
  Music Assistant media.
- Per-session entities: round count / round & break duration / warm-up target numbers,
  media-player / playlist / session-profile selects, warm-up-wait switch, start / stop /
  next-round / extend / skip-warm-up buttons.
- Per-session tracking sensors (session state, current round, time remaining, water,
  avg/max heart rate, peak temp) with graceful handling of absent water/heart-rate
  sensors, plus a charted last-session-water sensor.
- Services (`start_session`, `end_session`, `next_round`, `extend_round`, `set_rounds`,
  `skip_warmup`, `log_water`, `apply_profile`) and outbound/inbound events for the
  ESPHome panel, blueprints, and voice.
- Bundled Lovelace card and automation blueprints.
