"""DAB/DAB+ reception and scan using ``welle-cli`` in web server mode.

welle-cli decodes the ensemble and offers ``/mux.json`` (ensemble, services,
DLS, SNR), ``/mp3/<sid>`` (live audio) and ``/slide/<sid>`` (MOT slideshow).
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import itertools
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .config import Options
from .fm import rtl_power_sweep
from .procs import gain_args, kill

_LOGGER = logging.getLogger(__name__)

DAB_CHANNELS: dict[str, float] = {
    "5A": 174.928, "5B": 176.640, "5C": 178.352, "5D": 180.064,
    "6A": 181.936, "6B": 183.648, "6C": 185.360, "6D": 187.072,
    "7A": 188.928, "7B": 190.640, "7C": 192.352, "7D": 194.064,
    "8A": 195.936, "8B": 197.648, "8C": 199.360, "8D": 201.072,
    "9A": 202.928, "9B": 204.640, "9C": 206.352, "9D": 208.064,
    "10A": 209.936, "10B": 211.648, "10C": 213.360, "10D": 215.072,
    "11A": 216.928, "11B": 218.640, "11C": 220.352, "11D": 222.064,
    "12A": 223.936, "12B": 225.648, "12C": 227.360, "12D": 229.072,
    "13A": 230.784, "13B": 232.496, "13C": 234.208, "13D": 235.776,
    "13E": 237.488, "13F": 239.200,
}  # fmt: skip

PcmCallback = Callable[[bytes], Awaitable[None]]
_PORTS = itertools.cycle(range(7979, 7990))


def _label(obj: Any) -> str:
    if isinstance(obj, dict):
        obj = obj.get("label")
    return " ".join(str(obj or "").split())


def norm_sid(sid: Any) -> str:
    s = str(sid).lower()
    if not s.startswith("0x"):
        try:
            s = f"0x{int(s):04x}"
        except ValueError:
            pass
    return s


def split_dls(text: str | None) -> tuple[str | None, str | None]:
    """Guess (artist, title) from a DLS text like 'Artist - Title'."""
    if not text:
        return None, None
    # drop prefixes like "SWR3: ", "Jetzt läuft: ", "SWR3 – Jetzt: "
    body = re.sub(r"^[^:]{1,40}:\s+", "", text)
    if body.count(" - ") + body.count(" – ") != 1:
        return None, None
    m = re.match(r"^(.+?)\s+[-–]\s+(.+)$", body)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, None


class DabTuner:
    """welle-cli session on one DAB channel, optionally playing one service."""

    band = "dab"

    def __init__(self, opts: Options, channel: str, sid: str | None = None, on_pcm: PcmCallback | None = None) -> None:
        self.opts = opts
        self.channel = channel
        self.sid = norm_sid(sid) if sid else None
        self.on_pcm = on_pcm
        self.port = next(_PORTS)
        self.base = f"http://127.0.0.1:{self.port}"
        self.mux: dict[str, Any] = {}
        self.error: str | None = None
        self.running = False
        self.slide_version = 0
        self._slide_change = None
        self._proc: asyncio.subprocess.Process | None = None
        self._decoder: asyncio.subprocess.Process | None = None
        self._session: aiohttp.ClientSession | None = None
        self._tasks: list[asyncio.Task] = []
        self._stderr: collections.deque[str] = collections.deque(maxlen=30)
        self._last_audio = 0.0
        self._quality = 0.0
        self._synced = False
        self.started = 0.0

    async def start(self) -> None:
        cmd = [
            "welle-cli",
            "-c", self.channel,
            "-w", str(self.port),
            "-T",
            *gain_args("-g", self.opts.gain_value),
        ]  # fmt: skip
        _LOGGER.debug("Starting %s", " ".join(cmd))
        self._proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
        )
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, connect=3))
        self.running = True
        self.started = time.monotonic()
        self._tasks = [asyncio.create_task(self._read_stderr()), asyncio.create_task(self._poll())]
        if self.sid and self.on_pcm:
            self._tasks.append(asyncio.create_task(self._audio()))

    async def stop(self) -> None:
        self.running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await asyncio.gather(kill(self._decoder), kill(self._proc))
        if self._session:
            await self._session.close()
        self._tasks = []

    # ------------------------------------------------------------------
    async def _read_stderr(self) -> None:
        assert self._proc and self._proc.stderr
        while True:
            line = await self._proc.stderr.readline()
            if not line:
                break
            text = line.decode(errors="replace").rstrip()
            self._stderr.append(text)
            _LOGGER.debug("welle-cli: %s", text)
            if "No valid device found" in text or "usb_claim_interface error" in text:
                # welle-cli would continue with a "Null device" – treat as fatal
                self.error = "Kein RTL-SDR Stick gefunden oder Stick belegt"
                self.running = False
                with contextlib.suppress(ProcessLookupError):
                    self._proc.terminate()
        await self._proc.wait()
        self.running = False
        joined = "\n".join(self._stderr)
        if "No supported devices" in joined or "No valid device found" in joined or "Could not open" in joined:
            self.error = "Kein RTL-SDR Stick gefunden oder Stick belegt"
        elif not self.error and self._proc.returncode not in (0, -15):
            self.error = f"welle-cli wurde beendet (Code {self._proc.returncode})"

    async def _poll(self) -> None:
        assert self._session
        while True:
            try:
                async with self._session.get(f"{self.base}/mux.json", timeout=aiohttp.ClientTimeout(total=3)) as r:
                    if r.status == 200:
                        self.mux = await r.json(content_type=None)
                        self._update_quality()
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                pass
            await asyncio.sleep(1.0)

    def _update_quality(self) -> None:
        snr = self.snr
        q = 0.0 if snr is None else max(0.0, min(100.0, (snr - 3.0) * 100.0 / 12.0))
        if not self.ensemble_label:
            self._quality = min(q, 10.0)
            self._synced = False
            return
        if self.sid and self.on_pcm and self.started_audio and time.monotonic() - self._last_audio > 3:
            q *= 0.5  # audio stalls = reception problems
        # no smoothing across the moment the ensemble got synchronised
        self._quality = 0.7 * self._quality + 0.3 * q if self._synced else q
        self._synced = True
        svc = self.service
        if svc:
            change = (svc.get("mot") or {}).get("lastchange")
            if change and change != self._slide_change:
                self._slide_change = change
                self.slide_version += 1

    async def _audio(self) -> None:
        """Fetch /mp3/<sid>, decode with mpg123 and forward PCM."""
        assert self._session and self.on_pcm
        while self.running:
            if not self.service:
                await asyncio.sleep(0.5)
                continue
            try:
                self._decoder = await asyncio.create_subprocess_exec(
                    "mpg123", "-q", "-s", "-r", "48000", "--stereo", "-e", "s16", "-",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )  # fmt: skip
                reader = asyncio.create_task(self._pcm_out(self._decoder))
                async with self._session.get(f"{self.base}/mp3/{self.sid}") as resp:
                    if resp.status != 200:
                        raise aiohttp.ClientError(f"HTTP {resp.status}")
                    async for chunk in resp.content.iter_any():
                        assert self._decoder.stdin
                        self._decoder.stdin.write(chunk)
                        await self._decoder.stdin.drain()
                reader.cancel()
            except (aiohttp.ClientError, ConnectionError, asyncio.TimeoutError) as err:
                _LOGGER.debug("DAB audio stream interrupted: %s", err)
            finally:
                await kill(self._decoder)
            await asyncio.sleep(1)

    async def _pcm_out(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stdout and self.on_pcm
        while True:
            data = await proc.stdout.read(9600)
            if not data:
                return
            if len(data) & 3:
                data += await proc.stdout.readexactly(4 - (len(data) & 3))
            self._last_audio = time.monotonic()
            await self.on_pcm(data)

    # ------------------------------------------------------------------
    @property
    def started_audio(self) -> bool:
        return self._last_audio > 0

    @property
    def snr(self) -> float | None:
        try:
            return float(self.mux["demodulator"]["snr"])
        except (KeyError, TypeError, ValueError):
            return None

    @property
    def ensemble_label(self) -> str:
        return _label((self.mux.get("ensemble") or {}).get("label"))

    @property
    def services(self) -> list[dict[str, Any]]:
        return [s for s in self.mux.get("services") or [] if isinstance(s, dict)]

    @property
    def service(self) -> dict[str, Any] | None:
        if not self.sid:
            return None
        for s in self.services:
            if norm_sid(s.get("sid")) == self.sid:
                return s
        return None

    @property
    def quality(self) -> float:
        return round(self._quality, 1)

    async def fetch_slide(self) -> tuple[bytes, str] | None:
        if not self._session or not self.sid:
            return None
        try:
            async with self._session.get(f"{self.base}/slide/{self.sid}", timeout=aiohttp.ClientTimeout(total=3)) as r:
                if r.status == 200:
                    return await r.read(), r.headers.get("Content-Type", "image/jpeg")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass
        return None

    def status(self) -> dict[str, Any]:
        svc = self.service or {}
        dls = _label(svc.get("dls"))
        artist, title = split_dls(dls)
        return {
            "band": "dab",
            "channel": self.channel,
            "ensemble": self.ensemble_label or None,
            "signal": self.quality,
            "snr": self.snr,
            "stereo": svc.get("channels") == 2 if svc else None,
            "dls": dls or None,
            "radiotext": dls or None,
            "artist": artist,
            "title": title,
            "pty": svc.get("ptystring") or None,
            "bitrate_mode": svc.get("mode"),
            "samplerate": svc.get("samplerate"),
            "slide_version": self.slide_version,
        }


# ----------------------------------------------------------------------
async def probe_dab(opts: Options, channel: str, max_time: float = 12.0, want_sid: str | None = None) -> dict[str, Any]:
    """Tune to a DAB channel and list its audio services."""
    tuner = DabTuner(opts, channel)
    await tuner.start()
    start = time.monotonic()
    stable_since = None
    last_count = -1
    try:
        while time.monotonic() - start < max_time:
            await asyncio.sleep(0.5)
            if not tuner.running and tuner.error:
                raise RuntimeError(tuner.error)
            elapsed = time.monotonic() - start
            if elapsed > 5 and not tuner.ensemble_label and (tuner.snr or 0) < 4:
                break  # no ensemble on this channel
            audio = [s for s in tuner.services if s.get("url_mp3") and _label(s.get("label"))]
            if want_sid and any(norm_sid(s.get("sid")) == norm_sid(want_sid) for s in audio):
                break
            if len(audio) != last_count:
                last_count, stable_since = len(audio), time.monotonic()
            elif audio and tuner.ensemble_label and time.monotonic() - stable_since > 2.5:
                break
    finally:
        await tuner.stop()
    services = [
        {
            "sid": norm_sid(s.get("sid")),
            "name": _label(s.get("label")),
            "pty": s.get("ptystring") or None,
            "channel": channel,
            "ensemble": tuner.ensemble_label or None,
            "quality": tuner.quality,
        }
        for s in tuner.services
        if s.get("url_mp3") and _label(s.get("label"))
    ]
    return {"channel": channel, "ensemble": tuner.ensemble_label, "quality": tuner.quality, "services": services}


async def dab_candidates(opts: Options) -> list[str]:
    """Pre-select DAB channels with RF energy using a quick rtl_power sweep."""
    if not opts.dab_prefilter:
        return list(DAB_CHANNELS)
    try:
        spectrum = await rtl_power_sweep(opts, 174.0, 240.2, 200, seconds=1)
    except RuntimeError as err:
        if "Stick" in str(err):
            raise
        _LOGGER.warning("DAB prefilter failed (%s), scanning all channels", err)
        return list(DAB_CHANNELS)
    levels: dict[str, float] = {}
    freqs = sorted(spectrum)
    for ch, f in DAB_CHANNELS.items():
        vals = [spectrum[x] for x in freqs if abs(x - f) <= 0.7]
        if vals:
            levels[ch] = sum(vals) / len(vals)
    if not levels:
        return list(DAB_CHANNELS)
    ordered = sorted(levels.values())
    floor = ordered[len(ordered) // 4]
    chans = [ch for ch, lv in levels.items() if lv >= floor + 2.5]
    _LOGGER.info("DAB prefilter: %s", ", ".join(chans) or "-")
    return chans or list(DAB_CHANNELS)


async def scan_dab(
    opts: Options,
    progress: Callable[[float, str], None],
    cancel: asyncio.Event,
) -> list[dict[str, Any]]:
    progress(1, "Messe DAB-Band III …")
    channels = await dab_candidates(opts)
    results: list[dict[str, Any]] = []
    for idx, ch in enumerate(channels):
        if cancel.is_set():
            break
        progress(5 + 95 * idx / max(1, len(channels)), f"Prüfe Kanal {ch} … ({len(results)} gefunden)")
        res = await probe_dab(opts, ch)
        if res["services"]:
            _LOGGER.info("DAB %s (%s): %d services", ch, res["ensemble"], len(res["services"]))
            results.extend(res["services"])
    progress(100, f"DAB-Suchlauf beendet: {len(results)} Sender")
    return results
