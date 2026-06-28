"""Serve the Lovelace card and register it as a dashboard resource.

Mirrors Personal Hydration Manager's three-pronged registration so the card is
reliably picked up across YAML and storage dashboards, and survives cache wipes.
Both helpers dedupe, so re-running on every entry setup is safe.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_when_setup

_LOGGER = logging.getLogger(__name__)

# Keep in lockstep with manifest.json on every release.
CARD_VERSION = "0.3.0"
STATIC_URL_BASE = "/schvitz_master_static"
CARD_FILE = "schvitz-master-card.js"
CARD_URL = f"{STATIC_URL_BASE}/{CARD_FILE}"
CARD_URL_VERSIONED = f"{CARD_URL}?v={CARD_VERSION}"

_DATA_STATIC = "schvitz_master_static_registered"
_DATA_EXTRA_JS = "schvitz_master_extra_js_registered"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Expose the card bundle and register it as a Lovelace resource."""
    www_path = Path(__file__).parent / "www"
    card_path = www_path / CARD_FILE
    if not card_path.is_file():
        _LOGGER.error("Card bundle missing at %s", card_path)
        return

    if not hass.data.get(_DATA_STATIC):
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(STATIC_URL_BASE, str(www_path), cache_headers=False)]
            )
            hass.data[_DATA_STATIC] = True
        except RuntimeError as err:
            _LOGGER.debug("Static path already registered: %s", err)
            hass.data[_DATA_STATIC] = True

    if not hass.data.get(_DATA_EXTRA_JS):
        add_extra_js_url(hass, CARD_URL_VERSIONED)
        hass.data[_DATA_EXTRA_JS] = True

    if hass.data.get("lovelace") is not None:
        await _async_register_lovelace_resource(hass)
    else:
        async def _on_lovelace_ready(_hass: HomeAssistant, _component: str) -> None:
            await _async_register_lovelace_resource(_hass)

        async_when_setup(hass, "lovelace", _on_lovelace_ready)


async def _async_register_lovelace_resource(hass: HomeAssistant) -> None:
    lovelace_data = hass.data.get("lovelace")
    if lovelace_data is None:
        return
    resources = getattr(lovelace_data, "resources", None)
    if resources is None:
        return  # YAML mode — extra_js_url already covers it.

    if hasattr(resources, "async_load") and not getattr(resources, "loaded", True):
        try:
            await resources.async_load()
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.debug("Could not pre-load Lovelace resources: %s", err)

    existing = None
    for item in resources.async_items():
        if item.get("url", "").split("?", 1)[0] == CARD_URL:
            existing = item
            break

    payload = {"res_type": "module", "url": CARD_URL_VERSIONED}
    try:
        if existing is None:
            await resources.async_create_item(payload)
            _LOGGER.info("Registered Schvitz card resource %s", CARD_URL_VERSIONED)
        elif existing.get("url") != CARD_URL_VERSIONED:
            await resources.async_update_item(existing["id"], payload)
    except Exception as err:  # pragma: no cover - defensive
        _LOGGER.warning("Could not register Lovelace resource: %s", err)
