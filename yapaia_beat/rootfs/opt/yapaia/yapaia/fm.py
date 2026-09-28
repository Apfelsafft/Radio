"""FM reception (rtl_fm + redsea) and FM band scan (rtl_power)."""

from __future__ import annotations

import asyncio
import collections
import contextlib
import json
import logging
import signal
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .config import Options
from .dsp import MPX_RATE, FmStereoDecoder
from .procs import gain_args, kill
from .usb import reset_sticks

_LOGGER = logging.getLogger(__name__)

FM_START = 87.5
FM_STOP = 108.0
CHUNK_BYTES = MPX_RATE // 20 * 2  # 50 ms of int16 MPX

PcmCallback = Callable[[bytes], Awaitable[None]]


def khz_to_mhz(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v > 10_000:  # kHz
        v /= 1000.0
    if FM_START - 0.1 <= v <= FM_STOP + 0.1:
        return round(v, 2)
    return None


class RdsState:
    """Aggregated RDS information of the tuned station."""

    def __init__(self) -> None:
        self.pi: str | None = None
        self._pi_counter: collections.Counter[str] = collections.Counter()
        self._ps_counter: collections.Counter[str] = collections.Counter()
        self.ps: str | None = None
        self.radiotext: str | None = None
        self.pty: str | None = None
        self.title: str | None = None
        self.artist: str | None = None
        self.af: set[float] = set()
        self.tp = False
        self.ta = False
        self.bler: float | None = None
        self.last_update = 0.0

    def update(self, obj: dict[str, Any]) -> None:
        self.last_update = time.monotonic()
        pi = obj.get("pi")
        if pi:
            self._pi_counter[pi.upper().replace("0X", "0x")] += 1
            best, count = self._pi_counter.most_common(1)[0]
            if count >= 2:
                self.pi = best
        if obj.get("ps"):
            self.ps = obj["ps"].strip()
            if self.ps:
                self._ps_counter[self.ps] += 1
        if obj.get("radiotext"):
            self.radiotext = " ".join(obj["radiotext"].split())
        if obj.get("prog_type"):
            self.pty = obj["prog_type"]
        if "tp" in obj:
            self.tp = bool(obj["tp"])
        if "ta" in obj:
            self.ta = bool(obj["ta"])
        if "bler" in obj:
            try:
                self.bler = float(obj["bler"])
            except (TypeError, ValueError):
                pass
        for key in ("alt_frequencies_a", "partial_alt_frequencies"):
            for f in obj.get(key) or []:
                if (mhz := khz_to_mhz(f)) is not None:
                    self.af.add(mhz)
        afb = obj.get("alt_frequencies_b")
        if isinstance(afb, dict):
            for f in afb.get("same_programme") or []:
                if (mhz := khz_to_mhz(f)) is not None:
                    self.af.add(mhz)
        rtp = obj.get("radiotext_plus")
        if isinstance(rtp, dict):
            for tag in rtp.get("tags") or []:
                ctype, data = tag.get("content-type"), (tag.get("data") or "").strip()
                if not data:
                    continue
                if ctype == "item.title":
                    self.title = data
                elif ctype == "item.artist":
                    self.artist = data

    @property
    def name(self) -> str | None:
        """Station name.  Stations with scrolling PS get the most frequent PS."""
        if not self._ps_counter:
            return None
        best, count = self._ps_counter.most_common(1)[0]
        return best if count >= 2 or len(self._ps_counter) == 1 else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "pi": self.pi,
            "ps": self.ps,
            "radiotext": self.radiotext,
            "pty": self.pty,
            "title": self.title,
            "artist": self.artist,
            "af": sorted(self.af),
            "tp": self.tp,
            "ta": self.ta,
            "bler": self.bler,
        }


