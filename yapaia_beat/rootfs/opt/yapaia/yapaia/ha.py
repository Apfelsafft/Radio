"""Home Assistant / Supervisor glue.

* installs (and updates) the bundled ``yapaia_beat`` custom integration into
  ``/homeassistant/custom_components`` – it provides the entities and the
  Lovelace card
* announces the add-on via Supervisor discovery so the integration is set up
  with one click
"""

from __future__ import annotations

import filecmp
import json
import logging
import os
import shutil
from pathlib import Path

import aiohttp

from .config import APP_DIR

_LOGGER = logging.getLogger(__name__)

SUPERVISOR = "http://supervisor"
HA_CONFIG = Path(os.environ.get("YAPAIA_HA_CONFIG", "/homeassistant"))
INTEGRATION_SRC = APP_DIR / "integration" / "yapaia_beat"
DOMAIN = "yapaia_beat"


def _token() -> str | None:
    return os.environ.get("SUPERVISOR_TOKEN")


def _dirs_equal(a: Path, b: Path) -> bool:
    cmp = filecmp.dircmp(a, b, ignore=["__pycache__"])
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        return False
    return all(_dirs_equal(a / d, b / d) for d in cmp.common_dirs)


def install_integration() -> bool:
    """Copy the integration into the HA config.  Returns True if it changed."""
    if not HA_CONFIG.is_dir():
        _LOGGER.warning("Home Assistant configuration not mapped – cannot install integration")
        return False
    target = HA_CONFIG / "custom_components" / DOMAIN
    if target.exists() and _dirs_equal(INTEGRATION_SRC, target):
        _LOGGER.info("Integration %s is up to date", DOMAIN)
        return False
    fresh = not target.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{DOMAIN}.new")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(INTEGRATION_SRC, tmp, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.rmtree(target, ignore_errors=True)
    tmp.rename(target)
    version = json.loads((target / "manifest.json").read_text()).get("version")
    _LOGGER.info("%s integration %s version %s", "Installed" if fresh else "Updated", DOMAIN, version)
    return True


async def _call(method: str, path: str, payload: dict | None = None) -> dict | None:
    token = _token()
    if not token:
        return None
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.request(
                method, SUPERVISOR + path, json=payload, headers={"Authorization": f"Bearer {token}"}
            ) as r:
                if r.status >= 400:
                    _LOGGER.warning("Supervisor %s %s -> HTTP %s", method, path, r.status)
                    return None
                return await r.json(content_type=None)
    except (aiohttp.ClientError, ValueError) as err:
        _LOGGER.warning("Supervisor call %s failed: %s", path, err)
        return None


async def notify(title: str, message: str, notification_id: str = "yapaia_beat") -> None:
    await _call(
        "POST",
        "/core/api/services/persistent_notification/create",
        {"title": title, "message": message, "notification_id": notification_id},
    )


async def announce(port: int) -> None:
    """Supervisor discovery → HA offers to set up the integration."""
    info = await _call("GET", "/addons/self/info")
    hostname = ((info or {}).get("data") or {}).get("hostname")
    if not hostname:
        _LOGGER.info("Not running under the Supervisor – discovery skipped")
        return
    res = await _call("POST", "/discovery", {"service": DOMAIN, "config": {"host": hostname, "port": port}})
    if res is not None:
        _LOGGER.info("Discovery sent (%s:%s)", hostname, port)
