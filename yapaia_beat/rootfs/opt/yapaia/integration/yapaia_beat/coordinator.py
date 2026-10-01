"""Connection to the Yapaia Beat add-on (REST + websocket push)."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, LOGO_URL, SLIDE_URL

_LOGGER = logging.getLogger(__name__)


class YapaiaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Holds the latest status of the radio."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        self.base = f"http://{entry.data[CONF_HOST]}:{entry.data.get(CONF_PORT, 8099)}"
        self.session = async_get_clientsession(hass)
        self._ws_task: asyncio.Task | None = None
        self.speaker: Any = None  # SpeakerSync, set up in __init__

    # ------------------------------------------------------------------
    async def _async_update_data(self) -> dict[str, Any]:
        try:
            async with self.session.get(f"{self.base}/api/status", timeout=aiohttp.ClientTimeout(total=10)) as r:
                r.raise_for_status()
                return await r.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise UpdateFailed(f"Yapaia Beat nicht erreichbar: {err}") from err

    async def command(self, path: str, payload: dict[str, Any] | None = None, method: str = "POST") -> dict[str, Any]:
        try:
            async with self.session.request(
                method, f"{self.base}{path}", json=payload or {}, timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                data = await r.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise HomeAssistantError(f"Yapaia Beat: {err}") from err
        if not data.get("ok", r.status < 400):
            raise HomeAssistantError(f"Yapaia Beat: {data.get('error', r.status)}")
        return data

    async def get_json(self, path: str) -> Any:
        try:
            async with self.session.get(f"{self.base}{path}", timeout=aiohttp.ClientTimeout(total=10)) as r:
                r.raise_for_status()
                return await r.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise HomeAssistantError(f"Yapaia Beat: {err}") from err

    async def fetch(self, path: str) -> tuple[bytes, str] | None:
        try:
            async with self.session.get(f"{self.base}{path}", timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return None
                return await r.read(), r.headers.get("Content-Type", "image/png")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None

    # ------------------------------------------------------------------ push
    def start_push(self, entry: ConfigEntry) -> None:
        self._ws_task = entry.async_create_background_task(self.hass, self._ws_loop(), f"{DOMAIN}_websocket")

    async def _ws_loop(self) -> None:
        delay = 2
        while True:
            try:
                async with self.session.ws_connect(f"{self.base}/api/ws", heartbeat=30) as ws:
                    delay = 2
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            self.async_set_updated_data(msg.json())
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
            except asyncio.CancelledError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
                _LOGGER.debug("Websocket to Yapaia Beat lost: %s", err)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

    # ------------------------------------------------------------------ helpers
    @property
    def station(self) -> dict[str, Any] | None:
        return (self.data or {}).get("station")

    @property
    def favorites(self) -> list[dict[str, Any]]:
        return (self.data or {}).get("favorites") or []

    @staticmethod
    def logo_url(station: dict[str, Any] | None) -> str | None:
        if not station:
            return None
        version = str(station.get("logo_url", "")).rpartition("v=")[2]
        return LOGO_URL.format(station["id"]) + (f"?v={version}" if version else "")

    def slide_url(self) -> str | None:
        ver = (self.data or {}).get("slide_version")
        return f"{SLIDE_URL}?v={ver}" if ver else None

    def location(self) -> str | None:
        data = self.data or {}
        if data.get("band") == "fm" and data.get("frequency"):
            return f"UKW {data['frequency']:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " MHz"
        if data.get("band") == "dab" and data.get("channel"):
            ens = data.get("ensemble")
            return f"DAB+ {data['channel']}" + (f" · {ens}" if ens else "")
        return None