class FmTuner:
    """One running rtl_fm/redsea session on one frequency."""

    band = "fm"

    def __init__(self, opts: Options, freq: float, on_pcm: PcmCallback | None = None) -> None:
        self.opts = opts
        self.freq = round(freq, 2)
        self.on_pcm = on_pcm
        self.decoder = FmStereoDecoder(opts.fm_deemphasis_us)
        self.rds = RdsState()
        self.error: str | None = None
        self.started = 0.0
        self._rtl: asyncio.subprocess.Process | None = None
        self._redsea: asyncio.subprocess.Process | None = None
        self._tasks: list[asyncio.Task] = []
        self._stderr: collections.deque[str] = collections.deque(maxlen=20)
        self._quality = 0.0
        self.running = False

    async def start(self) -> None:
        cmd = [
            "rtl_fm",
            "-d", str(self.opts.rtl_device_index),
            "-M", "fm",
            "-l", "0",
            "-A", "std",
            "-p", str(self.opts.ppm_correction),
            "-s", str(MPX_RATE),
            "-F", "9",
            *gain_args("-g", self.opts.gain_value),
            "-f", f"{self.freq * 1e6:.0f}",
            "-",
        ]  # fmt: skip
        _LOGGER.debug("Starting %s", " ".join(cmd))
        self._rtl = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            self._redsea = await asyncio.create_subprocess_exec(
                "redsea", "--input", "mpx", "-r", str(MPX_RATE), "-E",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )  # fmt: skip
        except FileNotFoundError:
            _LOGGER.warning("redsea not installed – no RDS")
            self._redsea = None
        self.started = time.monotonic()
        self.running = True
        self._tasks = [
            asyncio.create_task(self._read_mpx()),
            asyncio.create_task(self._read_stderr()),
        ]
        if self._redsea:
            self._tasks.append(asyncio.create_task(self._read_rds()))

    async def stop(self) -> None:
        self.running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(kill(self._rtl), kill(self._redsea))
        self._tasks = []

    # ------------------------------------------------------------------
    async def _read_mpx(self) -> None:
        assert self._rtl and self._rtl.stdout
        rest = b""
        try:
            while True:
                data = await self._rtl.stdout.read(CHUNK_BYTES)
                if not data:
                    break
                data = rest + data
                cut = len(data) & ~1
                data, rest = data[:cut], data[cut:]
                self._feed_redsea(data)
                pcm = self.decoder.process(data)
                q = self.decoder.quality
                if self.rds.bler is not None and time.monotonic() - self.rds.last_update < 3:
                    q = 0.7 * q + 0.3 * max(0.0, 100.0 - self.rds.bler)
                self._quality = 0.9 * self._quality + 0.1 * q if self._quality else q
                if self.on_pcm and pcm:
                    await self.on_pcm(pcm)
        finally:
            self.running = False
            await asyncio.sleep(0.2)  # let stderr reader catch up
            self.error = self._error_from_stderr() or self.error

    def _feed_redsea(self, data: bytes) -> None:
        proc = self._redsea
        if not proc or not proc.stdin or proc.stdin.is_closing() or proc.returncode is not None:
            return
        transport = proc.stdin.transport  # type: ignore[attr-defined]
        if transport.get_write_buffer_size() > 2_000_000:
            return  # redsea too slow – drop instead of blocking audio
        try:
            proc.stdin.write(data)
        except (ConnectionError, RuntimeError):
            pass

    async def _read_rds(self) -> None:
        assert self._redsea and self._redsea.stdout
        while True:
            line = await self._redsea.stdout.readline()
            if not line:
                return
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                self.rds.update(obj)

    async def _read_stderr(self) -> None:
        assert self._rtl and self._rtl.stderr
        while True:
            line = await self._rtl.stderr.readline()
            if not line:
                return
            text = line.decode(errors="replace").rstrip()
            self._stderr.append(text)
            _LOGGER.debug("rtl_fm: %s", text)

    def _error_from_stderr(self) -> str | None:
        text = "\n".join(self._stderr)
        if "No supported devices" in text:
            return "Kein RTL-SDR Stick gefunden"
        if "usb_claim_interface" in text or "Failed to open" in text:
            return "RTL-SDR Stick belegt oder nicht zugreifbar"
        if "cb transfer status" in text or "LIBUSB_ERROR" in text:
            return "Verbindung zum RTL-SDR Stick verloren"
        return None

    # ------------------------------------------------------------------
    @property
    def quality(self) -> float:
        return round(self._quality, 1)

    def status(self) -> dict[str, Any]:
        return {
            "band": "fm",
            "frequency": self.freq,
            "signal": self.quality,
            "snr": round(self.decoder.snr_db, 1),
            "stereo": self.decoder.stereo,
            "rds": self.rds.as_dict(),
        }


# ----------------------------------------------------------------------
async def probe_fm(opts: Options, freq: float, max_time: float = 5.0, min_time: float = 2.0) -> dict[str, Any]:
    """Tune shortly to ``freq`` and return quality + RDS identification."""
    tuner = FmTuner(opts, freq)
    await tuner.start()
    start = time.monotonic()
    try:
        while time.monotonic() - start < max_time:
            await asyncio.sleep(0.25)
            if not tuner.running and tuner.error:
                raise RuntimeError(tuner.error)
            elapsed = time.monotonic() - start
            if elapsed >= min_time and tuner.rds.pi and (tuner.rds.name or elapsed > max_time * 0.7):
                break
            if elapsed >= min_time + 0.5 and not tuner.rds.last_update and tuner.quality < 15:
                break  # nothing there
    finally:
        await tuner.stop()
    return {
        "freq": freq,
        "quality": tuner.quality,
        "pi": tuner.rds.pi,
        "name": tuner.rds.name,
        "pty": tuner.rds.pty,
        "af": sorted(tuner.rds.af),
    }


