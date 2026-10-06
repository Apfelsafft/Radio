"""DAB-Verstärkung: richtige Stufe statt dB, und je Kanal gemessen.

Gemeldet: DAB-Sender werden gefunden, lassen sich aber oft nicht abspielen.
Zwei Ursachen im Code:
- welle-cli erwartet bei ``-g`` die NUMMER einer Verstärkungsstufe (0–28).
  Übergeben wurde der eingestellte Wert in dB; ``-g 40`` gibt es nicht,
  welle-cli schaltete die Automatik ab und blieb auf der kleinsten Stufe.
- Die Automatik von welle-cli verstellt alle 50 ms -- jeder Sprung kann
  einen Aussetzer machen. „DAB-Empfang optimieren“ misst stattdessen feste
  Stufen je Kanal.
"""

import asyncio

from yapaia import dab
from yapaia.config import Options
from yapaia.dab import DabTuner, bewerte
from yapaia.procs import R820T_GAINS_DB, welle_gain_index


def test_db_wird_auf_die_naechste_stufe_abgebildet():
    assert welle_gain_index(40) == R820T_GAINS_DB.index(40.2)
    assert welle_gain_index(49.6) == len(R820T_GAINS_DB) - 1
    assert welle_gain_index(0) == 0
    assert welle_gain_index(100) == len(R820T_GAINS_DB) - 1


def test_reihenfolge_konfiguration_vor_messung_vor_automatik():
    fest = DabTuner(Options(rtl_gain="40"), "5C", gain_index=8)
    assert fest._gain_args() == ["-g", str(welle_gain_index(40))]
    gemessen = DabTuner(Options(rtl_gain="auto"), "5C", gain_index=20)
    assert gemessen._gain_args() == ["-g", "20"]
    automatik = DabTuner(Options(rtl_gain="auto"), "5C")
    assert automatik._gain_args() == []
    assert DabTuner(Options(), "5C", gain_index=-1)._gain_args() == []


def test_bewertung_fic_fehler_vor_snr_und_ohne_sync_ganz_hinten():
    gut = {"synced": True, "fic_per_s": 0.0, "snr": 9.0}
    lauter_aber_fehler = {"synced": True, "fic_per_s": 2.5, "snr": 14.0}
    besserer_snr = {"synced": True, "fic_per_s": 0.0, "snr": 11.0}
    kein_sync = {"synced": False}
    reihe = sorted([lauter_aber_fehler, kein_sync, gut, besserer_snr], key=bewerte)
    assert reihe == [besserer_snr, gut, lauter_aber_fehler, kein_sync]


def test_optimierung_waehlt_je_kanal_die_beste_stufe(monkeypatch):
    async def fake(opts, channel, index, dauer=6.0):
        # Kanal 5C: Stufe 20 am besten; 11A: nichts empfangen
        if channel == "11A":
            return {"index": index, "synced": False}
        return {"index": index, "synced": True, "fic_per_s": 0.0 if index == 20 else 1.0, "snr": 10.0}

    monkeypatch.setattr(dab, "miss_verstaerkung", fake)
    meldungen = []
    res = asyncio.run(dab.optimiere_dab(Options(), ["5C", "11A"], lambda p, m: meldungen.append(m), asyncio.Event()))
    assert res == {"5C": 20}
    assert any("Automatik" in m for m in meldungen)


def test_abbrechen_beendet_die_optimierung(monkeypatch):
    async def fake(opts, channel, index, dauer=6.0):
        return {"index": index, "synced": True, "fic_per_s": 0.0, "snr": 10.0}

    monkeypatch.setattr(dab, "miss_verstaerkung", fake)
    stop = asyncio.Event()
    stop.set()
    assert asyncio.run(dab.optimiere_dab(Options(), ["5C"], lambda p, m: None, stop)) == {}
