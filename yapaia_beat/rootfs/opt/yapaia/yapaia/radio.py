"""Radio controller: owns the (single) tuner, playback, scans and station
following."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from typing import Any

from .audio import AudioOutput
from .config import Options
from .dab import DabTuner, dab_candidates, norm_sid, probe_dab, scan_dab, split_dls
from .fm import FM_START, FM_STOP, FmTuner, fm_candidates, probe_fm, rtl_power_sweep, scan_fm
from .logos import LogoManager
from .store import Store, display_name, fm_station_id, normalize_name
from .usb import reset_sticks

_LOGGER = logging.getLogger(__name__)
RECOVER_INTERVAL = 15  # seconds between attempts to get a lost stick back

Tuner = FmTuner | DabTuner


def _hex(code: str | None) -> str | None:
    return code.lower().replace("0x", "").lstrip("0") if code else None


class Radio:
    def __init__(self, opts: Options, store: Store, logos: LogoManager, audio: AudioOutput) -> None:
        self.opts = opts
        self.store = store
        self.logos = logos
        self.audio = audio
        self.tuner: Tuner | None = None
        self.station: dict[str, Any] | None = None
        self.state = "idle"  # idle | tuning | playing | scanning | following | error
        self.error: str | None = None
        self.scan: dict[str, Any] = {"running": False, "band": None, "progress": 0, "message": None, "found": 0}
        self.follow: dict[str, Any] = {"active": False, "message": None, "last_switch": None}
        self.auto_follow = bool(store.settings.get("auto_follow", opts.auto_follow))
        audio.volume = int(store.settings.get("volume", opts.default_volume))
        audio.local_enabled = bool(store.settings.get("local_output", True))
        # other Home Assistant media players (reported by the integration) and
        # the one the radio is sent to ("speaker"); the integration does the casting
        self.players: list[dict[str, Any]] = []
        self.speaker: str | None = store.settings.get("speaker")
        self.speaker_error: str | None = None
        self._listeners: set[asyncio.Queue[str]] = set()
        self._lock = asyncio.Lock()
        self._scan_cancel = asyncio.Event()
        self._scan_task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None
        self._logo_task: asyncio.Task | None = None
        self._bad_since: float | None = None
        self._follow_block_until = 0.0
        self._follow_fails = 0
        self._follow_task: asyncio.Task | None = None
        self._last_json = ""
        self._slide: tuple[int, bytes, str] | None = None
        self._recover_at = 0.0
        self._idle_since: float | None = None
        self._recover_error: str | None = None
        self._recover_tries = 0

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self._monitor_task = asyncio.create_task(self._monitor())
        self.lookup_logos()
        last = self.store.settings.get("last_station")
        if self.opts.resume_last_station and self.store.settings.get("was_playing") and last:
            with contextlib.suppress(Exception):
                if last in self.store.stations:
                    await self.play(last)
                elif isinstance(last, (int, float)):
                    await self.tune_fm(float(last))

    async def shutdown(self) -> None:
        for task in (self._monitor_task, self._scan_task, self._logo_task, self._follow_task):
            if task:
                task.cancel()
        await self._stop_tuner()
        await self.audio.close()

    # ------------------------------------------------------------------ listeners
    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=20)
        self._listeners.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        self._listeners.discard(q)

    def changed(self) -> None:
        payload = json.dumps(self.status(), ensure_ascii=False)
        if payload == self._last_json:
            return
        self._last_json = payload
        for q in list(self._listeners):
            if q.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
            q.put_nowait(payload)

    # ------------------------------------------------------------------ tuner handling
    async def _stop_tuner(self) -> None:
        if self.tuner:
            tuner, self.tuner = self.tuner, None
            await tuner.stop()

    async def _start_fm(self, freq: float) -> None:
        await self._stop_tuner()
        tuner = FmTuner(self.opts, freq, on_pcm=self.audio.write)
        await tuner.start()
        self.tuner = tuner

    async def _start_dab(self, channel: str, sid: str) -> None:
        cur = self.tuner
        if isinstance(cur, DabTuner) and cur.running and cur.channel == channel and cur.has_service(sid):
            await cur.set_service(sid)  # same ensemble: keep the receiver running
            return
        await self._stop_tuner()
        tuner = DabTuner(self.opts, channel, sid, on_pcm=self.audio.write)
        await tuner.start()
        self.tuner = tuner

    def _busy(self) -> None:
        if self.scan["running"]:
            raise RuntimeError("Suchlauf läuft – bitte warten oder abbrechen")

    # ------------------------------------------------------------------ public actions
    async def play(self, station_id: str) -> None:
        self._busy()
        await self._cancel_follow()
        station = self.store.get(station_id)
        if station is None:
            raise KeyError(station_id)
        async with self._lock:
            self.state, self.error = "tuning", None
            self.station = station
            self._reset_follow()
            self.changed()
            if station["band"] == "fm":
                await self._start_fm(station["freq"])
            else:
                await self._start_dab(station["channel"], station["sid"])
            self.state = "playing"
            self._remember(station_id)
        self.lookup_logos([station])
        self.changed()

    async def tune_fm(self, freq: float) -> None:
        """Tune to an arbitrary FM frequency (manual tuning)."""
        self._busy()
        await self._cancel_follow()
        freq = round(float(freq), 2)
        if not FM_START - 0.001 <= freq <= FM_STOP + 0.001:
            raise ValueError("Frequenz muss zwischen 87,5 und 108 MHz liegen")
        known = [
            s for s in self.store.stations.values()
            if s["band"] == "fm" and any(abs(f["freq"] - freq) < 0.01 for f in s.get("freqs", []))
        ]  # fmt: skip
        if known:
            station = known[0]
        else:
            station = {
                "id": fm_station_id(None, freq),
                "band": "fm",
                "name": f"FM {freq:.2f}".rstrip("0").rstrip(".").replace(".", ","),
                "freq": freq,
                "freqs": [{"freq": freq, "quality": 0, "seen": time.time()}],
                "transient": True,
            }
        async with self._lock:
            self.state, self.error = "tuning", None
            self.station = dict(station) if station.get("transient") else station
            self._reset_follow()
            self.changed()
            await self._start_fm(freq)
            self.state = "playing"
            self._remember(station["id"] if not station.get("transient") else freq)
        self.changed()

    async def stop(self) -> None:
        self._recover_error = None
        await self._cancel_follow()
        if self.scan["running"]:
            self.cancel_scan()
            return
        async with self._lock:
            await self._stop_tuner()
            await self.audio.stop_local()
            if self.state != "scanning":
                self.state = "idle"
            self.store.settings["was_playing"] = False
            self.store.save()
        self.changed()

    async def step(self, direction: int) -> None:
        """Next/previous favourite (or station if there are no favourites)."""
        ids = list(self.store.favorites)
        if not ids:
            ids = [s["id"] for s in self.sorted_stations() if s.get("available", True)]
        if not ids:
            return
        cur = self.station["id"] if self.station else None
        idx = ids.index(cur) if cur in ids else (-1 if direction > 0 else 0)
        await self.play(ids[(idx + direction) % len(ids)])

    async def seek_fm(self, direction: int) -> None:
        """Manual FM step tuning (+/- one channel step)."""
        base = self.tuner.freq if isinstance(self.tuner, FmTuner) else FM_START
        step = self.opts.fm_step_khz / 1000.0
        freq = base + direction * step
        if freq > FM_STOP:
            freq = FM_START
        if freq < FM_START:
            freq = FM_STOP
        await self.tune_fm(freq)

    def set_volume(self, volume: int | None = None, muted: bool | None = None) -> None:
        if volume is not None:
            self.audio.volume = max(0, min(100, int(volume)))
            self.store.settings["volume"] = self.audio.volume
            self.store.save()
        if muted is not None:
            self.audio.muted = bool(muted)
        self.changed()

    async def set_local_output(self, enabled: bool) -> None:
        """Sound from the speakers of the Home Assistant host on/off (the
        MP3 stream for browsers keeps running either way)."""
        await self.audio.set_local_enabled(enabled)
        self.store.settings["local_output"] = self.audio.local_enabled
        self.store.save()
        if enabled:
            self.wake()
        self.changed()

    def set_speaker(self, entity_id: str | None) -> None:
        """Send the radio to a Home Assistant media player (None = none)."""
        self.speaker = str(entity_id) if entity_id else None
        self.speaker_error = None
        self.store.settings["speaker"] = self.speaker
        self.store.save()
        if self.speaker:
            self.wake()
        self.changed()

    def set_players(self, players: list[dict[str, Any]]) -> None:
        self.players = [
            {"entity_id": str(p["entity_id"]), "name": str(p.get("name") or p["entity_id"])}
            for p in players
            if isinstance(p, dict) and p.get("entity_id")
        ]
        self.changed()

    def set_speaker_error(self, error: str | None) -> None:
        self.speaker_error = str(error) if error else None
        self.changed()

    # ------------------------------------------------------------------ standby
    def _listening(self) -> bool:
        """Can anybody hear the radio right now?"""
        local = self.audio.local and self.audio.local_enabled
        return local or self.audio.client_count > 0

    async def _check_standby(self) -> None:
        minutes = self.opts.standby_minutes
        if minutes <= 0 or self.state != "playing" or self._listening():
            self._idle_since = None
            return
        now = time.monotonic()
        if self._idle_since is None:
            self._idle_since = now
            return
        if now - self._idle_since < minutes * 60:
            return
        _LOGGER.info("Nobody listening for %d min – standby (receiver off)", minutes)
        async with self._lock:
            await self._stop_tuner()
            self.state = "standby"
            self._idle_since = None
        self.changed()

    def wake(self) -> None:
        """Somebody wants to listen again (browser connects, speakers on)."""
        if self.state == "standby" and self.station and not self._lock.locked():
            st = self.station
            _LOGGER.info("Waking up from standby")

            async def resume() -> None:
                with contextlib.suppress(Exception):
                    if st.get("transient"):
                        await self.tune_fm(st["freq"])
                    else:
                        await self.play(st["id"])

            asyncio.create_task(resume())

    def set_auto_follow(self, enabled: bool) -> None:
        self.auto_follow = bool(enabled)
        self.store.settings["auto_follow"] = self.auto_follow
        self.store.save()
        self._reset_follow()
        self.changed()

    def set_favorite(self, station_id: str, favorite: bool) -> None:
        if station_id not in self.store.stations and self.station and self.station["id"] == station_id:
            # manually tuned station – store it permanently
            st = {k: v for k, v in self.station.items() if k != "transient"}
            if isinstance(self.tuner, FmTuner) and self.tuner.rds.name:
                st["name"] = self.tuner.rds.name
            st["available"] = True
            self.store.stations[station_id] = st
            self.station = st
        self.store.set_favorite(station_id, favorite)
        self.lookup_logos([self.store.stations[station_id]] if station_id in self.store.stations else [])
        self.changed()

    def _remember(self, key: str | float) -> None:
        self.store.settings["last_station"] = key
        self.store.settings["was_playing"] = True
        self.store.save()

    # ------------------------------------------------------------------ scanning
    def start_scan(self, band: str) -> None:
        if self.scan["running"]:
            raise RuntimeError("Suchlauf läuft bereits")
        if band not in ("fm", "dab", "all"):
            raise ValueError("band muss fm, dab oder all sein")
        self._scan_cancel.clear()
        self._scan_task = asyncio.create_task(self._run_scan(band))

    async def _cancel_follow(self) -> None:
        """A user action always wins over a running station-following search
        (which may take half a minute)."""
        task = self._follow_task
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.follow["active"] = False
            _LOGGER.info("Station following interrupted by user action")

    def cancel_scan(self) -> None:
        self._scan_cancel.set()

    async def _run_scan(self, band: str) -> None:
        await self._cancel_follow()
        resume = self.station["id"] if self.station and self.state in ("playing", "following") else None
        self.scan = {"running": True, "band": band, "progress": 0, "message": "Starte Suchlauf …", "found": 0, "error": None}
        async with self._lock:
            await self._stop_tuner()
            self.state = "scanning"
            self.changed()
            bands = ["fm", "dab"] if band == "all" else [band]
            found = 0
            try:
                for i, b in enumerate(bands):
                    def progress(p: float, msg: str, i: int = i) -> None:
                        self.scan["progress"] = round((i * 100 + p) / len(bands))
                        self.scan["message"] = msg
                        self.changed()

                    if b == "fm":
                        res = await scan_fm(self.opts, progress, self._scan_cancel)
                        if not self._scan_cancel.is_set() or res:
                            self.store.merge_fm(res)
                    else:
                        res = await scan_dab(self.opts, progress, self._scan_cancel)
                        if not self._scan_cancel.is_set() or res:
                            self.store.merge_dab(res)
                    found += len(res)
                    self.scan["found"] = found
                self.scan["message"] = (
                    "Suchlauf abgebrochen" if self._scan_cancel.is_set() else f"Suchlauf beendet – {found} Sender gefunden"
                )
            except Exception as err:  # noqa: BLE001 – report any failure to the UI
                _LOGGER.exception("Scan failed")
                self.scan["error"] = str(err)
                self.scan["message"] = f"Fehler: {err}"
            finally:
                self.scan["running"] = False
                self.scan["progress"] = 100
                self.state = "idle"
        self.changed()
        self.lookup_logos()
        if resume and resume in self.store.stations:
            with contextlib.suppress(Exception):
                await self.play(resume)

    # ------------------------------------------------------------------ logos
    def lookup_logos(self, stations: list[dict[str, Any]] | None = None) -> None:
        if not self.logos.online:
            return
        if stations is None:
            favs = set(self.store.favorites)
            stations = sorted(self.store.stations.values(), key=lambda s: s["id"] not in favs)
        todo = [s for s in stations if not s.get("transient") and not self.logos.has_logo(s["id"])]
        if not todo:
            return

        async def run() -> None:
            changed = False
            for st in todo:
                if await self.logos.ensure(st):
                    changed = True
                    self.changed()
            self.store.save()
            if changed:
                self.changed()

        if self._logo_task and not self._logo_task.done():
            if stations is not None and len(todo) <= 2:
                asyncio.create_task(run())
            return
        self._logo_task = asyncio.create_task(run())

    # ------------------------------------------------------------------ slides (DAB)
    async def slide(self) -> tuple[bytes, str] | None:
        if not isinstance(self.tuner, DabTuner):
            return None
        ver = self.tuner.slide_version
        if self._slide and self._slide[0] == ver:
            return self._slide[1], self._slide[2]
        data = await self.tuner.fetch_slide()
        if data:
            self._slide = (ver, data[0], data[1])
        return data

    # ------------------------------------------------------------------ monitor & follow
    async def _monitor(self) -> None:
        while True:
            await asyncio.sleep(1)
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Monitor error")

    async def _tick(self) -> None:
        tuner = self.tuner
        if tuner and self.state == "playing" and not tuner.running:
            if not tuner.error:  # died silently, e.g. stick unplugged
                tuner.error = "Empfänger unerwartet beendet – RTL-SDR Stick prüfen"
            _LOGGER.error("Receiver stopped: %s", tuner.error)
            self.error = tuner.error
            self.state = "error"
            await self._stop_tuner()
            if "Stick" in tuner.error:
                self._recover_error = tuner.error
                self._recover_at = time.monotonic() + RECOVER_INTERVAL
        elif tuner and tuner.running and time.monotonic() - tuner.started > 60:
            self._recover_tries = 0  # healthy again
        if self.state == "error" and self.station and self._recover_error:
            await self._recover()
        if isinstance(tuner, FmTuner) and self.station and self.station.get("transient"):
            self._enrich_transient(tuner)
        if not self._lock.locked():
            await self._check_follow()
            await self._check_standby()
        self.changed()

    async def _recover(self) -> None:
        """The stick vanished or hung (USB hiccup, loose cable in the camper):
        keep retrying the last station until it is back."""
        now = time.monotonic()
        wait = max(0, int(self._recover_at - now))
        base = self._recover_error or ""
        self.error = f"{base} · neuer Versuch in {wait} s"
        if now < self._recover_at or self._lock.locked() or self.scan["running"]:
            return
        self._recover_tries += 1
        self._recover_at = now + RECOVER_INTERVAL
        if self._recover_tries % 4 == 2 and "belegt" in base:
            await asyncio.to_thread(reset_sticks)  # enumerated but not answering
        st = self.station
        _LOGGER.info("Trying to recover the receiver (attempt %d)", self._recover_tries)
        try:
            if st.get("transient"):
                await self.tune_fm(st["freq"])
            else:
                await self.play(st["id"])
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Recovery attempt failed: %s", err)
        if self.state == "playing":
            self.error = None  # the monitor sets it again if the tuner dies
            self._recover_error = None

    def _enrich_transient(self, tuner: FmTuner) -> None:
        pi = tuner.rds.pi
        if pi:
            sid = fm_station_id(pi, tuner.freq)
            if sid in self.store.stations:
                self.station = self.store.stations[sid]
                self.store.remember_fm_freq(sid, tuner.freq, tuner.quality)
                return
            self.station["id"] = sid
            self.station["pi"] = pi
        if tuner.rds.name:
            self.station["name"] = tuner.rds.name

    def _reset_follow(self) -> None:
        self._bad_since = None
        self.follow["active"] = False
        self.follow["message"] = None
        self._follow_fails = 0
        self._follow_block_until = 0.0

    async def _check_follow(self) -> None:
        tuner, st = self.tuner, self.station
        if not (self.auto_follow and self.state == "playing" and tuner and st and tuner.running):
            self._bad_since = None
            return
        now = time.monotonic()
        if now - tuner.started < 10:
            return  # give the receiver time to settle
        if tuner.quality >= self.opts.follow_threshold:
            self._bad_since = None
            return
        if self._bad_since is None:
            self._bad_since = now
            return
        if now - self._bad_since < max(3, self.opts.follow_delay_s) or now < self._follow_block_until:
            return
        if self._follow_task and not self._follow_task.done():
            return
        # separate task, so user actions can interrupt the search right away
        self._follow_task = asyncio.create_task(self._follow(tuner, st))

    async def _follow(self, tuner: Tuner, st: dict[str, Any]) -> None:
        cur_q = tuner.quality
        name = display_name(st)
        _LOGGER.info("Reception of %s poor (%.0f%%) – searching alternative", name, cur_q)
        async with self._lock:
            self.state = "following"
            self.follow.update(active=True, message=f"Empfang schwach – suche {name} …")
            self.changed()
            original = (tuner.band, getattr(tuner, "freq", None), getattr(tuner, "channel", None))
            fm_af = sorted(tuner.rds.af) if isinstance(tuner, FmTuner) else []
            pi = (tuner.rds.pi if isinstance(tuner, FmTuner) else None) or st.get("pi")
            try:
                await self._stop_tuner()
                best = await self._find_alternative(st, original, cur_q, fm_af, pi)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Station following failed: %s", err)
                best = None
            if best:
                station, band, where, q = best
                self.station = station
                if band == "fm":
                    await self._start_fm(where)
                    self.store.remember_fm_freq(station["id"], where, q)
                    loc = f"{where:.1f} MHz".replace(".", ",")
                else:
                    await self._start_dab(where, station["sid"])
                    self.store.remember_dab_channel(station["id"], where, None, q)
                    loc = f"DAB+ Kanal {where}"
                msg = f"Umgeschaltet: {display_name(station)} auf {loc}"
                _LOGGER.info(msg)
                self.follow.update(message=msg, last_switch=time.time())
                self._follow_block_until = time.monotonic() + 30
                self._follow_fails = 0
            else:
                band, freq, channel = original
                if band == "fm":
                    await self._start_fm(freq)
                else:
                    await self._start_dab(channel, st["sid"])
                self.follow["message"] = "Kein besserer Empfang gefunden"
                # every search interrupts the audio – back off 2, 4, 8 … 30 min
                self._follow_block_until = time.monotonic() + min(120 * 2**self._follow_fails, 1800)
                self._follow_fails += 1
            self.state = "playing"
            self.follow["active"] = False
            self._bad_since = None
        self.changed()

    async def _find_alternative(
        self,
        st: dict[str, Any],
        original: tuple[str, float | None, str | None],
        cur_q: float,
        fm_af: list[float],
        pi: str | None,
    ) -> tuple[dict[str, Any], str, Any, float] | None:
        need = max(self.opts.follow_threshold, cur_q + 10)
        band = original[0]
        code = _hex(pi if band == "fm" else st.get("sid"))

        async def try_fm(station: dict[str, Any], freqs: list[float], pi_code: str | None) -> tuple | None:
            best = None
            for f in freqs[:10]:
                self.follow["message"] = f"Prüfe {display_name(station)} auf {f:.1f} MHz …".replace(".", ",", 1)
                self.changed()
                res = await probe_fm(self.opts, f, max_time=3.5, min_time=1.5)
                if pi_code and _hex(res["pi"]) != pi_code:
                    continue
                if res["quality"] >= need and (best is None or res["quality"] > best[3]):
                    best = (station, "fm", f, res["quality"])
            return best

        async def try_dab(station: dict[str, Any], channels: list[str]) -> tuple | None:
            for ch in channels[:6]:
                self.follow["message"] = f"Prüfe {display_name(station)} auf DAB+ {ch} …"
                self.changed()
                res = await probe_dab(self.opts, ch, max_time=8, want_sid=station["sid"])
                if any(norm_sid(s["sid"]) == norm_sid(station["sid"]) for s in res["services"]):
                    if res["quality"] >= need:
                        return (station, "dab", ch, res["quality"])
            return None

        def partners(target_band: str) -> list[dict[str, Any]]:
            norm = normalize_name(display_name(st))
            out = []
            for s in self.store.stations.values():
                if s["band"] != target_band or s["id"] == st["id"]:
                    continue
                other = _hex(s.get("pi") if target_band == "fm" else s.get("sid"))
                if (code and other == code) or (norm and normalize_name(display_name(s)) == norm):
                    out.append(s)
            return out

        if band == "fm":
            cur = original[1]
            freqs: list[float] = []
            for f in fm_af + [x["freq"] for x in st.get("freqs", [])]:
                if abs(f - cur) > 0.01 and f not in freqs:
                    freqs.append(f)
            if res := await try_fm(st, freqs, code):
                return res
            if self.opts.follow_cross_band:
                for other in partners("dab"):
                    if res := await try_dab(other, [c["channel"] for c in other.get("channels", [])]):
                        return res
            if self.opts.follow_full_search and code and cur_q < 20:
                self.follow["message"] = f"Durchsuche FM-Band nach {display_name(st)} …"
                self.changed()
                spectrum = await rtl_power_sweep(self.opts, FM_START - 0.2, FM_STOP + 0.2, 10, seconds=1)
                cands = sorted(fm_candidates(spectrum, self.opts.fm_step_khz, self.opts.fm_scan_threshold_db), key=lambda c: -c[1])
                rest = [f for f, _ in cands if f not in freqs and abs(f - cur) > 0.01]
                if res := await try_fm(st, rest[:12], code):
                    return res
        else:
            cur = original[2]
            channels = [c["channel"] for c in st.get("channels", []) if c["channel"] != cur]
            if res := await try_dab(st, channels):
                return res
            if self.opts.follow_cross_band:
                for other in partners("fm"):
                    freqs = [x["freq"] for x in other.get("freqs", [])]
                    if res := await try_fm(other, freqs, _hex(other.get("pi"))):
                        return res
            if self.opts.follow_full_search and cur_q < 20:
                self.follow["message"] = f"Durchsuche DAB-Band nach {display_name(st)} …"
                self.changed()
                chans = [c for c in await dab_candidates(self.opts) if c != cur and c not in channels]
                if res := await try_dab(st, chans):
                    return res
        return None

    # ------------------------------------------------------------------ status
    def sorted_stations(self) -> list[dict[str, Any]]:
        return sorted(
            self.store.stations.values(),
            key=lambda s: (s["band"], s.get("freq") or 0, normalize_name(display_name(s))),
        )

    def station_info(self, st: dict[str, Any]) -> dict[str, Any]:
        sid = st["id"]
        return {
            "id": sid,
            "name": display_name(st),
            "original_name": st.get("name"),
            "band": st["band"],
            "frequency": st.get("freq"),
            "frequencies": [f["freq"] for f in st.get("freqs", [])],
            "channel": st.get("channel"),
            "ensemble": st.get("ensemble"),
            "pi": st.get("pi"),
            "sid": st.get("sid"),
            "pty": st.get("pty"),
            "available": st.get("available", True),
            "favorite": sid in self.store.favorites,
            "has_logo": self.logos.has_logo(sid),
            "logo_url": f"api/logo/{sid}?v={self.logos.version(sid)}",
            "transient": bool(st.get("transient")),
        }

    def active_favorite(self) -> str | None:
        """Favourite matching the current station – same id, or the same
        programme on the other band (PI == SId, or identical name)."""
        st = self.station
        if not st:
            return None
        if st["id"] in self.store.favorites:
            return st["id"]
        code = _hex(st.get("pi") or st.get("sid"))
        name = normalize_name(display_name(st))
        for fid in self.store.favorites:
            fav = self.store.stations.get(fid)
            if not fav:
                continue
            if code and _hex(fav.get("pi") or fav.get("sid")) == code:
                return fid
            if name and normalize_name(display_name(fav)) == name:
                return fid
        return None

    def status(self) -> dict[str, Any]:
        tuner = self.tuner
        tstat: dict[str, Any] = tuner.status() if tuner else {}
        st = self.station
        title = artist = radiotext = None
        if isinstance(tuner, FmTuner):
            rds = tstat.get("rds") or {}
            title, artist, radiotext = rds.get("title"), rds.get("artist"), rds.get("radiotext")
            if not title and radiotext:  # no RadioText+ → guess from "Artist - Title"
                artist, title = split_dls(radiotext)
        elif isinstance(tuner, DabTuner):
            title, artist, radiotext = tstat.get("title"), tstat.get("artist"), tstat.get("radiotext")
        playing = self.state in ("playing", "following", "tuning")
        return {
            "state": self.state,
            "playing": playing,
            "error": self.error,
            "station": self.station_info(st) if st else None,
            "band": tstat.get("band") or (st or {}).get("band"),
            "frequency": tstat.get("frequency"),
            "channel": tstat.get("channel"),
            "ensemble": tstat.get("ensemble"),
            "signal": tstat.get("signal"),
            "snr": tstat.get("snr"),
            "stereo": tstat.get("stereo"),
            "pty": (tstat.get("rds") or {}).get("pty") or tstat.get("pty") or (st or {}).get("pty"),
            "rds": tstat.get("rds"),
            "dls": tstat.get("dls"),
            "radiotext": radiotext,
            "title": title,
            "artist": artist,
            "slide_version": tstat.get("slide_version"),
            "volume": self.audio.volume,
            "muted": self.audio.muted,
            "local_audio": self.audio.local,
            "local_output": self.audio.local_enabled,
            "stream_clients": self.audio.client_count,
            "speaker": self.speaker,
            "speaker_error": self.speaker_error,
            "players": self.players,
            "auto_follow": self.auto_follow,
            "standby_minutes": self.opts.standby_minutes,
            "follow": dict(self.follow),
            "scan": dict(self.scan),
            "active_favorite": self.active_favorite(),
            "favorites": [self.station_info(self.store.stations[f]) for f in self.store.favorites if f in self.store.stations],
            "station_count": len(self.store.stations),
        }
