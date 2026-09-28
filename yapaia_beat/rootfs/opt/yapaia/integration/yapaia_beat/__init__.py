"""Yapaia Beat – FM/DAB+ radio (RTL-SDR) as Home Assistant entities."""

from __future__ import annotations

import logging
import re

import voluptuous as vol
from aiohttp import web

from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CARD_PATH, CARD_URL, DOMAIN, VERSION
from .coordinator import YapaiaCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.MEDIA_PLAYER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.IMAGE,
]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_STATION_ID = re.compile(r"^[a-z0-9-]{1,40}$")

YapaiaConfigEntry = ConfigEntry[YapaiaCoordinator]


def _coordinators(hass: HomeAssistant) -> list[YapaiaCoordinator]:
    return list(hass.data.get(DOMAIN, {}).values())


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the Lovelace card, image proxy views and services."""
    hass.data.setdefault(DOMAIN, {})
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(CARD_PATH), False)])
    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
    except ImportError:  # pragma: no cover
        _LOGGER.warning("Could not register the Yapaia Beat card automatically")
    hass.http.register_view(YapaiaLogoView())
    hass.http.register_view(YapaiaSlideView())

    async def _call(path: str, payload: dict) -> None:
        coords = _coordinators(hass)
        if not coords:
            raise HomeAssistantError("Yapaia Beat ist nicht eingerichtet")
        for coord in coords:
            await coord.command(path, payload)

    async def play(call: ServiceCall) -> None:
        if call.data.get("frequency"):
            await _call("/api/play", {"frequency": call.data["frequency"]})
        elif call.data.get("station_id"):
            await _call("/api/play", {"id": call.data["station_id"]})
        elif call.data.get("station"):
            await _call("/api/play", {"name": call.data["station"]})
        else:
            await _call("/api/play", {})

    async def scan(call: ServiceCall) -> None:
        await _call("/api/scan", {"band": call.data.get("band", "all")})

    async def favorite(call: ServiceCall) -> None:
        for coord in _coordinators(hass):
            sid = call.data.get("station_id") or (coord.station or {}).get("id")
            if sid:
                await coord.command("/api/favorites", {"id": sid, "favorite": call.data.get("favorite", True)})

    hass.services.async_register(
        DOMAIN,
        "play",
        play,
        schema=vol.Schema(
            {
                vol.Optional("station"): cv.string,
                vol.Optional("station_id"): cv.string,
                vol.Optional("frequency"): vol.All(vol.Coerce(float), vol.Range(min=87.5, max=108.0)),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN, "scan", scan, schema=vol.Schema({vol.Optional("band", default="all"): vol.In(["fm", "dab", "all"])})
    )
    hass.services.async_register(
        DOMAIN,
        "set_favorite",
        favorite,
        schema=vol.Schema({vol.Optional("station_id"): cv.string, vol.Optional("favorite", default=True): cv.boolean}),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: YapaiaConfigEntry) -> bool:
    coordinator = YapaiaCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    coordinator.start_push(entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: YapaiaConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok


class YapaiaLogoView(HomeAssistantView):
    """Serve station logos without auth so standard cards and <img> tags work.

    Logos are public images, nothing sensitive is exposed.
    """

    url = "/api/yapaia_beat/logo/{station_id}"
    name = "api:yapaia_beat:logo"
    requires_auth = False

    async def get(self, request: web.Request, station_id: str) -> web.Response:
        if station_id != "current" and not _STATION_ID.match(station_id):
            raise web.HTTPNotFound()
        for coord in _coordinators(request.app["hass"]):
            res = await coord.fetch(f"/api/logo/{station_id}")
            if res:
                return web.Response(body=res[0], content_type=res[1].split(";")[0], headers={"Cache-Control": "public, max-age=86400"})
        raise web.HTTPNotFound()


class YapaiaSlideView(HomeAssistantView):
    """DAB+ slideshow image of the current station."""

    url = "/api/yapaia_beat/slide"
    name = "api:yapaia_beat:slide"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        for coord in _coordinators(request.app["hass"]):
            res = await coord.fetch("/api/slide")
            if res:
                return web.Response(body=res[0], content_type=res[1].split(";")[0], headers={"Cache-Control": "no-cache"})
        raise web.HTTPNotFound()
