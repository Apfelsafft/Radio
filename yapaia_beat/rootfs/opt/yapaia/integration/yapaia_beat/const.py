"""Constants for the Yapaia Beat integration."""

from __future__ import annotations

import json
from pathlib import Path

DOMAIN = "yapaia_beat"
DEFAULT_HOST = "local-yapaia-beat"
DEFAULT_PORT = 8099
CARD_URL = "/yapaia_beat/yapaia-beat-card.js"
CARD_PATH = Path(__file__).parent / "www" / "yapaia-beat-card.js"
LOGO_URL = "/api/yapaia_beat/logo/{}"
SLIDE_URL = "/api/yapaia_beat/slide"
STREAM_URL = "/api/yapaia_beat/stream"

VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text())["version"]
