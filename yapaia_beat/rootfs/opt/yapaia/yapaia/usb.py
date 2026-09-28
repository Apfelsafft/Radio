"""USB helpers for RTL-SDR sticks: detect and reset a hung stick."""

from __future__ import annotations

import fcntl
import logging
import os
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

# RTL2832U based sticks (Realtek reference IDs, most common clones)
RTL_IDS = {("0bda", "2838"), ("0bda", "2832")}
USBDEVFS_RESET = 0x5514  # _IO('U', 20)
SYSFS = Path("/sys/bus/usb/devices")


def find_sticks() -> list[Path]:
    """Device nodes (/dev/bus/usb/BBB/DDD) of connected RTL-SDR sticks."""
    nodes = []
    for dev in SYSFS.glob("*") if SYSFS.exists() else []:
        try:
            ids = ((dev / "idVendor").read_text().strip(), (dev / "idProduct").read_text().strip())
            if ids not in RTL_IDS:
                continue
            bus = int((dev / "busnum").read_text())
            num = int((dev / "devnum").read_text())
        except (OSError, ValueError):
            continue
        nodes.append(Path(f"/dev/bus/usb/{bus:03d}/{num:03d}"))
    return nodes


def reset_sticks() -> int:
    """USB-reset all RTL-SDR sticks (like unplugging). Returns the count."""
    done = 0
    for node in find_sticks():
        try:
            fd = os.open(node, os.O_WRONLY)
            try:
                fcntl.ioctl(fd, USBDEVFS_RESET, 0)
            finally:
                os.close(fd)
            done += 1
            _LOGGER.warning("USB reset of RTL-SDR stick %s", node)
        except OSError as err:
            _LOGGER.warning("USB reset of %s failed: %s", node, err)
    return done
