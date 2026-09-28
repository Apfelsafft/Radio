"""Media player entity – works with the standard media control card."""

from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import LOGO_URL
from .coordinator import YapaiaCoordinator
from .entity import YapaiaEntity

F = MediaPlayerEntityFeature
MEDIA_PREFIX = "yapaia://station/"


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([YapaiaMediaPlayer(entry.runtime_data)])


class YapaiaMediaPlayer(YapaiaEntity, MediaPlayerEntity):
    _attr_name = None
    _attr_media_content_type = MediaType.MUSIC
    _attr_media_image_remotely_accessible = False
    _attr_supported_features = (
        F.PLAY | F.PAUSE | F.STOP | F.VOLUME_SET | F.VOLUME_MUTE | F.VOLUME_STEP | F.SELECT_SOURCE
        | F.NEXT_TRACK | F.PREVIOUS_TRACK | F.PLAY_MEDIA | F.BROWSE_MEDIA | F.TURN_ON | F.TURN_OFF
    )  # fmt: skip

    def __init__(self, coordinator: YapaiaCoordinator) -> None:
        super().__init__(coordinator, "radio", "media_player")

    @property
    def _d(self) -> dict[str, Any]:
        return self.coordinator.data or {}

    # ------------------------------------------------------------------ state
    @property
    def state(self) -> MediaPlayerState:
        st = self._d.get("state")
        if st in ("tuning", "following", "scanning"):
            return MediaPlayerState.BUFFERING
        if self._d.get("playing"):
            return MediaPlayerState.PLAYING
        return MediaPlayerState.IDLE

    @property
    def volume_level(self) -> float | None:
        return (self._d.get("volume") or 0) / 100

    @property
    def is_volume_muted(self) -> bool | None:
        return self._d.get("muted")

    @property
    def media_title(self) -> str | None:
        d = self._d
        if d.get("state") == "scanning":
            return (d.get("scan") or {}).get("message")
        station = (d.get("station") or {}).get("name")
        if not d.get("playing"):
            return station
        return d.get("title") or d.get("radiotext") or station

    @property
    def media_artist(self) -> str | None:
        d = self._d
        station = (d.get("station") or {}).get("name")
        if d.get("playing") and d.get("title") and d.get("artist"):
            return d["artist"]
        return station

    @property
    def media_album_name(self) -> str | None:
        return self.coordinator.location()

    @property
    def media_channel(self) -> str | None:
        return (self._d.get("station") or {}).get("name")

    @property
    def app_name(self) -> str:
        return "Yapaia Beat"

    @property
    def media_image_url(self) -> str | None:
        st = self._d.get("station")
        if not st:
            return None
        return f"{self.coordinator.base}/{st['logo_url']}"

    @property
    def source(self) -> str | None:
        active = self._d.get("active_favorite")
        for fav in self.coordinator.favorites:
            if fav["id"] == active:
                return fav["name"]
        return (self._d.get("station") or {}).get("name")

    @property
    def source_list(self) -> list[str]:
        return [f["name"] for f in self.coordinator.favorites]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._d
        st = d.get("station") or {}
        signal = d.get("signal")
        return {
            "station_id": st.get("id"),
            "station_name": st.get("name"),
            "band": d.get("band"),
            "frequency": d.get("frequency"),
            "channel": d.get("channel"),
            "ensemble": d.get("ensemble"),
            "location": self.coordinator.location(),
            "pi": (d.get("rds") or {}).get("pi") or st.get("pi"),
            "program_type": d.get("pty"),
            "radiotext": d.get("radiotext"),
            "signal": None if signal is None else int(round(signal / 5.0) * 5),
            "stereo": d.get("stereo"),
            "favorite": st.get("favorite"),
            "active_favorite": d.get("active_favorite"),
            "logo": self.coordinator.logo_url(st) if st else None,
            "slide": self.coordinator.slide_url(),
            "auto_follow": d.get("auto_follow"),
            "follow_message": (d.get("follow") or {}).get("message"),
            "scan_running": (d.get("scan") or {}).get("running"),
            "radio_state": d.get("state"),
            "favorites": [
                {
                    "id": f["id"],
                    "name": f["name"],
                    "band": f["band"],
                    "frequency": f.get("frequency"),
                    "channel": f.get("channel"),
                    "logo": self.coordinator.logo_url(f),
                }
                for f in self.coordinator.favorites
            ],
        }

    # ------------------------------------------------------------------ commands
    async def async_media_play(self) -> None:
        await self.coordinator.command("/api/play")

    async def async_media_pause(self) -> None:
        await self.coordinator.command("/api/stop")

    async def async_media_stop(self) -> None:
        await self.coordinator.command("/api/stop")

    async def async_turn_on(self) -> None:
        await self.async_media_play()

    async def async_turn_off(self) -> None:
        await self.async_media_stop()

    async def async_set_volume_level(self, volume: float) -> None:
        await self.coordinator.command("/api/volume", {"volume": round(volume * 100)})

    async def async_mute_volume(self, mute: bool) -> None:
        await self.coordinator.command("/api/volume", {"muted": mute})

    async def async_volume_up(self) -> None:
        await self.coordinator.command("/api/volume", {"step": 5})

    async def async_volume_down(self) -> None:
        await self.coordinator.command("/api/volume", {"step": -5})

    async def async_media_next_track(self) -> None:
        await self.coordinator.command("/api/next")

    async def async_media_previous_track(self) -> None:
        await self.coordinator.command("/api/previous")

    async def async_select_source(self, source: str) -> None:
        for fav in self.coordinator.favorites:
            if fav["name"] == source:
                await self.coordinator.command("/api/play", {"id": fav["id"]})
                return
        await self.coordinator.command("/api/play", {"name": source})

    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        if media_id.startswith(MEDIA_PREFIX):
            await self.coordinator.command("/api/play", {"id": media_id[len(MEDIA_PREFIX) :]})
            return
        try:
            freq = float(media_id.replace(",", "."))
        except ValueError:
            await self.coordinator.command("/api/play", {"name": media_id})
            return
        await self.coordinator.command("/api/play", {"frequency": freq})

    # ------------------------------------------------------------------ browse
    async def async_browse_media(self, media_content_type: str | None = None, media_content_id: str | None = None) -> BrowseMedia:
        folders = {"favorites": "Favoriten", "fm": "UKW (FM)", "dab": "DAB+"}
        if media_content_id in folders:
            if media_content_id == "favorites":
                stations = self.coordinator.favorites
            else:
                stations = await self.coordinator.get_json(f"/api/stations?band={media_content_id}")
            return BrowseMedia(
                media_class=MediaClass.DIRECTORY,
                media_content_id=media_content_id,
                media_content_type="directory",
                title=folders[media_content_id],
                can_play=False,
                can_expand=True,
                children_media_class=MediaClass.CHANNEL,
                children=[self._station_item(s) for s in stations],
            )
        if media_content_id not in (None, "", "root"):
            raise HomeAssistantError(f"Unbekannter Ordner {media_content_id}")
        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id="root",
            media_content_type="directory",
            title="Yapaia Beat",
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.DIRECTORY,
            children=[
                BrowseMedia(
                    media_class=MediaClass.DIRECTORY,
                    media_content_id=key,
                    media_content_type="directory",
                    title=title,
                    can_play=False,
                    can_expand=True,
                )
                for key, title in folders.items()
            ],
        )

    def _station_item(self, st: dict[str, Any]) -> BrowseMedia:
        return BrowseMedia(
            media_class=MediaClass.CHANNEL,
            media_content_id=MEDIA_PREFIX + st["id"],
            media_content_type=MediaType.CHANNEL,
            title=st["name"],
            can_play=True,
            can_expand=False,
            thumbnail=LOGO_URL.format(st["id"]),
        )
