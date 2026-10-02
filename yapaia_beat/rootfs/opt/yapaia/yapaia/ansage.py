"""Announcements mixed into the radio ("ducking").

Other Yapaia modules (e.g. Yapaia Go's navigation voice) send a spoken
announcement; the music is faded down, the announcement is laid on top and the
music comes back afterwards – sample-exact, without stopping anything.  The
speaker keeps receiving one continuous stream, so nothing has to be restarted.

Everything that reaches the speakers passes through ``AudioOutput.write`` –
the local output and the MP3 stream alike – so mixing there covers every way
of listening.
"""

from __future__ import annotations

import asyncio
import io
import wave
from collections import deque
from dataclasses import dataclass

import numpy as np

RATE = 48_000
CHANNELS = 2

# Priorities: a navigation instruction goes before an informational message.
PRIORITAETEN = {"info": 0, "hinweis": 1, "navigation": 2}
MAX_WARTEND = 5


@dataclass
class _Ansage:
    pcm: np.ndarray  # float32, shape (frames, 2), range -1..1
    prioritaet: int
    pos: int = 0

    @property
    def rest(self) -> int:
        return len(self.pcm) - self.pos


class Mischer:
    """Mixes queued announcements into PCM chunks and ducks the music."""

    def __init__(self, musik_pegel: float = 0.2, rampe_s: float = 0.3) -> None:
        self.musik_pegel = min(1.0, max(0.0, musik_pegel))
        self._rampe = max(1, int(RATE * rampe_s))
        self._gain = 1.0  # current music gain
        self._aktuell: _Ansage | None = None
        self._wartend: deque[_Ansage] = deque()

    # ------------------------------------------------------------------
    @property
    def aktiv(self) -> bool:
        """True while an announcement is playing/queued or the music is still ramping."""
        return self._aktuell is not None or bool(self._wartend) or self._gain < 1.0

    def einreihen(self, pcm: np.ndarray, prioritaet: int = 0) -> float:
        """Queue an announcement; returns the seconds until it has been played."""
        a = _Ansage(np.asarray(pcm, dtype=np.float32).reshape(-1, CHANNELS), int(prioritaet))
        # higher priority first, FIFO within the same priority
        liste = list(self._wartend)
        i = next((n for n, w in enumerate(liste) if w.prioritaet < a.prioritaet), len(liste))
        liste.insert(i, a)
        self._wartend = deque(liste[:MAX_WARTEND])
        vorher = (self._aktuell.rest if self._aktuell else 0) + sum(w.rest for w in liste[:i])
        einblenden = 0 if self._aktuell else self._rampe
        return (vorher + einblenden + len(a.pcm) + self._rampe) / RATE

    def mische(self, pcm: bytes) -> bytes:
        """Mix one chunk of 16-bit stereo PCM. Returns the chunk unchanged when idle."""
        if not self.aktiv or not pcm:
            return pcm
        musik = np.frombuffer(pcm, dtype="<i2").astype(np.float32).reshape(-1, CHANNELS) / 32768.0
        n = len(musik)
        gains = np.empty(n, dtype=np.float32)
        ansage = np.zeros((n, CHANNELS), dtype=np.float32)
        schritt = (1.0 - self.musik_pegel) / self._rampe

        i = 0
        while i < n:
            if self._aktuell is None and self._wartend and self._gain <= self.musik_pegel + 1e-6:
                self._aktuell = self._wartend.popleft()  # music is down → start speaking
            if self._aktuell is not None:
                # speaking: music stays down, announcement samples are added
                k = min(n - i, self._aktuell.rest)
                gains[i : i + k] = self._gain = self.musik_pegel
                ansage[i : i + k] = self._aktuell.pcm[self._aktuell.pos : self._aktuell.pos + k]
                self._aktuell.pos += k
                i += k
                if self._aktuell.rest == 0:
                    self._aktuell = None
                continue
            ziel = self.musik_pegel if self._wartend else 1.0
            if abs(self._gain - ziel) < 1e-6:
                gains[i:] = self._gain = ziel
                break
            # ramp towards the target, one sample at a time but vectorised
            richtung = -1.0 if ziel < self._gain else 1.0
            bis_ziel = int(np.ceil(abs(self._gain - ziel) / schritt))
            k = min(n - i, bis_ziel)
            rampe = self._gain + richtung * schritt * np.arange(1, k + 1, dtype=np.float32)
            rampe = np.clip(rampe, min(ziel, self._gain), max(ziel, self._gain))
            gains[i : i + k] = rampe
            self._gain = float(rampe[-1]) if k < bis_ziel else ziel
            i += k

        out = musik * gains[:, None] + ansage
        return (np.clip(out, -1.0, 32767 / 32768) * 32768.0).astype("<i2").tobytes()


# ---------------------------------------------------------------------- decoding
def _resample(x: np.ndarray, rate: int) -> np.ndarray:
    if rate == RATE or len(x) == 0:
        return x
    n = int(round(len(x) * RATE / rate))
    t_alt = np.arange(len(x)) / rate
    t_neu = np.arange(n) / RATE
    return np.stack([np.interp(t_neu, t_alt, x[:, c]) for c in range(x.shape[1])], axis=1).astype(np.float32)


def wav_zu_pcm(daten: bytes) -> np.ndarray:
    """WAV (8/16/32-bit PCM, mono or stereo, any rate) → float32 stereo at 48 kHz."""
    with wave.open(io.BytesIO(daten)) as w:
        kanaele, breite, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        roh = w.readframes(w.getnframes())
    if breite == 1:
        x = (np.frombuffer(roh, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif breite == 2:
        x = np.frombuffer(roh, dtype="<i2").astype(np.float32) / 32768.0
    elif breite == 4:
        x = np.frombuffer(roh, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"WAV mit {breite * 8} Bit wird nicht unterstützt")
    x = x.reshape(-1, kanaele)
    if kanaele == 1:
        x = np.repeat(x, 2, axis=1)
    elif kanaele > 2:
        x = x[:, :2]
    return _resample(x, rate)


async def mp3_zu_pcm(daten: bytes) -> np.ndarray:
    """MP3 → float32 stereo at 48 kHz (via mpg123, which the image ships)."""
    proc = await asyncio.create_subprocess_exec(
        "mpg123", "-q", "-s", "-r", str(RATE), "--stereo", "-e", "s16", "-",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )  # fmt: skip
    out, _ = await asyncio.wait_for(proc.communicate(daten), 20)
    if proc.returncode != 0 or not out:
        raise ValueError("Ansage konnte nicht dekodiert werden (MP3)")
    out = out[: len(out) // 4 * 4]
    return np.frombuffer(out, dtype="<i2").astype(np.float32).reshape(-1, CHANNELS) / 32768.0


async def dekodiere(daten: bytes, format_: str) -> np.ndarray:
    fmt = (format_ or "").lower().lstrip(".")
    if fmt == "wav" or daten[:4] == b"RIFF":
        return wav_zu_pcm(daten)
    if fmt == "mp3" or daten[:3] == b"ID3" or daten[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return await mp3_zu_pcm(daten)
    raise ValueError(f"Audioformat „{format_}“ wird nicht unterstützt (WAV oder MP3)")
