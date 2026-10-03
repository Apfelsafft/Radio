"""Yapaia Beat – FM/DAB+ radio (RTL-SDR) as Home Assistant entities."""

from __future__ import annotations

import asyncio
import logging
import re
import time

import aiohttp

import voluptuous as vol
from aiohttp import web

from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CARD_PATH, CARD_URL, DOMAIN, STREAM_URL, VERSION
from .coordinator import YapaiaCoordinator
from .speaker import SpeakerSync

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
    hass.http.register_view(YapaiaStreamView())

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

    async def set_output(call: ServiceCall) -> None:
        await _call("/api/settings", output_payload(call.data["output"]))

    async def announce(call: ServiceCall) -> ServiceResponse:
        """Speak a message mixed into the radio (music turned down, then back up).

        Meant for the other Yapaia modules (Yapaia Go's navigation voice …) and
        automations.  Fails when nobody would hear it, so the caller can fall
        back to ``tts.speak``."""
        try:
            coords = _coordinators(hass)
            if not coords:
                raise HomeAssistantError("Yapaia Beat ist nicht eingerichtet")
            beginn = time.monotonic()
            audio, fmt = await tts_audio(
                hass, call.data["message"], call.data.get("engine"), call.data.get("language")
            )
            tts_s = round(time.monotonic() - beginn, 2)
            res = await coords[0].send_audio(
                "/api/announce", audio, {"format": fmt, "priority": call.data.get("priority", "hinweis")}
            )
        except Exception as err:  # noqa: BLE001 – TTS engines fail in their own ways
            if not call.return_response:
                raise
            # A caller that asks for the response (Yapaia Go) gets the reason
            # in plain words instead of a bare HTTP 500.
            _LOGGER.warning("Yapaia Beat announcement failed: %s", err)
            return {"ok": False, "error": str(err) or err.__class__.__name__}
        # tts_s: how long Home Assistant took to render the voice – the part
        # of the delay that is not the browser's buffer
        return {"ok": True, "seconds": res.get("seconds"), "tts_s": tts_s}

    hass.services.async_register(
        DOMAIN,
        "announce",
        announce,
        schema=vol.Schema(
            {
                vol.Required("message"): vol.All(cv.string, vol.Length(min=1, max=1000)),
                vol.Optional("engine"): cv.entity_id,
                vol.Optional("language"): cv.string,
                vol.Optional("priority", default="hinweis"): vol.In(["info", "hinweis", "navigation"]),
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, "set_output", set_output, schema=vol.Schema({vol.Required("output"): cv.string})
    )
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


async def tts_audio(hass: HomeAssistant, message: str, engine: str | None, language: str | None) -> tuple[bytes, str]:
    """Let Home Assistant's text-to-speech render ``message``.

    Asks for WAV (mono, 48 kHz) so the add-on needs no decoder; engines or
    versions that cannot convert fall back to their native format (MP3 is
    decoded by the add-on, too)."""
    from homeassistant.components import tts

    engine = engine or tts.async_default_engine(hass)
    if not engine:
        raise HomeAssistantError("Keine Sprachausgabe (TTS) in Home Assistant eingerichtet")
    language = tts_language(hass, engine, language)
    wunsch = {"preferred_format": "wav", "preferred_sample_rate": 48000, "preferred_sample_channels": 1}
    for options in (wunsch, None):
        try:
            media_id = tts.generate_media_source_id(hass, message, engine=engine, language=language, options=options)
            ext, data = await tts.async_get_media_source_audio(hass, media_id)
        except HomeAssistantError:
            if options is None:
                raise
            continue
        return data, ext
    raise HomeAssistantError("Sprachausgabe fehlgeschlagen")  # pragma: no cover


def tts_language(hass: HomeAssistant, engine: str, language: str | None) -> str | None:
    """The language to speak in: the one asked for, else Home Assistant's own
    (Settings → System → General) – matched to what the engine offers.

    Without it the engine used its default, often English, and read the
    German text with a funny accent."""
    from homeassistant.util import language as language_util

    wunsch = language or hass.config.language
    try:
        from homeassistant.components.tts import get_engine_instance

        instance = get_engine_instance(hass, engine)
        angebot = list(getattr(instance, "supported_languages", None) or [])
    except Exception:  # noqa: BLE001 – older Home Assistant: keep what we have
        return language
    if not wunsch or not angebot:
        return language
    if wunsch in angebot:
        return wunsch
    treffer = language_util.matches(wunsch, angebot, country=hass.config.country)
    return treffer[0] if treffer else language


def output_payload(output: str) -> dict:
    """``local`` = Mini-PC speakers, ``none`` = only browsers/stream,
    otherwise the entity id of a Home Assistant media player."""
    output = output.strip()
    if output in ("local", "mini-pc", "host"):
        return {"local_output": True, "speaker": None}
    if output in ("none", "browser", "off", ""):
        return {"local_output": False, "speaker": None}
    if not output.startswith("media_player."):
        raise HomeAssistantError(f"Unbekannte Ausgabe: {output}")
    return {"local_output": False, "speaker": output}


async def async_setup_entry(hass: HomeAssistant, entry: YapaiaConfigEntry) -> bool:
    coordinator = YapaiaCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    coordinator.start_push(entry)
    coordinator.speaker = SpeakerSync(hass, coordinator)
    coordinator.speaker.start(entry)
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


class YapaiaStreamView(HomeAssistantView):
    """Proxy of the add-on's MP3 stream so a dashboard can play the radio in
    the browser.  Requires authentication – the card uses a signed URL
    (``auth/sign_path``) because <audio> cannot send an auth header."""

    url = STREAM_URL
    name = "api:yapaia_beat:stream"
    requires_auth = True

    async def get(self, request: web.Request) -> web.StreamResponse:
        coords = _coordinators(request.app["hass"])
        if not coords:
            raise web.HTTPNotFound()
        coord = coords[0]
        timeout = aiohttp.ClientTimeout(total=None, connect=5, sock_read=30)
        try:
            upstream = await coord.session.get(f"{coord.base}/stream.mp3", timeout=timeout)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise web.HTTPBadGateway(text=str(err)) from err
        resp = web.StreamResponse(headers={"Content-Type": "audio/mpeg", "Cache-Control": "no-cache, no-store"})
        try:
            await resp.prepare(request)
            async for chunk in upstream.content.iter_any():
                await resp.write(chunk)
        except (ConnectionResetError, aiohttp.ClientError, asyncio.TimeoutError):
            pass
        finally:
            upstream.close()
        return resp
