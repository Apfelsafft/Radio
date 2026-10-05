"""Senderwechsel: der Player bekommt den Stream neu, damit er den Namen kennt.

Gemeldet: nach dem Wechsel von SWR3 auf Beats Radio stand in Music Assistant
weiter „SWR3 via Yapaia Beat". Der Player liest den Sendernamen (icy-name)
nur beim Verbinden, und der Live-Stream läuft über den Wechsel hinweg.

Home Assistant ist in dieser Testumgebung nicht installiert; die wenigen
Teile, die ``speaker.py`` braucht, werden hier nachgebildet.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

INTEGRATION = Path(__file__).resolve().parents[1] / "yapaia_beat/rootfs/opt/yapaia/integration/yapaia_beat"


def _stub_homeassistant() -> None:
    def mod(name: str, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        sys.modules[name] = m
        return m

    class NoURLAvailableError(Exception):
        pass

    class Feature:
        PLAY_MEDIA = 1
        TURN_ON = 2
        VOLUME_SET = 4
        VOLUME_MUTE = 8

    mod("homeassistant")
    mod("homeassistant.components")
    mod("homeassistant.components.http")
    mod("homeassistant.components.http.auth", async_sign_path=lambda *a, **k: "/stream?sig=x")
    mod("homeassistant.components.media_player", MediaPlayerEntityFeature=Feature, MediaType=types.SimpleNamespace(MUSIC="music"))
    mod("homeassistant.config_entries", ConfigEntry=object)
    mod(
        "homeassistant.const",
        ATTR_SUPPORTED_FEATURES="supported_features",
        EVENT_STATE_CHANGED="state_changed",
        STATE_OFF="off",
        STATE_UNAVAILABLE="unavailable",
    )
    mod("homeassistant.core", Event=object, HomeAssistant=object, callback=lambda f: f)
    mod("homeassistant.exceptions", HomeAssistantError=Exception)
    mod("homeassistant.helpers")
    mod("homeassistant.helpers.entity_registry", async_get=lambda hass: types.SimpleNamespace(entities={}))
    mod("homeassistant.helpers.network", NoURLAvailableError=NoURLAvailableError, get_url=lambda *a, **k: "http://ha")
    mod("homeassistant.helpers.start", async_at_started=lambda *a: None)


def _load_speaker():
    _stub_homeassistant()
    pkg = types.ModuleType("yapaia_beat_int")
    pkg.__path__ = [str(INTEGRATION)]
    sys.modules["yapaia_beat_int"] = pkg
    for name in ("const", "speaker"):
        spec = importlib.util.spec_from_file_location(f"yapaia_beat_int.{name}", INTEGRATION / f"{name}.py")
        m = importlib.util.module_from_spec(spec)
        sys.modules[f"yapaia_beat_int.{name}"] = m
        spec.loader.exec_module(m)
    return sys.modules["yapaia_beat_int.speaker"]


class FakeHass:
    def __init__(self, loop):
        self.loop = loop
        self.calls = []
        self.states = types.SimpleNamespace(get=lambda e: None)
        self.services = types.SimpleNamespace(async_call=self._call)

    async def _call(self, domain, service, data, blocking=True):
        self.calls.append((service, data.get("entity_id")))

    def async_create_task(self, coro):
        return self.loop.create_task(coro)


def test_neuer_sender_wird_nach_kurzer_zeit_neu_uebergeben_beim_durchschalten_nicht():
    speaker = _load_speaker()
    speaker.REPLAY_AFTER_S = 0.05

    async def run():
        hass = FakeHass(asyncio.get_running_loop())
        coord = types.SimpleNamespace(data={"state": "playing", "station": {"id": "swr3", "name": "SWR3"}})
        sync = speaker.SpeakerSync(hass, coord)
        sync.casting = "media_player.yapaia_browser"
        sync._sent_station = "swr3"

        # Gleicher Sender: nichts.
        sync._station_changed()
        await asyncio.sleep(0.1)
        assert hass.calls == []

        # Schnell durchgeschaltet: nur der letzte zählt, und erst nach der Pause.
        for sid in ("bob", "rockland", "beats"):
            coord.data = {"state": "playing", "station": {"id": sid, "name": sid}}
            sync._station_changed()
            await asyncio.sleep(0.01)
        assert hass.calls == []
        await asyncio.sleep(0.15)
        assert hass.calls == [("play_media", "media_player.yapaia_browser")]
        assert sync._sent_station == "beats"

        # Mit Senderverfolgung („following") gilt dasselbe.
        coord.data = {"state": "following", "station": {"id": "swr1", "name": "SWR1"}}
        sync._station_changed()
        await asyncio.sleep(0.15)
        assert len(hass.calls) == 2

        # Beim Suchen (kein Sender auf Sendung) nicht.
        coord.data = {"state": "tuning", "station": {"id": "x", "name": "x"}}
        sync._station_changed()
        await asyncio.sleep(0.15)
        assert len(hass.calls) == 2

    asyncio.run(run())
