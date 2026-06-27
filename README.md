# Schvitz Master 3000

A Home Assistant integration that runs your sauna **session** end-to-end — so you
start it once and it takes care of the rest.

It replaces the scattered timer/counter/template-sensor/automation mix (and the
session logic baked into ESPHome firmware) with **one config-flow integration** that
owns a session state machine:

```
idle → warm-up → round 1 → break → round 2 → … → end → idle
```

## Features

- **Rounds** — the number of times you sit (default 2), adjustable per session.
- **Adjustable durations** — round length and break length, per session, no firmware
  reflash.
- **Full orchestration** — on start it flicks the heater/pre-switches, plays your
  chosen Music Assistant playlist on your sauna speaker, runs the round & break
  countdowns, notifies you at each transition, and cleans up at the end.
- **Per-session sensor tracking** — optionally track a water bottle (HidrateSpark) and
  a heart-rate monitor. Both are optional every session and degrade gracefully when
  absent. Water-per-session history is exposed for charting.
- **Monitor-only warm-up** — optionally wait until the sauna reaches a target temp
  (HA can switch the sauna on/off but never controls the hardwired thermostat) before
  starting round 1.
- **Four ways to drive it** — a bundled Lovelace card, the ESPHome sauna panel,
  mobile notifications, and voice.

## Install

1. HACS → custom repository → this repo → install.
2. Restart Home Assistant.
3. Settings → Devices & Services → **Add integration** → *Schvitz Master 3000*, then
   pick your sauna's temperature/door/switch/media/water/heart-rate entities.

See [info.md](info.md) for the per-session controls and services.
