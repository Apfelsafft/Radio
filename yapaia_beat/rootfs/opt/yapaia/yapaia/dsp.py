"""FM stereo decoder working on the MPX signal delivered by ``rtl_fm``.

rtl_fm runs with ``-s 192k`` so the MPX baseband has an exact 4:1 ratio to
the 48 kHz audio output.  The decoder is fully stream based (all filters keep
their state between chunks) and only uses numpy/scipy vector operations, so it
runs comfortably on a Raspberry Pi.

Pipeline::

    MPX ──┬─ LP 15k ───────────────────────────────┐ (L+R)/2
          ├─ BP 19k ─ ^2 ─ BP 38k ─ normalise ─┐    │
          │                                     × ─ LP 15k ─ (L-R)/2
          └─────────────────────────────────────┘
          └─ BP 70-90k ─ rms  → noise / signal quality

    L = mono + blend * diff ; R = mono - blend * diff ; ↓4 ; de-emphasis
"""

from __future__ import annotations

import math

import numpy as np
from scipy import signal

MPX_RATE = 192_000
AUDIO_RATE = 48_000
DECIM = MPX_RATE // AUDIO_RATE
MAX_DEVIATION = 75_000.0


class FmStereoDecoder:
    """Decode an FM MPX stream (int16 from rtl_fm) to 48 kHz stereo PCM."""

    def __init__(self, deemphasis_us: float = 50.0) -> None:
        fs = MPX_RATE
        # Audio low pass, shared by the sum and the difference channel so both
        # have exactly the same group delay.
        self._lp = signal.firwin(95, 15_000, fs=fs)
        self._zi_mono = np.zeros(len(self._lp) - 1)
        self._zi_diff = np.zeros(len(self._lp) - 1)

        self._bp19 = signal.butter(2, [18_800, 19_200], "bandpass", fs=fs, output="sos")
        self._zi19 = np.zeros((self._bp19.shape[0], 2))
        self._bp38 = signal.butter(2, [37_600, 38_400], "bandpass", fs=fs, output="sos")
        self._zi38 = np.zeros((self._bp38.shape[0], 2))
        self._bpn = signal.butter(6, [72_000, 92_000], "bandpass", fs=fs, output="sos")
        self._zin = np.zeros((self._bpn.shape[0], 2))

        # Note: the Butterworth band passes are phase neutral at 19/38 kHz
        # (< 1° error), so the regenerated carrier needs no correction.

        tau = deemphasis_us * 1e-6
        alpha = math.exp(-1.0 / (AUDIO_RATE * tau)) if tau > 0 else 0.0
        self._de_b = [1 - alpha]
        self._de_a = [1, -alpha]
        self._zi_de_l = np.zeros(1)
        self._zi_de_r = np.zeros(1)

        self._carrier_amp = 1e-3
        self._blend = 0.0
        self._phase = 0  # decimation phase
        self._pending = np.zeros(0, dtype=np.float64)
        self._first = True

        # public measurements
        self.pilot_level = 0.0  # relative to nominal 9 % pilot injection
        self.noise_rms = 1.0
        self.snr_db = 0.0
        self.stereo = False
        self.force_mono = False

    # ------------------------------------------------------------------
    def process(self, raw: bytes) -> bytes:
        """Take int16 MPX samples, return interleaved int16 stereo @48 kHz."""
        x = np.frombuffer(raw, dtype="<i2").astype(np.float64)
        if self._pending.size:
            x = np.concatenate((self._pending, x))
        usable = (x.size // DECIM) * DECIM
        self._pending = x[usable:]
        x = x[:usable]
        if not x.size:
            return b""

        # rtl_fm scales the phase difference so that x/32768 * fs == deviation
        x *= MPX_RATE / 32768.0 / MAX_DEVIATION

        mono, self._zi_mono = signal.lfilter(self._lp, 1.0, x, zi=self._zi_mono)

        pilot, self._zi19 = signal.sosfilt(self._bp19, x, zi=self._zi19)
        carrier, self._zi38 = signal.sosfilt(self._bp38, pilot * pilot, zi=self._zi38)

        noise, self._zin = signal.sosfilt(self._bpn, x, zi=self._zin)
        nrms = float(np.sqrt(np.mean(noise * noise)) + 1e-9)
        self.noise_rms = nrms if self._first else 0.8 * self.noise_rms + 0.2 * nrms
        pilot_amp = float(np.sqrt(2 * np.mean(pilot * pilot)))
        plev = pilot_amp / 0.09
        self.pilot_level = plev if self._first else 0.8 * self.pilot_level + 0.2 * plev
        self._first = False
        # Noise above the MPX band is independent from programme content and
        # rises quickly when the RF signal gets weak.  Expressed relative to
        # the nominal pilot level so the number is roughly a "pilot SNR".
        self.snr_db = 20 * math.log10(0.09 / self.noise_rms)

        amp = float(np.sqrt(2 * np.mean(carrier * carrier)))
        self._carrier_amp = 0.7 * self._carrier_amp + 0.3 * max(amp, 1e-9)
        carrier = carrier / self._carrier_amp

        diff, self._zi_diff = signal.lfilter(self._lp, 1.0, 2.0 * x * carrier, zi=self._zi_diff)

        pilot_ok = self.pilot_level > 0.35 and not self.force_mono
        target = 0.0
        if pilot_ok:
            # blend to mono on weak signals to suppress stereo noise
            target = min(1.0, max(0.0, (self.snr_db - 12.0) / 12.0))
        self._blend = 0.8 * self._blend + 0.2 * target
        self.stereo = self._blend > 0.5

        diff *= self._blend
        left = (mono + diff)[self._phase :: DECIM]
        right = (mono - diff)[self._phase :: DECIM]

        left, self._zi_de_l = signal.lfilter(self._de_b, self._de_a, left, zi=self._zi_de_l)
        right, self._zi_de_r = signal.lfilter(self._de_b, self._de_a, right, zi=self._zi_de_r)

        out = np.empty(left.size * 2, dtype=np.float64)
        out[0::2] = left
        out[1::2] = right
        out *= 0.9 * 32767
        np.clip(out, -32768, 32767, out=out)
        return out.astype("<i2").tobytes()

    @property
    def quality(self) -> float:
        """Signal quality 0..100 derived from the pilot/noise ratio."""
        return max(0.0, min(100.0, (self.snr_db - 5.0) * 100.0 / 30.0))


def measure_mpx(raw: bytes) -> float:
    """Quick one-shot quality measurement (used while probing frequencies)."""
    dec = FmStereoDecoder()
    dec.process(raw)
    return dec.quality
