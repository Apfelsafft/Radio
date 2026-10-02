"""Announcements mixed into the radio: music down, announcement on top, music back."""

import asyncio
import io
import wave

import numpy as np
import pytest

from yapaia.ansage import RATE, Mischer, dekodiere, wav_zu_pcm

CHUNK = 4800  # 100 ms


def _musik(sekunden: float, pegel: float = 0.5) -> bytes:
    return (np.full((int(RATE * sekunden), 2), pegel * 32767)).astype("<i2").tobytes()


def _abspielen(m: Mischer, sekunden: float, pegel: float = 0.5) -> np.ndarray:
    roh = _musik(sekunden, pegel)
    out = b"".join(m.mische(roh[i : i + CHUNK * 4]) for i in range(0, len(roh), CHUNK * 4))
    return np.frombuffer(out, "<i2").reshape(-1, 2) / 32767


def test_ohne_ansage_bleibt_alles_wie_es_ist():
    m = Mischer()
    roh = _musik(0.5)
    assert m.mische(roh) is roh
    assert not m.aktiv


def test_musik_leiser_ansage_drueber_musik_wieder_laut():
    m = Mischer(musik_pegel=0.2, rampe_s=0.3)
    ansage = np.full((RATE, 2), 0.25, dtype=np.float32)  # 1 s, konstanter Pegel
    dauer = m.einreihen(ansage)
    assert dauer == pytest.approx(0.3 + 1.0 + 0.3)

    out = _abspielen(m, 3.0)[:, 0]
    # 0,3 s Rampe nach unten, dann 1 s Ansage über leiser Musik, dann 0,3 s nach oben
    assert out[int(0.29 * RATE)] > 0.1
    assert out[int(0.5 * RATE)] == pytest.approx(0.5 * 0.2 + 0.25, abs=1e-3)
    assert out[int(1.25 * RATE)] == pytest.approx(0.35, abs=1e-3)
    assert out[int(2.5 * RATE)] == pytest.approx(0.5, abs=1e-3)
    assert not m.aktiv
    # weich: kein Sprung größer als eine Rampenstufe außerhalb von Ansagebeginn/-ende
    for teil in (out[: int(0.3 * RATE)], out[int(1.31 * RATE) :]):
        assert np.abs(np.diff(teil)).max() < 0.001


def test_navigation_geht_vor_info():
    m = Mischer(musik_pegel=0.0, rampe_s=0.01)
    m.einreihen(np.full((RATE // 10, 2), 0.1, dtype=np.float32), prioritaet=0)
    m.einreihen(np.full((RATE // 10, 2), 0.3, dtype=np.float32), prioritaet=2)
    out = _abspielen(m, 1.0, pegel=0.0)[:, 0]  # Stille: nur die Ansagen sind zu hören
    werte = [round(v, 2) for v in out if v > 0.05]
    assert werte[0] == 0.3 and werte[-1] == 0.1


def test_uebersteuerung_wird_begrenzt():
    m = Mischer(musik_pegel=1.0)
    m.einreihen(np.full((RATE, 2), 0.9, dtype=np.float32))
    out = _abspielen(m, 1.0)
    assert out.max() <= 1.0


def test_wav_mono_22khz_wird_stereo_48khz():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes((np.full(22050, 0.5) * 32767).astype("<i2").tobytes())
    pcm = wav_zu_pcm(buf.getvalue())
    assert pcm.shape == (RATE, 2)
    assert pcm[100, 0] == pytest.approx(0.5, abs=1e-3)
    assert asyncio.run(dekodiere(buf.getvalue(), "")).shape == (RATE, 2)


def test_unbekanntes_format():
    with pytest.raises(ValueError):
        asyncio.run(dekodiere(b"OggS....", "ogg"))
