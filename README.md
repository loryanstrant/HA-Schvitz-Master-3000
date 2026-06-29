# Schvitz Master 3000

[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5?style=flat-square)](https://github.com/hacs/integration)
[![License](https://img.shields.io/github/license/loryanstrant/HA-Schvitz-Master-3000?style=flat-square)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/loryanstrant/HA-Schvitz-Master-3000?style=flat-square)](https://github.com/loryanstrant/HA-Schvitz-Master-3000/commits)
[![Stars](https://img.shields.io/github/stars/loryanstrant/HA-Schvitz-Master-3000?style=flat-square)](https://github.com/loryanstrant/HA-Schvitz-Master-3000/stargazers)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=loryanstrant&repository=HA-Schvitz-Master-3000&category=integration)

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
