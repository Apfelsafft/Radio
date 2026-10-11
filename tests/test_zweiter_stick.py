"""Zweiter RTL-SDR-Stick (1.13.0).

Gewünscht: „Ich habe noch einen zweiten rtl-sdr Stick. Können wir den
zusätzlich einbinden um bspw. einen Sendersuchlauf oder Senderverfolgung im
Hintergrund zu ermöglichen? Oder ein schnelles Umschalten zwischen DAB und FM?“

Die Empfänger sind hier Attrappen: es zählt, WELCHER Stick WANN geöffnet und
geschlossen wird und wessen Ton zu hören ist.
"""

import asyncio
import time
import types

import pytest

from yapaia import radio as radio_mod
from yapaia.config import Options
from yapaia.radio import Radio

log: list[str] = []


class FakeTuner:
    def __init__(self, opts, band="fm", freq=None, channel=None, on_pcm=None, sound=True, quality=80.0):
        self.opts, self.band, self.freq, self.channel = opts, band, freq, channel
        self.on_pcm, self.sound = on_pcm, sound
        self.running = False
        self.started = time.monotonic() - 60
        self.quality = quality
        self.error = None
        self.rds = types.SimpleNamespace(af=set(), pi=None)
        self.name = f"{band}:{freq or channel}@{opts.rtl_device_index}"

    async def start(self):
        log.append(f"start {self.name}")
        self.running = True
        if self.sound and self.on_pcm:
            asyncio.get_running_loop().call_later(0.05, lambda: asyncio.ensure_future(self.on_pcm(self.name.encode())))

    async def stop(self):
        log.append(f"stop {self.name}")
        self.running = False

    def status(self):
        return {"band": self.band}


class FakeFm(FakeTuner):
    def __init__(self, opts, freq, on_pcm=None, **kw):
        super().__init__(opts, "fm", freq=freq, on_pcm=on_pcm, **kw)


def make_radio(mode="suche", sticks=2, **kw):
    log.clear()
    opts = Options(second_stick=mode, **kw)
    store = types.SimpleNamespace(
        settings={},
        favorites=[],
        stations={},
        save=lambda: None,
        merge_fm=lambda res: log.append(f"merge fm {len(res)}"),
        merge_dab=lambda res: log.append(f"merge dab {len(res)}"),
        remember_fm_freq=lambda *a: None,
        remember_dab_channel=lambda *a: None,
        get=lambda sid: None,
    )
    heard: list[bytes] = []

    async def write(data):
        heard.append(data)

    audio = types.SimpleNamespace(volume=0, muted=False, local_enabled=True, local=True, client_count=0, write=write)
    logos = types.SimpleNamespace(online=False, has_logo=lambda sid: False, version=lambda sid: 0)
    r = Radio(opts, store, logos, audio)
    r.heard = heard
    radio_mod.find_sticks = lambda: list(range(sticks))
    r.detect_sticks()
    return r


@pytest.fixture(autouse=True)
def _restore(monkeypatch):
    monkeypatch.setattr(radio_mod, "find_sticks", radio_mod.find_sticks)
    monkeypatch.setattr(radio_mod, "FmTuner", FakeFm)
    monkeypatch.setattr(radio_mod, "SWITCH_WAIT", {"fm": 1.0, "dab": 1.0})


# ---------------------------------------------------------------- erkennen
def test_zweiter_stick_wird_erkannt():
    assert make_radio(sticks=1).sticks == [0]
    assert make_radio(sticks=2).sticks == [0, 1]
    assert make_radio(sticks=2, rtl_device_index=1).sticks == [1, 0]
    assert make_radio(mode="aus", sticks=2).sticks == [0]
    r = make_radio(sticks=2)
    assert r.two_sticks and not r.equal_sticks
    assert make_radio(mode="gleichwertig").equal_sticks


# ---------------------------------------------------------------- umschalten
def fm(freq, **kw):
    return lambda o, cb: FakeTuner(o, "fm", freq=freq, on_pcm=cb, **kw)


def test_gleichwertig_neuer_sender_erst_auf_dem_freien_stick_dann_wechsel():
    async def run():
        r = make_radio(mode="gleichwertig")
        await r._bring_up(fm(98.0))
        assert r.tuner.opts.rtl_device_index == 0
        await asyncio.sleep(0.1)
        await r._bring_up(fm(101.1))
        # Der neue lief auf Stick 1 an, BEVOR der alte aufhörte -- keine Lücke.
        assert log.index("start fm:101.1@1") < log.index("stop fm:98.0@0")
        assert r.tuner.opts.rtl_device_index == 1
        # Wieder zurück: jetzt ist Stick 0 der freie.
        await r._bring_up(fm(104.5))
        assert r.tuner.opts.rtl_device_index == 0
        await asyncio.sleep(0.1)
        # Zu hören war nur, wer gerade der Empfänger war.
        assert all(h.decode().startswith(("fm:98.0", "fm:101.1", "fm:104.5")) for h in r.heard)

    asyncio.run(run())


def test_gleichwertig_ohne_ton_vom_neuen_bleibt_es_beim_alten_weg():
    async def run():
        r = make_radio(mode="gleichwertig")
        await r._bring_up(fm(98.0))
        await r._bring_up(fm(101.1, sound=False))
        # Der Versuch auf Stick 1 gab keinen Ton: wie früher auf dem
        # Hörstick neu gestartet.
        assert "start fm:101.1@1" in log and "stop fm:101.1@1" in log
        assert r.tuner.opts.rtl_device_index == 0 and r.tuner.freq == 101.1

    asyncio.run(run())


