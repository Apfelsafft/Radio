"""Audio sink: local playback via the Home Assistant audio system (PulseAudio)
and an MP3 live stream (``/stream.mp3``) for other players.

All sources deliver 48 kHz / 16 bit / stereo PCM.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil

import numpy as np

from .procs import kill

_LOGGER = logging.getLogger(__name__)

RATE = 48_000
CHANNELS = 2


class AudioOutput:
    def __init__(self, local: bool, bitrate: int, volume: int) -> None:
        self.local = local and bool(os.environ.get("PULSE_SERVER") or shutil.which("pacat"))
        self.bitrate = bitrate
        self.volume = max(0, min(100, volume))
        self.muted = False
        self._pacat: asyncio.subprocess.Process | None = None
        self._lame: asyncio.subprocess.Process | None = None
        self._lame_reader: asyncio.Task | None = None
        self._clients: set[asyncio.Queue[bytes]] = set()
        self.level = 0.0

    # ------------------------------------------------------------------
    async def _ensure_pacat(self) -> asyncio.subprocess.Process | None:
        if not self.local:
            return None
        if self._pacat and self._pacat.returncode is None:
            return self._pacat
        try:
            self._pacat = await asyncio.create_subprocess_exec(
                "pacat",
                "--playback",
                "--raw",
                "--format=s16le",
                f"--rate={RATE}",
                f"--channels={CHANNELS}",
                "--latency-msec=250",
                "--client-name=Yapaia Beat",
                "--stream-name=Radio",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            _LOGGER.error("pacat not available, local playback disabled")
            self.local = False
            return None
        return self._pacat

    async def _ensure_lame(self) -> asyncio.subprocess.Process | None:
        if self._lame and self._lame.returncode is None:
            return self._lame
        try:
            self._lame = await asyncio.create_subprocess_exec(
                "lame",
                "-r",
                "-s",
                "48",
                "--bitwidth",
                "16",
                "--signed",
                "--little-endian",
                "-m",
                "j",
                "-b",
                str(self.bitrate),
                "--quiet",
                "-",
                "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            _LOGGER.error("lame not available, MP3 stream disabled")
            return None
        self._lame_reader = asyncio.create_task(self._read_lame(self._lame))
        return self._lame

    async def _read_lame(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stdout
        while True:
            data = await proc.stdout.read(4096)
            if not data:
                return
            for q in list(self._clients):
                if q.qsize() > 64:  # slow client, drop data
                    continue
                q.put_nowait(data)

    # ------------------------------------------------------------------
    async def write(self, pcm: bytes) -> None:
        if not pcm:
            return
        samples = np.frombuffer(pcm, dtype="<i2")
        self.level = 0.7 * self.level + 0.3 * float(np.abs(samples).mean() / 32768.0) if samples.size else 0.0

        if self._clients:
            lame = await self._ensure_lame()
            if lame and lame.stdin and not lame.stdin.is_closing():
                lame.stdin.write(pcm)
                try:
                    await asyncio.wait_for(lame.stdin.drain(), 2)
                except (asyncio.TimeoutError, ConnectionError):
                    await kill(lame)

        if self.local:
            player = await self._ensure_pacat()
            if player and player.stdin and not player.stdin.is_closing():
                gain = 0.0 if self.muted else (self.volume / 100.0) ** 2
                out = (samples.astype(np.float32) * gain).astype("<i2").tobytes()
                player.stdin.write(out)
                try:
                    # the sound card paces the whole receive pipeline
                    await asyncio.wait_for(player.stdin.drain(), 3)
                except (asyncio.TimeoutError, ConnectionError):
                    _LOGGER.warning("Local audio output stalled, restarting")
                    await kill(player)

    async def silence(self, seconds: float = 0.2) -> None:
        await self.write(bytes(int(RATE * seconds) * CHANNELS * 2))

    # ------------------------------------------------------------------
    def add_client(self) -> asyncio.Queue[bytes]:
        q: asyncio.Queue[bytes] = asyncio.Queue()
        self._clients.add(q)
        return q

    def remove_client(self, q: asyncio.Queue[bytes]) -> None:
        self._clients.discard(q)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def stop_local(self) -> None:
        """Release the sound card (called when the radio stops)."""
        if self._pacat:
            await kill(self._pacat)
            self._pacat = None

    async def close(self) -> None:
        await self.stop_local()
        if self._lame:
            await kill(self._lame)
        if self._lame_reader:
            self._lame_reader.cancel()
