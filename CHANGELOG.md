# Changelog

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
