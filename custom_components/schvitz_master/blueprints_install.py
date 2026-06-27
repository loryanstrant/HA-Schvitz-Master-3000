"""Copy bundled automation blueprints into the user's blueprint folder.

Same approach HACS uses for blueprint repos — copy into
``<config>/blueprints/automation/loryanstrant/``, off the event loop, only when
the source is newer or the destination is missing.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_BLUEPRINT_SUBPATH = "automation/loryanstrant"
_DATA_INSTALLED = "schvitz_master_blueprints_installed"


def _copy_blueprints(source_dir: Path, dest_dir: Path) -> list[str]:
    copied: list[str] = []
    if not source_dir.is_dir():
        return copied
    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in source_dir.glob("*.yaml"):
        dst = dest_dir / src.name
        try:
            if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                shutil.copy2(src, dst)
                copied.append(src.name)
        except OSError as err:
            _LOGGER.warning("Could not install blueprint %s: %s", src.name, err)
    return copied


async def async_install_blueprints(hass: HomeAssistant) -> None:
    if hass.data.get(_DATA_INSTALLED):
        return
    source_dir = Path(__file__).parent / "blueprints" / _BLUEPRINT_SUBPATH
    dest_dir = Path(hass.config.path("blueprints", *_BLUEPRINT_SUBPATH.split("/")))
    copied = await hass.async_add_executor_job(_copy_blueprints, source_dir, dest_dir)
    hass.data[_DATA_INSTALLED] = True
    if copied:
        _LOGGER.info("Installed Schvitz blueprints to %s: %s", dest_dir, ", ".join(copied))
