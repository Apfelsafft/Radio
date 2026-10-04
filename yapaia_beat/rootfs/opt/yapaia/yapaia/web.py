"""HTTP API, web UI (Home Assistant ingress), websocket push and MP3 stream."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from typing import Any

from aiohttp import WSMsgType, web

from .config import APP_DIR, VERSION
from .ansage import PRIORITAETEN, dekodiere
from .icy import IcyWriter, icy_name, jetzt_titel
from .radio import Radio
from .store import display_name, normalize_name

_LOGGER = logging.getLogger(__name__)
WWW = APP_DIR / "www"

routes = web.RouteTableDef()


def _radio(request: web.Request) -> Radio:
    return request.app["radio"]


async def _json(request: web.Request) -> dict[str, Any]:
    if not request.can_read_body:
        return {}
    try:
        data = await request.json()
    except ValueError as err:
        raise web.HTTPBadRequest(text="invalid json") from err
    return data if isinstance(data, dict) else {}


def _ok(**extra: Any) -> web.Response:
    return web.json_response({"ok": True, **extra})


@web.middleware
async def errors(request: web.Request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except KeyError as err:
        return web.json_response({"ok": False, "error": f"Unbekannter Sender: {err}"}, status=404)
    except (ValueError, RuntimeError) as err:
        return web.json_response({"ok": False, "error": str(err)}, status=400)


# ---------------------------------------------------------------------- UI
@routes.get("/")
async def index(request: web.Request) -> web.StreamResponse:
    html = (WWW / "index.html").read_text().replace("{{VERSION}}", VERSION)
    return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------------- status
@routes.get("/api/status")
async def status(request: web.Request) -> web.Response:
    return web.json_response(_radio(request).status())


@routes.get("/api/info")
async def info(request: web.Request) -> web.Response:
    return web.json_response({"name": "Yapaia Beat", "version": VERSION})


@routes.get("/api/ws")
async def websocket(request: web.Request) -> web.WebSocketResponse:
    radio = _radio(request)
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    queue = radio.subscribe()
    await ws.send_str(json.dumps(radio.status(), ensure_ascii=False))

    async def pump() -> None:
        while True:
            await ws.send_str(await queue.get())

    task = asyncio.create_task(pump())
    try:
        async for msg in ws:
            if msg.type == WSMsgType.ERROR:
                break
    finally:
        task.cancel()
        radio.unsubscribe(queue)
    return ws


# ---------------------------------------------------------------------- stations
@routes.get("/api/stations")
async def stations(request: web.Request) -> web.Response:
    radio = _radio(request)
    q = request.query.get("q", "").strip()
    band = request.query.get("band")
    result = []
    freq_query = None
    with contextlib.suppress(ValueError):
        freq_query = float(q.replace(",", ".")) if q else None
    norm = normalize_name(q)
    candidates = [s for s in radio.sorted_stations() if band not in ("fm", "dab") or s["band"] == band]

    def name_match(st: dict[str, Any]) -> bool:
        return bool(norm) and (
            norm in normalize_name(display_name(st)) or norm in normalize_name(st.get("name", ""))
        )

    # the ensemble name is only searched when no station name matches
    by_ensemble = bool(norm) and not any(name_match(s) for s in candidates)
    for st in candidates:
        if q:
            match = name_match(st) or (by_ensemble and norm in normalize_name(st.get("ensemble") or ""))
            if not match and freq_query is not None and st["band"] == "fm":
                match = any(
                    abs(f["freq"] - freq_query) < 0.051 or f"{f['freq']:.2f}".startswith(q.replace(",", "."))
                    for f in st.get("freqs", [])
                )
            if not match and st["band"] == "dab" and (st.get("channel") or "").lower() == q.lower():
                match = True
            if not match:
                continue
        result.append(radio.station_info(st))
    return web.json_response(result)


@routes.post("/api/play")
async def play(request: web.Request) -> web.Response:
    radio = _radio(request)
    data = await _json(request)
    if data.get("id"):
        await radio.play(str(data["id"]))
    elif data.get("frequency"):
        await radio.tune_fm(float(str(data["frequency"]).replace(",", ".")))
    elif data.get("name"):
        matches = radio.store.find_by_name(str(data["name"]))
        if not matches:
            raise KeyError(data["name"])
        await radio.play(matches[0]["id"])
    elif radio.station and not radio.station.get("transient"):
        await radio.play(radio.station["id"])
    elif radio.station:
        await radio.tune_fm(radio.station["freq"])
    else:
        await radio.step(1)
    return _ok()


@routes.post("/api/stop")
async def stop(request: web.Request) -> web.Response:
    await _radio(request).stop()
    return _ok()


@routes.post("/api/next")
async def next_station(request: web.Request) -> web.Response:
    await _radio(request).step(1)
    return _ok()


@routes.post("/api/previous")
async def previous_station(request: web.Request) -> web.Response:
    await _radio(request).step(-1)
    return _ok()


@routes.post("/api/seek")
async def seek(request: web.Request) -> web.Response:
    data = await _json(request)
    await _radio(request).seek_fm(1 if data.get("direction", "up") == "up" else -1)
    return _ok()


@routes.post("/api/volume")
async def volume(request: web.Request) -> web.Response:
    data = await _json(request)
    radio = _radio(request)
    vol = data.get("volume")
    if "step" in data:
        vol = radio.audio.volume + int(data["step"])
    radio.set_volume(None if vol is None else int(vol), data.get("muted"))
    return _ok(volume=radio.audio.volume, muted=radio.audio.muted)


@routes.post("/api/announce")
async def announce(request: web.Request) -> web.Response:
    """An announcement of another Yapaia module (e.g. Yapaia Go's navigation
    voice): raw WAV/MP3 in the body, mixed into the radio with the music
    turned down.  409 when nobody would hear it – the caller then speaks some
    other way."""
    radio = _radio(request)
    grund = radio.ansage_moeglich()
    if grund:
        return web.json_response({"ok": False, "error": grund}, status=409)
    daten = await request.read()
    if not daten:
        raise ValueError("Keine Audiodaten")
    prioritaet = PRIORITAETEN.get(request.query.get("priority", "hinweis"), 1)
    pcm = await dekodiere(daten, request.query.get("format", ""))
    dauer = radio.audio.mischer.einreihen(pcm, prioritaet)
    return _ok(seconds=round(dauer, 2))


@routes.post("/api/settings")
async def settings(request: web.Request) -> web.Response:
    data = await _json(request)
    radio = _radio(request)
    if "auto_follow" in data:
        radio.set_auto_follow(bool(data["auto_follow"]))
    if "local_output" in data:
        await radio.set_local_output(bool(data["local_output"]))
    if "speaker" in data:
        radio.set_speaker(data["speaker"])
    return _ok(auto_follow=radio.auto_follow, local_output=radio.audio.local_enabled, speaker=radio.speaker)


@routes.post("/api/players")
async def players(request: web.Request) -> web.Response:
    """The integration reports the media players of Home Assistant."""
    data = await _json(request)
    players = data.get("players")
    if not isinstance(players, list):
        raise ValueError("players fehlt")
    ma = data.get("music_assistant")
    _radio(request).set_players(players, ma if isinstance(ma, bool) else None)
    if "error" in data:
        _radio(request).set_speaker_error(data["error"])
    return _ok()


@routes.post("/api/favorites")
async def favorite(request: web.Request) -> web.Response:
    data = await _json(request)
    radio = _radio(request)
    if "order" in data:
        radio.store.order_favorites([str(i) for i in data["order"]])
        radio.changed()
    else:
        radio.set_favorite(str(data["id"]), bool(data.get("favorite", True)))
    return _ok(favorites=radio.store.favorites)


@routes.post("/api/stations/{sid}")
async def update_station(request: web.Request) -> web.Response:
    radio = _radio(request)
    sid = request.match_info["sid"]
    if sid not in radio.store.stations:
        raise KeyError(sid)
    data = await _json(request)
    if "name" in data:
        radio.store.rename(sid, str(data["name"]))
    radio.changed()
    return _ok(station=radio.station_info(radio.store.stations[sid]))


@routes.delete("/api/stations/{sid}")
async def delete_station(request: web.Request) -> web.Response:
    radio = _radio(request)
    radio.store.delete(request.match_info["sid"])
    radio.changed()
    return _ok()


# ---------------------------------------------------------------------- logos
@routes.get("/api/logo/{sid}")
async def logo(request: web.Request) -> web.StreamResponse:
    radio = _radio(request)
    sid = request.match_info["sid"]
    if sid == "current":
        if not radio.station:
            return web.Response(body=radio.logos.placeholder(None), content_type="image/svg+xml")
        sid = radio.station["id"]
    path = None if request.query.get("placeholder") else radio.logos.path(sid)
    headers = {"Cache-Control": "public, max-age=3600"}
    if path:
        return web.FileResponse(path, headers={**headers, "Content-Type": radio.logos.content_type(path)})
    station = radio.store.get(sid) or (radio.station if radio.station and radio.station["id"] == sid else None)
    return web.Response(body=radio.logos.placeholder(station), content_type="image/svg+xml", headers=headers)


@routes.post("/api/stations/{sid}/logo")
async def upload_logo(request: web.Request) -> web.Response:
    radio = _radio(request)
    sid = request.match_info["sid"]
    if sid not in radio.store.stations:
        raise KeyError(sid)
    reader = await request.multipart()
    field = await reader.next()
    if field is None or getattr(field, "name", None) != "file":
        raise ValueError("Feld 'file' fehlt")
    data = await field.read(decode=False)  # type: ignore[union-attr]
    if len(data) > 5_000_000:
        raise ValueError("Datei zu groß (max. 5 MB)")
    radio.logos.save_custom(sid, data, field.headers.get("Content-Type", ""))  # type: ignore[union-attr]
    radio.changed()
    return _ok(station=radio.station_info(radio.store.stations[sid]))


@routes.delete("/api/stations/{sid}/logo")
async def delete_logo(request: web.Request) -> web.Response:
    radio = _radio(request)
    radio.logos.remove_custom(request.match_info["sid"])
    radio.changed()
    return _ok()


@routes.post("/api/stations/{sid}/logo/refresh")
async def refresh_logo(request: web.Request) -> web.Response:
    radio = _radio(request)
    sid = request.match_info["sid"]
    st = radio.store.get(sid)
    if st is None:
        raise KeyError(sid)
    found = await radio.logos.ensure(st, force=True)
    radio.store.save()
    radio.changed()
    return _ok(found=found)


@routes.get("/api/slide")
async def slide(request: web.Request) -> web.Response:
    data = await _radio(request).slide()
    if not data:
        raise web.HTTPNotFound()
    return web.Response(body=data[0], content_type=data[1], headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------------- scan
@routes.post("/api/scan")
async def scan(request: web.Request) -> web.Response:
    data = await _json(request)
    _radio(request).start_scan(str(data.get("band", "all")))
    return _ok()


@routes.post("/api/scan/cancel")
async def scan_cancel(request: web.Request) -> web.Response:
    _radio(request).cancel_scan()
    return _ok()


# ---------------------------------------------------------------------- stream
@routes.get("/stream.mp3")
async def stream(request: web.Request) -> web.StreamResponse:
    radio = _radio(request)
    # players that ask for it (Music Assistant, VLC …) get the current song as
    # ICY metadata – otherwise Music Assistant shows the URL as the title
    icy = IcyWriter() if request.headers.get("Icy-MetaData") == "1" else None
    headers = {"Content-Type": "audio/mpeg", "Cache-Control": "no-cache", "icy-name": icy_name(radio.status())}
    if icy:
        headers["icy-metaint"] = str(icy.metaint)
    resp = web.StreamResponse(headers=headers)
    await resp.prepare(request)
    queue = radio.audio.add_client()
    radio.wake()  # a listener is back → leave standby
    radio.changed()
    titel, titel_zeit = "", 0.0
    try:
        while True:
            chunk = await queue.get()
            if icy:
                jetzt = time.monotonic()
                if jetzt - titel_zeit > 1:
                    titel, titel_zeit = jetzt_titel(radio.status()), jetzt
                chunk = icy.feed(chunk, titel)
            await resp.write(chunk)
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    finally:
        radio.audio.remove_client(queue)
        radio.changed()
    return resp


def create_app(radio: Radio) -> web.Application:
    app = web.Application(middlewares=[errors], client_max_size=6 * 1024 * 1024)
    app["radio"] = radio
    app.add_routes(routes)
    app.router.add_static("/static", WWW, append_version=False)
    return app
