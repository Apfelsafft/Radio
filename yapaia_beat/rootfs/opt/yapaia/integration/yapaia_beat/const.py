"""Constants for the Yapaia Beat integration."""

from __future__ import annotations

import json
from pathlib import Path

DOMAIN = "yapaia_beat"
DEFAULT_HOST = "local-yapaia-beat"
DEFAULT_PORT = 8099
CARD_URL = "/yapaia_beat/yapaia-beat-card.js"
CARD_PATH = Path(__file__).parent / "www" / "yapaia-beat-card.js"
# Sendspin client (Music Assistant's audio protocol), loaded by the card on demand
SENDSPIN_URL = "/yapaia_beat/sendspin.js"
SENDSPIN_PATH = Path(__file__).parent / "www" / "sendspin.js"
SENDSPIN_LICENSES_URL = "/yapaia_beat/sendspin.LICENSES.txt"
SENDSPIN_LICENSES_PATH = Path(__file__).parent / "www" / "sendspin.LICENSES.txt"
LOGO_URL = "/api/yapaia_beat/logo/{}"
SLIDE_URL = "/api/yapaia_beat/slide"
STREAM_URL = "/api/yapaia_beat/stream"

VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text())["version"]
