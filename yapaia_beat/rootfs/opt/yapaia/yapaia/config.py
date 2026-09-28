"""Add-on options (``/data/options.json``) with sane defaults."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, fields
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("YAPAIA_DATA", "/data"))
APP_DIR = Path(os.environ.get("YAPAIA_APP", "/opt/yapaia"))
VERSION = os.environ.get("YAPAIA_VERSION", "dev")


@dataclass
class Options:
    log_level: str = "info"
    audio_output: str = "local"  # local | stream
    default_volume: int = 60
    mp3_bitrate: int = 128
    rtl_device_index: int = 0
    rtl_gain: str = "auto"
    ppm_correction: int = 0
    fm_step_khz: int = 100
    fm_scan_threshold_db: float = 8.0
    fm_deemphasis_us: int = 50
    dab_prefilter: bool = True
    auto_follow: bool = True
    follow_threshold: int = 35
    follow_delay_s: int = 8
    follow_cross_band: bool = True
    follow_full_search: bool = True
    logo_lookup_online: bool = True
    country_code: str = "DE"
    resume_last_station: bool = True
    install_integration: bool = True

    @property
    def gain_value(self) -> float | None:
        """Numeric tuner gain or ``None`` for automatic gain."""
        try:
            return float(str(self.rtl_gain).replace(",", "."))
        except ValueError:
            return None


def load_options() -> Options:
    path = DATA_DIR / "options.json"
    opts = Options()
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        _LOGGER.warning("%s not found, using defaults", path)
        return opts
    except ValueError as err:
        _LOGGER.error("Cannot parse %s: %s", path, err)
        return opts
    for f in fields(Options):
        if f.name in raw and raw[f.name] is not None:
            try:
                setattr(opts, f.name, type(getattr(opts, f.name))(raw[f.name]))
            except (TypeError, ValueError):
                _LOGGER.warning("Invalid value for option %s: %r", f.name, raw[f.name])
    return opts
