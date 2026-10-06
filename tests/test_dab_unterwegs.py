"""Unterwegs: eine gemessene feste DAB-Verstärkung gilt nur, solange sie taugt.

Gemeldet: „Denke bitte bei der Funktion daran, dass es für den Einsatz in
einem Wohnmobil gedacht ist. Also das Fahrzeug sich bewegt.“ Die Stufe aus
„DAB-Empfang optimieren“ passt zu dem Ort, an dem gemessen wurde. Wird der
Empfang schlecht, geht es zurück auf die Automatik -- vor der Sendersuche.
"""

import asyncio
import time
import types

from yapaia.config import Options
from yapaia.dab import DabTuner
from yapaia.radio import Radio


def _radio(gains):
    r = Radio.__new__(Radio)
    r.opts = Options()
    r.store = types.SimpleNamespace(settings={"dab_gain": gains}, save=lambda: None)
    r._dab_agc = set()
    return r


def test_gemessene_stufe_ausser_nach_rueckfall():
    r = _radio({"5C": 20, "11A": -1})
    assert r.dab_gain("5C") == 20
    assert r.dab_gain("11A") is None  # Automatik war am besten
    assert r.dab_gain("8D") is None  # nie gemessen
    r._dab_agc.add("5C")
    assert r.dab_gain("5C") is None


def test_schlechter_empfang_mit_fester_stufe_schaltet_erst_auf_automatik():
    async def run():
        r = _radio({"5C": 20})
        r._lock = asyncio.Lock()
        r.state = "playing"
        r.station = {"id": "dab-d3d5", "channel": "5C", "sid": "d3d5", "band": "dab"}
        tuner = DabTuner(Options(), "5C", "d3d5", gain_index=20)
        tuner.running = True
        tuner.started = time.monotonic() - 60
        tuner._quality = 5.0
        r.tuner = tuner
        r._bad_since = time.monotonic() - 60
        r._follow_block_until = 0.0
        r._follow_task = None
        neu = []

        async def restart(st):
            neu.append(st["channel"])

        r._agc_restart = restart
        r.auto_follow = True
        await r._check_follow()
        await asyncio.sleep(0)
        assert "5C" in r._dab_agc
        assert neu == ["5C"]

    asyncio.run(run())
