import numpy as np

from yapaia.dsp import MPX_RATE, FmStereoDecoder


def _mpx_fm(noise: float, seconds: float = 2.0) -> bytes:
    """Stereo MPX (L=1 kHz, R=silence), FM modulated and demodulated like rtl_fm."""
    rng = np.random.default_rng(1)
    n = int(MPX_RATE * seconds)
    t = np.arange(n) / MPX_RATE
    left = 0.8 * np.sin(2 * np.pi * 1000 * t)
    mpx = 0.9 * (left / 2 + left / 2 * np.cos(2 * np.pi * 38000 * t)) + 0.09 * np.cos(2 * np.pi * 19000 * t)
    iq = np.exp(1j * 2 * np.pi * 75000 * np.cumsum(mpx) / MPX_RATE)
    iq += noise * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    d = np.angle(iq[1:] * np.conj(iq[:-1]))
    return (d / np.pi * 16384).astype("<i2").tobytes()


def _decode(raw: bytes) -> tuple[FmStereoDecoder, np.ndarray]:
    dec = FmStereoDecoder()
    out = b"".join(dec.process(raw[i : i + 19200]) for i in range(0, len(raw), 19200))
    return dec, np.frombuffer(out, "<i2").reshape(-1, 2)[48000:] / 32767


def test_stereo_separation_clean_signal():
    dec, audio = _decode(_mpx_fm(0.0))
    sep = 20 * np.log10(audio[:, 0].std() / audio[:, 1].std())
    assert dec.stereo
    assert sep > 30
    assert dec.quality > 80


def test_weak_signal_blends_to_mono_and_reports_low_quality():
    dec, audio = _decode(_mpx_fm(0.2))
    assert not dec.stereo
    assert abs(audio[:, 0].std() - audio[:, 1].std()) < 0.05
    assert dec.quality < 20


def test_output_rate_is_quarter_of_input():
    dec = FmStereoDecoder()
    out = dec.process(bytes(19200 * 2))  # 19200 samples
    assert len(out) == 19200 // 4 * 2 * 2
