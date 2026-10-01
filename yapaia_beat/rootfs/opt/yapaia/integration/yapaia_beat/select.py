"""Favourite selection – usable with the tile card "select options" feature
or the entities card."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import output_payload
from .coordinator import YapaiaCoordinator
from .entity import YapaiaEntity

NO_FAVORITES = "–"
OUT_LOCAL = "Mini-PC"
OUT_NONE = "Nur Browser / Stream"


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([YapaiaFavoriteSelect(entry.runtime_data), YapaiaOutputSelect(entry.runtime_data)])


class YapaiaFavoriteSelect(YapaiaEntity, SelectEntity):
    _attr_icon = "mdi:radio"

    def __init__(self, coordinator: YapaiaCoordinator) -> None:
        super().__init__(coordinator, "favorite", "select")

    def _names(self) -> dict[str, str]:
        """Option label -> station id (labels made unique)."""
        out: dict[str, str] = {}
        for fav in self.coordinator.favorites:
            label = fav["name"]
            if label in out:
                label = f"{label} ({'DAB+' if fav['band'] == 'dab' else 'UKW'})"
            out[label] = fav["id"]
        return out

    @property
    def options(self) -> list[str]:
        return list(self._names()) or [NO_FAVORITES]

    @property
    def current_option(self) -> str | None:
        active = (self.coordinator.data or {}).get("active_favorite")
        for label, sid in self._names().items():
            if sid == active:
                return label
        return None

    @property
    def entity_picture(self) -> str | None:
        return self.coordinator.logo_url(self.coordinator.station)

    async def async_select_option(self, option: str) -> None:
        sid = self._names().get(option)
        if sid:
            await self.coordinator.command("/api/play", {"id": sid})


class YapaiaOutputSelect(YapaiaEntity, SelectEntity):
    """Where the radio is heard: Mini-PC speakers, only browsers, or any
    other media player of Home Assistant (Sonos, Cast, Music Assistant …)."""

    _attr_icon = "mdi:speaker-wireless"

    def __init__(self, coordinator: YapaiaCoordinator) -> None:
        super().__init__(coordinator, "output", "select")

    def _choices(self) -> dict[str, str]:
        data = self.coordinator.data or {}
        out: dict[str, str] = {}
        if data.get("local_audio"):
            out[OUT_LOCAL] = "local"
        out[OUT_NONE] = "none"
        for player in data.get("players") or []:
            label = player.get("name") or player["entity_id"]
            if label in out:
                label = f"{label} ({player['entity_id']})"
            out[label] = player["entity_id"]
        speaker = data.get("speaker")
        if speaker and speaker not in out.values():
            out[speaker] = speaker  # chosen player is currently unavailable
        return out

    @property
    def options(self) -> list[str]:
        return list(self._choices())

    @property
    def current_option(self) -> str | None:
        data = self.coordinator.data or {}
        wanted = data.get("speaker") or ("local" if data.get("local_audio") and data.get("local_output") else "none")
        for label, value in self._choices().items():
            if value == wanted:
                return label
        return None

    async def async_select_option(self, option: str) -> None:
        value = self._choices().get(option)
        if value:
            await self.coordinator.command("/api/settings", output_payload(value))