async def rtl_power_sweep(opts: Options, start_mhz: float, stop_mhz: float, bin_khz: int, seconds: int = 2) -> dict[float, float]:
    """Run a single ``rtl_power`` sweep and return {MHz: dB}.

    rtl_power occasionally hangs (and can take the stick with it), so it gets
    a hard deadline; whatever was measured until then is still used.
    """
    cmd = [
        "rtl_power",
        "-d", str(opts.rtl_device_index),
        "-f", f"{start_mhz}M:{stop_mhz}M:{bin_khz}k",
        "-i", str(seconds),
        "-1",
        "-c", "25%",
        "-p", str(opts.ppm_correction),
        *gain_args("-g", opts.gain_value if opts.gain_value is not None else 30),
        "-",
    ]  # fmt: skip
    _LOGGER.debug("Starting %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    lines: list[str] = []
    err_lines: list[str] = []

    async def read(stream: asyncio.StreamReader, into: list[str]) -> None:
        while line := await stream.readline():
            into.append(line.decode(errors="replace"))

    assert proc.stdout and proc.stderr
    readers = asyncio.gather(read(proc.stdout, lines), read(proc.stderr, err_lines), proc.wait())
    deadline = 25 + seconds * 10
    hung = False
    try:
        await asyncio.wait_for(asyncio.shield(readers), deadline)
    except asyncio.TimeoutError:
        hung = True
        _LOGGER.warning("rtl_power did not finish within %ss – stopping it", deadline)
        with contextlib.suppress(ProcessLookupError):
            proc.send_signal(signal.SIGINT)  # graceful: lets it release the stick
        try:
            await asyncio.wait_for(asyncio.shield(readers), 5)
        except asyncio.TimeoutError:
            await kill(proc)
            readers.cancel()
            reset_sticks()
    text = "".join(err_lines)
    spectrum = _parse_rtl_power("".join(lines))
    if not spectrum:
        if "No supported devices" in text:
            raise RuntimeError("Kein RTL-SDR Stick gefunden")
        if "usb_claim_interface" in text or "Failed to open" in text:
            raise RuntimeError("RTL-SDR Stick belegt oder nicht zugreifbar")
        raise RuntimeError("rtl_power timeout" if hung else f"rtl_power fehlgeschlagen: {text.strip()[-200:]}")
    return spectrum


def _parse_rtl_power(out: str) -> dict[float, float]:
    spectrum: dict[float, float] = {}
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 7:
            continue
        try:
            low = float(parts[2])
            step = float(parts[4])
            values = [float(v) for v in parts[6:] if v and v.lower() != "nan"]
        except ValueError:
            continue
        for i, db in enumerate(values):
            spectrum[round((low + i * step) / 1e6, 4)] = db
    return spectrum


def fm_candidates(spectrum: dict[float, float], step_khz: int, threshold_db: float) -> list[tuple[float, float]]:
    """Find FM channels with a signal peak.  Returns [(MHz, dB above floor)]."""
    if not spectrum:
        return []
    freqs = sorted(spectrum)
    step = step_khz / 1000.0
    channels: list[tuple[float, float]] = []
    f = FM_START
    while f <= FM_STOP + 1e-6:
        vals = [spectrum[x] for x in freqs if abs(x - f) <= 0.06]
        if vals:
            channels.append((round(f, 2), sum(vals) / len(vals)))
        f += step
    if not channels:
        return []
    levels = sorted(v for _, v in channels)
    floor = levels[len(levels) // 5]
    result = []
    for freq, level in channels:
        if level < floor + threshold_db:
            continue
        neighbours = [lv for fq, lv in channels if 0 < abs(fq - freq) <= 0.15 + 1e-6]
        if all(level >= lv for lv in neighbours):
            result.append((freq, round(level - floor, 1)))
    return result


async def scan_fm(
    opts: Options,
    progress: Callable[[float, str], None],
    cancel: asyncio.Event,
) -> list[dict[str, Any]]:
    progress(1, "Messe FM-Band (87,5–108 MHz) …")
    spectrum = await rtl_power_sweep(opts, FM_START - 0.2, FM_STOP + 0.2, 10, seconds=2)
    candidates = fm_candidates(spectrum, opts.fm_step_khz, opts.fm_scan_threshold_db)
    _LOGGER.info("FM scan: %d candidate frequencies", len(candidates))
    results: list[dict[str, Any]] = []
    for idx, (freq, level) in enumerate(candidates):
        if cancel.is_set():
            break
        progress(5 + 95 * idx / max(1, len(candidates)), f"Prüfe {freq:.1f} MHz … ({len(results)} gefunden)")
        try:
            res = await probe_fm(opts, freq)
        except RuntimeError as err:
            _LOGGER.error("FM probe failed: %s", err)
            raise
        res["level"] = level
        if res["pi"] or res["quality"] >= 25:
            if not res["name"]:
                res["name"] = f"FM {freq:.1f}".replace(".", ",")
            _LOGGER.info("FM %.1f MHz: %s (PI %s, %.0f%%)", freq, res["name"], res["pi"], res["quality"])
            results.append(res)
    progress(100, f"FM-Suchlauf beendet: {len(results)} Sender")
    return results
