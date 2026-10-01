"""Small helpers around external processes."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import time

_LOGGER = logging.getLogger(__name__)


async def kill(
    proc: asyncio.subprocess.Process | None, timeout: float = 3.0, first: int = signal.SIGTERM
) -> None:
    """Stop a process gracefully (``first`` signal), escalate to SIGKILL."""
    if proc is None or proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        if proc.stdin and not proc.stdin.is_closing():
            proc.stdin.close()
        proc.send_signal(first)
    try:
        await asyncio.wait_for(proc.wait(), timeout)
        return
    except asyncio.TimeoutError:
        pass
    if first != signal.SIGTERM:
        with contextlib.suppress(ProcessLookupError):
            proc.terminate()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout)
            return
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(proc.wait(), timeout)


# --------------------------------------------------------------------------
# RTL-SDR access gate
#
# Opening the stick again right after another program released it (or was
# killed in the middle of a USB transfer) can hang the RTL2832U – especially
# behind USB pass-through into a VM.  All SDR programs therefore stop with
# SIGINT (their clean shutdown path) and the next one waits a moment.
# --------------------------------------------------------------------------
DEVICE_COOLDOWN = 1.5
_device_released = 0.0


async def device_ready() -> None:
    """Wait until the stick has rested since the last program released it."""
    wait = _device_released + DEVICE_COOLDOWN - time.monotonic()
    if wait > 0:
        await asyncio.sleep(wait)


def device_released() -> None:
    global _device_released
    _device_released = time.monotonic()


async def stop_sdr(proc: asyncio.subprocess.Process | None) -> None:
    """Stop an SDR program cleanly so it releases the stick properly."""
    if proc is None:
        return
    was_running = proc.returncode is None
    await kill(proc, timeout=4.0, first=signal.SIGINT)
    if was_running or proc.returncode is not None:
        device_released()


async def log_stderr(proc: asyncio.subprocess.Process, name: str, level: int = logging.DEBUG) -> None:
    """Forward stderr lines of a helper process to our log."""
    if proc.stderr is None:
        return
    log = logging.getLogger(f"yapaia.{name}")
    while True:
        line = await proc.stderr.readline()
        if not line:
            return
        log.log(level, "%s", line.decode(errors="replace").rstrip())


def gain_args(flag: str, gain: float | None) -> list[str]:
    return [] if gain is None else [flag, f"{gain:g}"]
