"""Send the radio to other Home Assistant media players ("speakers").

The add-on keeps the choice (``speaker`` in its status) so the add-on UI,
the card and the select entity all show the same thing; this module does the
actual work inside Home Assistant:

* reports all media players that can play a URL to the add-on,
* starts the live stream on the chosen player while the radio is on and
  stops it again when the radio is switched off,
* keeps the volume of the radio and the player in sync.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.http.auth import async_sign_path
from homeassistant.components.media_player import MediaPlayerEntityFeature, MediaType
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_SUPPORTED_FEATURES, EVENT_STATE_CHANGED, STATE_OFF, STATE_UNAVAILABLE
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.start import async_at_started

from .const import DOMAIN, STREAM_URL

_LOGGER = logging.getLogger(__name__)

# radio states in which the speaker should be playing
ACTIVE = ("playing", "tuning", "following", "scanning", "error")
STREAM_VALID = timedelta(days=7)
# a new station must play this long before the player gets the stream again
REPLAY_AFTER_S = 3.0
# radio states in which a station is actually on air ("following" = playing
# with station tracking)
PLAYING = ("playing", "following")


class SpeakerSync:
    def __init__(self, hass: HomeAssistant, coordinator: Any) -> None:
        self.hass = hass
        self.coord = coordinator
        self.casting: str | None = None  # player we started the stream on
        self._lock = asyncio.Lock()
        self._busy = False
        self._again = False
        self._ready = False  # Home Assistant has started (all players loaded)
        self._last_volume: int | None = None
        self._last_muted: bool | None = None
        self._push_scheduled = False
        # station the player was last given (see _station_changed)
        self._sent_station: str | None = None
        self._replay: asyncio.TimerHandle | None = None

    # ------------------------------------------------------------------ setup
    def start(self, entry: ConfigEntry) -> None:
        entry.async_on_unload(self.coord.async_add_listener(self._on_radio))
        entry.async_on_unload(self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._on_state, self._is_player))
        entry.async_on_unload(async_at_started(self.hass, self._on_started))

    async def _on_started(self, _hass: HomeAssistant) -> None:
        self._ready = True
        self._on_radio()

    @callback
    def _is_player(self, event_data: Any) -> bool:
        return str(event_data.get("entity_id", "")).startswith("media_player.")

    # ------------------------------------------------------------------ player list
    def players(self) -> list[dict[str, Any]]:
        ours = {
            e.entity_id
            for e in er.async_get(self.hass).entities.values()
            if e.platform == DOMAIN and e.domain == "media_player"
        }
        out = []
        for state in self.hass.states.async_all("media_player"):
            if state.entity_id in ours or state.state == STATE_UNAVAILABLE:
                continue
            if not int(state.attributes.get(ATTR_SUPPORTED_FEATURES) or 0) & MediaPlayerEntityFeature.PLAY_MEDIA:
                continue
            # players of Music Assistant carry this attribute; announcements
            # sent to them are mixed in by Music Assistant itself
            out.append({"entity_id": state.entity_id, "name": state.name, "ma": "mass_player_type" in state.attributes})
        return sorted(out, key=lambda p: p["name"].lower())

    def music_assistant(self) -> bool:
        """Is the Music Assistant integration set up in Home Assistant?"""
        return "music_assistant" in self.hass.config.components

    def _schedule_push(self) -> None:
        if not self._push_scheduled:
            self._push_scheduled = True
            self.hass.async_create_task(self._push_players())

    @staticmethod
    def _reported(data: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"entity_id": p.get("entity_id"), "name": p.get("name"), "ma": bool(p.get("ma"))} for p in data.get("players") or []
        ]

    def _aktuell(self, data: dict[str, Any]) -> bool:
        return self._reported(data) == self.players() and bool(data.get("music_assistant")) == self.music_assistant()

    async def _push_players(self) -> None:
        await asyncio.sleep(1)  # collect bursts of state changes
        self._push_scheduled = False
        players = self.players()
        if self._aktuell(self.coord.data or {}):
            return
        await self._command("/api/players", {"players": players, "music_assistant": self.music_assistant()})

    @callback
    def _on_state(self, event: Event) -> None:
        entity_id = event.data["entity_id"]
        old, new = event.data.get("old_state"), event.data.get("new_state")
        if old is None or new is None or old.name != new.name or (old.state == STATE_UNAVAILABLE) != (new.state == STATE_UNAVAILABLE):
            self._schedule_push()
        if entity_id == self.casting and new is not None and not self._busy:
            self._volume_from_speaker(new.attributes)
        elif entity_id == self._wanted() and new is not None and new.state != STATE_UNAVAILABLE:
            self._on_radio()  # the chosen player is (back) online

    # ------------------------------------------------------------------ radio changes
    @callback
    def _on_radio(self) -> None:
        data = self.coord.data or {}
        if "speaker" not in data or not self._ready:
            return  # add-on too old / players not loaded yet
        if not self._aktuell(data):
            self._schedule_push()  # e.g. the add-on was restarted
        if self._lock.locked():
            self._again = True
        else:
            self.hass.async_create_task(self._sync())

    def _wanted(self) -> str | None:
        """Player that should play the radio right now.  After a failure the
        add-on shows the error until the user picks a speaker again."""
        data = self.coord.data or {}
        speaker = data.get("speaker")
        if not speaker or data.get("state") not in ACTIVE or data.get("speaker_error"):
            return None
        return speaker

    async def _sync(self) -> None:
        async with self._lock:
            self._again = False
            target = self._wanted()
            if target != self.casting:
                self._busy = True
                try:
                    await self._switch(target)
                finally:
                    self._busy = False
            elif self.casting:
                await self._volume_to_speaker()
                self._station_changed()
        if self._again:
            self.hass.async_create_task(self._sync())

    async def _switch(self, target: str | None) -> None:
        old, self.casting = self.casting, target
        if old:
            await self._service("media_stop", old)
        if not target:
            return
        state = self.hass.states.get(target)
        if state is None or state.state == STATE_UNAVAILABLE:
            self.casting = None  # try again when the player shows up
            return
        features = int(state.attributes.get(ATTR_SUPPORTED_FEATURES) or 0)
        if state.state == STATE_OFF and features & MediaPlayerEntityFeature.TURN_ON:
            await self._service("turn_on", target)  # e.g. TVs and AV receivers
        data = self.coord.data or {}
        _LOGGER.info("Sending the radio to %s", target)
        try:
            ok = await self._play(target)
        except NoURLAvailableError:
            await self._fail("Keine Home-Assistant-URL gefunden (Einstellungen → System → Netzwerk)")
            return
        if ok:
            self._sent_station = self._station_key()
        if not ok:
            await self._fail(f"{self._name(target)} konnte den Stream nicht abspielen")
            return
        # take over the volume of the speaker so the slider shows it
        state = self.hass.states.get(target)
        vol = state.attributes.get("volume_level") if state else None
        if isinstance(vol, (int, float)):
            self._last_volume = round(vol * 100)
            if self._last_volume != data.get("volume"):
                await self._command("/api/volume", {"volume": self._last_volume})
        else:
            self._last_volume = data.get("volume")
        self._last_muted = data.get("muted")

    # ------------------------------------------------------------------ station name
    def _station_key(self) -> str | None:
        st = (self.coord.data or {}).get("station") or {}
        return st.get("id") or st.get("name")

    @callback
    def _station_changed(self) -> None:
        """Hand the stream over again once a NEW station plays.

        Reported: after switching from SWR3 to Beats Radio, Music Assistant
        still showed "SWR3 via Yapaia Beat".  The player reads the station
        name (``icy-name``) only when it connects, and the live stream keeps
        running across station changes -- so it never learned the new one.

        Waits until the new station has played for a moment: while scanning
        or skipping through stations this would otherwise restart the player
        for every one of them.
        """
        key = self._station_key()
        data = self.coord.data or {}
        if not key or key == self._sent_station or data.get("state") not in PLAYING:
            if self._replay and (not key or key == self._sent_station):
                self._replay.cancel()
                self._replay = None
            return
        if self._replay:
            self._replay.cancel()
        self._replay = self.hass.loop.call_later(REPLAY_AFTER_S, self._replay_now, key)

    @callback
    def _replay_now(self, key: str) -> None:
        self._replay = None
        data = self.coord.data or {}
        if self._station_key() != key or data.get("state") not in PLAYING or not self.casting:
            return
        self.hass.async_create_task(self._replay_stream(key))

    async def _replay_stream(self, key: str) -> None:
        async with self._lock:
            if not self.casting or self._station_key() != key:
                return
            self._busy = True
            try:
                if await self._play(self.casting):
                    self._sent_station = key
            except NoURLAvailableError:
                pass  # the first hand-over reported this already
            finally:
                self._busy = False

    async def _play(self, target: str) -> bool:
        url = self.stream_url()
        data = self.coord.data or {}
        station = (data.get("station") or {}).get("name") or "Yapaia Beat"
        return await self._service(
            "play_media",
            target,
            {
                "media_content_id": url,
                "media_content_type": MediaType.MUSIC,
                "extra": {"title": station, "metadata": {"title": station, "artist": "Yapaia Beat"}},
            },
        )

    def stream_url(self) -> str:
        """Absolute, signed URL of the live stream for a player in the LAN."""
        base = get_url(self.hass, allow_internal=True, allow_external=True, allow_cloud=False, prefer_external=False)
        path = async_sign_path(self.hass, STREAM_URL, STREAM_VALID, use_content_user=True)
        return f"{base}{path}"

    async def _fail(self, message: str) -> None:
        _LOGGER.warning("Yapaia Beat: %s", message)
        await self._command("/api/players", {"players": self.players(), "error": message})

    # ------------------------------------------------------------------ volume
    async def _volume_to_speaker(self) -> None:
        data = self.coord.data or {}
        target = self.casting
        state = self.hass.states.get(target) if target else None
        if not state:
            return
        features = int(state.attributes.get(ATTR_SUPPORTED_FEATURES) or 0)
        vol, muted = data.get("volume"), data.get("muted")
        if vol is not None and vol != self._last_volume:
            self._last_volume = vol
            if features & MediaPlayerEntityFeature.VOLUME_SET:
                await self._service("volume_set", target, {"volume_level": vol / 100})
        if muted is not None and muted != self._last_muted:
            self._last_muted = muted
            if features & MediaPlayerEntityFeature.VOLUME_MUTE:
                await self._service("volume_mute", target, {"is_volume_muted": muted})

    @callback
    def _volume_from_speaker(self, attrs: dict[str, Any]) -> None:
        vol = attrs.get("volume_level")
        payload: dict[str, Any] = {}
        if isinstance(vol, (int, float)) and round(vol * 100) != self._last_volume:
            self._last_volume = round(vol * 100)
            payload["volume"] = self._last_volume
        muted = attrs.get("is_volume_muted")
        if isinstance(muted, bool) and muted != self._last_muted:
            self._last_muted = muted
            payload["muted"] = muted
        if payload:
            self.hass.async_create_task(self._command("/api/volume", payload))

    # ------------------------------------------------------------------ helpers
    def _name(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        return state.name if state else entity_id

    async def _service(self, service: str, entity_id: str, data: dict[str, Any] | None = None) -> bool:
        try:
            await self.hass.services.async_call(
                "media_player", service, {"entity_id": entity_id, **(data or {})}, blocking=True
            )
        except Exception as err:  # noqa: BLE001 – any integration may fail in its own way
            _LOGGER.warning("media_player.%s on %s failed: %r", service, entity_id, err)
            return False
        return True

    async def _command(self, path: str, payload: dict[str, Any]) -> None:
        try:
            await self.coord.command(path, payload)
        except HomeAssistantError as err:
            _LOGGER.debug("Yapaia Beat command failed: %s", err)