def test_suche_modus_hoert_immer_auf_dem_ersten_stick():
    async def run():
        r = make_radio(mode="suche")
        await r._bring_up(fm(98.0))
        await r._bring_up(fm(101.1))
        assert log == ["start fm:98.0@0", "stop fm:98.0@0", "start fm:101.1@0"]

    asyncio.run(run())


# ---------------------------------------------------------------- verfolgen
def _spielend(r, quality=10.0):
    st = {"id": "fm-d3d5", "band": "fm", "name": "SWR3", "freq": 98.0, "freqs": [{"freq": 98.0}, {"freq": 101.1}], "pi": "D3D5"}
    r.station = st
    r.state = "playing"
    r.tuner = FakeFm(Options(), 98.0, quality=quality)
    r.tuner.running = True
    r.auto_follow = True
    r._bad_since = time.monotonic() - 60
    return st


def test_verfolgung_sucht_auf_dem_zweiten_stick_und_der_erste_spielt_weiter(monkeypatch):
    async def run():
        r = make_radio(mode="suche")
        st = _spielend(r)
        gemessen = []

        async def probe_fm(opts, f, **kw):
            gemessen.append((opts.rtl_device_index, f, r.tuner.running))
            q = 30.0 if f == 98.0 else 90.0  # Gegenprobe: Stick 1 empfängt wie Stick 0
            return {"freq": f, "quality": q, "pi": "D3D5", "name": "SWR3", "pty": None, "af": []}

        monkeypatch.setattr(radio_mod, "probe_fm", probe_fm)
        await r._check_follow()
        await r._follow_task
        # Gemessen wurde auf Stick 1, während der Empfänger auf Stick 0 lief.
        assert gemessen and all(stick == 1 and lief for stick, _, lief in gemessen)
        assert r.tuner.freq == 101.1 and r.tuner.opts.rtl_device_index == 0
        assert "Umgeschaltet" in r.follow["message"]
        assert r._helper is None

    asyncio.run(run())


def test_zweiter_stick_ohne_antenne_klassisch_verfolgen(monkeypatch):
    async def run():
        r = make_radio(mode="suche")
        st = _spielend(r, quality=30.0)

        async def probe_fm(opts, f, **kw):
            return {"freq": f, "quality": 2.0, "pi": None, "name": None, "pty": None, "af": []}

        klassisch = []

        async def follow(tuner, station):
            klassisch.append(station["id"])

        monkeypatch.setattr(radio_mod, "probe_fm", probe_fm)
        r._follow = follow
        await r._check_follow()
        await r._follow_task
        assert klassisch == [st["id"]]
        assert "Antenne" in r.spare_hint
        assert r.status()["second_stick_hint"] == r.spare_hint

    asyncio.run(run())


def test_verfolgung_hat_vorrang_vor_dem_automatischen_suchlauf():
    async def run():
        r = make_radio(mode="suche")
        _spielend(r)
        r._helper, r._scan_auto = "scan", True
        r.scan["running"] = True
        await r._check_follow()
        assert r._scan_cancel.is_set()
        assert r._follow_task is None  # erst im nächsten Takt, wenn der Stick frei ist

    asyncio.run(run())


# ---------------------------------------------------------------- suchlauf
def test_suchlauf_im_hintergrund_unterbricht_nicht(monkeypatch):
    async def run():
        r = make_radio(mode="suche")
        _spielend(r, quality=80.0)
        benutzt = []

        async def scan(opts, progress, cancel):
            benutzt.append((opts.rtl_device_index, r.tuner.running))
            progress(50, "…")
            return [{"x": 1}]

        monkeypatch.setattr(radio_mod, "scan_fm", scan)
        monkeypatch.setattr(radio_mod, "scan_dab", scan)
        r.start_scan("all")
        assert r.scan["running"]
        r._busy()  # Senderwahl bleibt möglich
        await r._scan_task
        assert benutzt == [(1, True), (1, True)]
        assert "merge fm 1" in log and "merge dab 1" in log
        assert r.state == "playing" and r._helper is None and not r.scan["running"]
        assert not any(e.startswith("stop") for e in log)

    asyncio.run(run())


def test_abgebrochener_automatischer_suchlauf_verwirft_halbe_ergebnisse(monkeypatch):
    async def run():
        r = make_radio(mode="suche")
        _spielend(r, quality=80.0)

        async def scan(opts, progress, cancel):
            cancel.set()
            return [{"x": 1}]

        monkeypatch.setattr(radio_mod, "scan_fm", scan)
        r.start_scan("fm", auto=True)
        await r._scan_task
        assert not any(e.startswith("merge") for e in log)

    asyncio.run(run())


def test_automatischer_suchlauf_nur_beim_hoeren_und_mit_zwei_sticks():
    r = make_radio(mode="suche", sticks=1)
    _spielend(r, quality=80.0)
    r._bg_scan_at = 0
    started = []
    r.start_scan = lambda band, auto=False: started.append((band, auto))
    r._maybe_background_scan()
    assert started == []
    r = make_radio(mode="suche")
    _spielend(r, quality=80.0)
    r._bg_scan_at = 0
    r.start_scan = lambda band, auto=False: started.append((band, auto))
    r._maybe_background_scan()
    assert started == [("all", True)]
    r.state = "idle"
    r._bg_scan_at = 0
    r._maybe_background_scan()
    assert started == [("all", True)]


def test_stopp_waehrend_hintergrund_suchlauf_stoppt_das_radio():
    async def run():
        r = make_radio(mode="suche")
        _spielend(r, quality=80.0)
        r.audio.stop_local = lambda: asyncio.sleep(0)
        r.scan.update(running=True, background=True)
        await r.stop()
        assert r.tuner is None and r.state == "idle"
        assert not r._scan_cancel.is_set()

    asyncio.run(run())
