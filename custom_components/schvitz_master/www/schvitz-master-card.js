/*!
 * Schvitz Master 3000 Card
 * https://github.com/loryanstrant/HA-Schvitz-Master-3000
 * MIT License
 *
 * A single-file vanilla web component — no build step required.
 * Shows a countdown ring (round n/N + time remaining), Start/Next/+5/Stop
 * controls, water-this-session, and a per-session history strip.
 */

const CARD_TAG = "schvitz-master-card";
const EDITOR_TAG = "schvitz-master-card-editor";
const CARD_VERSION = "0.2.0";

const STATE_LABEL = {
  idle: "Idle",
  warmup: "Heating",
  in_round: "In round",
  break: "Break",
  ending: "Finishing",
};

function fmtMMSS(seconds) {
  if (seconds == null || isNaN(seconds)) return "--:--";
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

class SchvitzMasterCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._slug = this._config.slug || null;
  }

  static getConfigElement() {
    return document.createElement(EDITOR_TAG);
  }

  static getStubConfig(hass) {
    const ent = Object.keys(hass.states).find((e) =>
      e.startsWith("sensor.schvitz_") && e.endsWith("_session_state")
    );
    const slug = ent ? ent.slice("sensor.schvitz_".length, -"_session_state".length) : "";
    return { slug };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._slug) {
      const ent = Object.keys(hass.states).find((e) =>
        e.startsWith("sensor.schvitz_") && e.endsWith("_session_state")
      );
      if (ent) this._slug = ent.slice("sensor.schvitz_".length, -"_session_state".length);
    }
    this._render();
  }

  _e(domain, suffix) {
    return this._hass && this._slug
      ? this._hass.states[`${domain}.schvitz_${this._slug}_${suffix}`]
      : undefined;
  }

  _num(suffix) {
    const s = this._e("sensor", suffix);
    return s ? Number(s.state) : null;
  }

  _call(service, data = {}) {
    this._hass.callService("schvitz_master", service, { target: this._slug, ...data });
  }

  _render() {
    if (!this._hass) return;
    if (!this._slug) {
      this.innerHTML = `<ha-card><div style="padding:16px">No Schvitz Master sauna found. Set <code>slug:</code> in the card config.</div></ha-card>`;
      return;
    }

    const state = (this._e("sensor", "session_state") || {}).state || "idle";
    const round = this._num("current_round") ?? 0;
    const total =
      (this._e("sensor", "current_round") || { attributes: {} }).attributes.total_rounds ?? 0;
    const remaining = this._num("time_remaining");
    const water = this._num("session_water");
    const avgHr = this._num("avg_heart_rate");
    const peak = this._num("peak_temp");
    const lastSensor = this._e("sensor", "last_session_water") || { attributes: {} };
    const history = lastSensor.attributes.history || [];

    const active = state !== "idle";
    // Ring progress: fraction of the current phase elapsed (best-effort via attrs).
    const phaseEnds = (this._e("sensor", "session_state") || { attributes: {} }).attributes
      .phase_ends_at;
    let pct = active ? 100 : 0;
    if (remaining != null && active && state !== "warmup") {
      // We don't know the phase length here; show remaining as a shrinking ring
      // scaled against the configured round/break number entities.
      const knob = state === "break" ? "break_duration" : "round_duration";
      const mins = Number((this._e("number", knob) || {}).state) || 0;
      const totalSec = mins * 60;
      pct = totalSec > 0 ? Math.max(0, Math.min(100, (remaining / totalSec) * 100)) : 0;
    }

    const ring = this._ring(pct, state);
    const label = STATE_LABEL[state] || state;
    const sub =
      state === "idle"
        ? "Ready"
        : state === "warmup"
        ? "Warming up…"
        : `Round ${round} of ${total}`;

    this.innerHTML = `
      <ha-card>
        <style>
          .sm-wrap { padding: 16px; font-family: var(--primary-font-family); }
          .sm-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
          .sm-title { font-weight:600; font-size:1.1rem; }
          .sm-state { color: var(--secondary-text-color); }
          .sm-ring-wrap { display:flex; justify-content:center; margin:8px 0; }
          .sm-center { text-align:center; }
          .sm-time { font-size:2.2rem; font-weight:700; }
          .sm-sub { color: var(--secondary-text-color); }
          .sm-btns { display:flex; gap:8px; justify-content:center; margin:12px 0 4px; flex-wrap:wrap; }
          .sm-btns button {
            border:none; border-radius:10px; padding:10px 14px; font-weight:600;
            cursor:pointer; background: var(--secondary-background-color);
            color: var(--primary-text-color);
          }
          .sm-btns button.primary { background: var(--primary-color); color: var(--text-primary-color); }
          .sm-stats { display:flex; justify-content:space-around; margin-top:8px; text-align:center; }
          .sm-stats .v { font-weight:600; font-size:1.1rem; }
          .sm-stats .k { color: var(--secondary-text-color); font-size:0.8rem; }
          .sm-hist { margin-top:12px; }
          .sm-hist .row { display:flex; justify-content:space-between; padding:2px 0; border-top:1px solid var(--divider-color); font-size:0.85rem; }
        </style>
        <div class="sm-wrap">
          <div class="sm-head">
            <span class="sm-title">${(this._config.title) || "Schvitz Master"}</span>
            <span class="sm-state">${label}</span>
          </div>
          <div class="sm-ring-wrap">${ring}</div>
          <div class="sm-center">
            <div class="sm-time">${state === "warmup" ? "♨" : fmtMMSS(remaining)}</div>
            <div class="sm-sub">${sub}</div>
          </div>
          <div class="sm-btns">
            ${
              active
                ? `<button data-act="stop">Stop</button>
                   ${state === "warmup" ? `<button data-act="skip_warmup">Skip warm-up</button>` : ""}
                   <button data-act="next_round">Next</button>
                   <button data-act="extend">+5 min</button>`
                : `<button class="primary" data-act="start">Start schvitz</button>`
            }
          </div>
          <div class="sm-stats">
            <div><div class="v">${water != null ? Math.round(water) + " mL" : "—"}</div><div class="k">Water</div></div>
            <div><div class="v">${avgHr != null ? Math.round(avgHr) : "—"}</div><div class="k">Avg HR</div></div>
            <div><div class="v">${peak != null ? Math.round(peak) + "°" : "—"}</div><div class="k">Peak</div></div>
          </div>
          ${this._historyHtml(history)}
        </div>
      </ha-card>`;

    this.querySelectorAll("button[data-act]").forEach((b) => {
      b.addEventListener("click", () => {
        const act = b.getAttribute("data-act");
        if (act === "extend") this._call("extend_round", { minutes: 5 });
        else this._call(act);
      });
    });
  }

  _ring(pct, state) {
    const r = 70;
    const c = 2 * Math.PI * r;
    const off = c * (1 - Math.max(0, Math.min(100, pct)) / 100);
    const color =
      state === "warmup"
        ? "var(--warning-color, #e8823c)"
        : state === "break"
        ? "var(--info-color, #5fa8d6)"
        : "var(--primary-color)";
    return `
      <svg width="170" height="170" viewBox="0 0 170 170">
        <circle cx="85" cy="85" r="${r}" fill="none" stroke="var(--divider-color)" stroke-width="12"/>
        <circle cx="85" cy="85" r="${r}" fill="none" stroke="${color}" stroke-width="12"
          stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${off}"
          transform="rotate(-90 85 85)"/>
      </svg>`;
  }

  _historyHtml(history) {
    if (!history || !history.length) return "";
    const rows = history
      .slice(0, 5)
      .map((h) => {
        const when = h.ended_at ? new Date(h.ended_at).toLocaleDateString() : "";
        const water = h.water_ml != null ? `${Math.round(h.water_ml)} mL` : "—";
        return `<div class="row"><span>${when} · ${h.rounds || 0} rounds</span><span>${water}</span></div>`;
      })
      .join("");
    return `<div class="sm-hist"><div class="k" style="color:var(--secondary-text-color);font-size:0.8rem;margin-bottom:2px">Recent sessions</div>${rows}</div>`;
  }

  getCardSize() {
    return 5;
  }
}

class SchvitzMasterCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }
  set hass(hass) {
    this._hass = hass;
  }
  _render() {
    this.innerHTML = `
      <div style="padding:8px">
        <ha-textfield label="Title (optional)" id="title"></ha-textfield>
        <ha-textfield label="Sauna slug (optional)" id="slug"></ha-textfield>
      </div>`;
    const t = this.querySelector("#title");
    const s = this.querySelector("#slug");
    if (t) { t.value = this._config.title || ""; t.addEventListener("input", () => this._emit()); }
    if (s) { s.value = this._config.slug || ""; s.addEventListener("input", () => this._emit()); }
  }
  _emit() {
    const config = {
      ...this._config,
      title: this.querySelector("#title").value || undefined,
      slug: this.querySelector("#slug").value || undefined,
    };
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config } }));
  }
}

if (!customElements.get(CARD_TAG)) customElements.define(CARD_TAG, SchvitzMasterCard);
if (!customElements.get(EDITOR_TAG)) customElements.define(EDITOR_TAG, SchvitzMasterCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: CARD_TAG,
  name: "Schvitz Master 3000",
  description: "Start and run a sauna session — rounds, breaks, water, history.",
  preview: true,
});

console.info(
  `%c SCHVITZ-MASTER-3000 %c v${CARD_VERSION} `,
  "color:#fff;background:#e8823c;font-weight:700",
  "color:#e8823c;background:#201b18"
);
