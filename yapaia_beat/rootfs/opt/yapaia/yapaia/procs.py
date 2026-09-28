"""Small helpers around external processes."""

from __future__ import annotations

import asyncio
import contextlib
import logging

_LOGGER = logging.getLogger(__name__)


async def kill(proc: asyncio.subprocess.Process | None, timeout: float = 3.0) -> None:
    """Terminate a process, escalate to SIGKILL, never raise."""
    if proc is None or proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        if proc.stdin and not proc.stdin.is_closing():
            proc.stdin.close()
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout)


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
