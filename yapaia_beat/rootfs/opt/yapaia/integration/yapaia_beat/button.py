"""Buttons: scans, next/previous favourite, FM seek."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import YapaiaCoordinator
from .entity import YapaiaEntity


@dataclass(frozen=True, kw_only=True)
class YapaiaButtonDescription(ButtonEntityDescription):
    path: str
    payload: dict[str, Any] | None = None


BUTTONS = (
    YapaiaButtonDescription(key="scan_fm", icon="mdi:radar", path="/api/scan", payload={"band": "fm"}, entity_category=EntityCategory.CONFIG),
    YapaiaButtonDescription(key="scan_dab", icon="mdi:radar", path="/api/scan", payload={"band": "dab"}, entity_category=EntityCategory.CONFIG),
    YapaiaButtonDescription(key="scan_all", icon="mdi:radar", path="/api/scan", payload={"band": "all"}, entity_category=EntityCategory.CONFIG),
    YapaiaButtonDescription(key="next", icon="mdi:skip-next", path="/api/next"),
    YapaiaButtonDescription(key="previous", icon="mdi:skip-previous", path="/api/previous"),
    YapaiaButtonDescription(key="seek_up", icon="mdi:chevron-right", path="/api/seek", payload={"direction": "up"}),
    YapaiaButtonDescription(key="seek_down", icon="mdi:chevron-left", path="/api/seek", payload={"direction": "down"}),
    YapaiaButtonDescription(key="favorite_current", icon="mdi:star-plus", path="/api/favorites"),
)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities(YapaiaButton(entry.runtime_data, d) for d in BUTTONS)


class YapaiaButton(YapaiaEntity, ButtonEntity):
    entity_description: YapaiaButtonDescription

    def __init__(self, coordinator: YapaiaCoordinator, description: YapaiaButtonDescription) -> None:
        super().__init__(coordinator, description.key, "button")
        self.entity_description = description

    async def async_press(self) -> None:
        d = self.entity_description
        payload = d.payload
        if d.key == "favorite_current":
            st = self.coordinator.station
            if not st:
                return
            payload = {"id": st["id"], "favorite": not st.get("favorite")}
        await self.coordinator.command(d.path, payload)
