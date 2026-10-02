"""Entry point: ``python3 -m yapaia``."""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from aiohttp import web

from . import ha
from .audio import AudioOutput
from .config import DATA_DIR, VERSION, load_options
from .logos import LogoManager
from .radio import Radio
from .store import Store
from .web import create_app

PORT = int(os.environ.get("YAPAIA_PORT", "8099"))
LEVELS = {"trace": logging.DEBUG, "debug": logging.DEBUG, "info": logging.INFO, "notice": logging.INFO,
          "warning": logging.WARNING, "error": logging.ERROR, "fatal": logging.CRITICAL}  # fmt: skip


async def main() -> None:
    opts = load_options()
    logging.basicConfig(
        level=LEVELS.get(opts.log_level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    log = logging.getLogger("yapaia")
    log.info("Yapaia Beat %s starting", VERSION)

    store = Store(DATA_DIR / "stations.json")
    logos = LogoManager(DATA_DIR / "logos", opts.logo_lookup_online, opts.country_code)
    audio = AudioOutput(opts.audio_output == "local", opts.mp3_bitrate, opts.default_volume)
    audio.mischer.musik_pegel = max(0, min(100, opts.announce_music_level)) / 100
    radio = Radio(opts, store, logos, audio)

    runner = web.AppRunner(create_app(radio), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    log.info("Web interface listening on port %d (local audio: %s)", PORT, audio.local)

    if opts.install_integration:
        try:
            if ha.install_integration():
                await ha.notify(
                    "Yapaia Beat",
                    "Die Yapaia Beat Integration wurde installiert bzw. aktualisiert. "
                    "Bitte **Home Assistant neu starten**, danach erscheint Yapaia Beat unter "
                    "*Einstellungen → Geräte & Dienste* als entdecktes Gerät.",
                )
        except OSError as err:
            log.error("Could not install integration: %s", err)
    await ha.announce(PORT)

    await radio.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    log.info("Shutting down")
    await radio.shutdown()
    await logos.close()
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
