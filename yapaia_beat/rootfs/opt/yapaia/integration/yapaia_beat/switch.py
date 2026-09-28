"""Automatic station following on/off."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import YapaiaCoordinator
from .entity import YapaiaEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([YapaiaFollowSwitch(entry.runtime_data), YapaiaMuteSwitch(entry.runtime_data)])


class YapaiaFollowSwitch(YapaiaEntity, SwitchEntity):
    _attr_icon = "mdi:map-marker-path"

    def __init__(self, coordinator: YapaiaCoordinator) -> None:
        super().__init__(coordinator, "auto_follow", "switch")

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get("auto_follow"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.command("/api/settings", {"auto_follow": True})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.command("/api/settings", {"auto_follow": False})


class YapaiaMuteSwitch(YapaiaEntity, SwitchEntity):
    _attr_icon = "mdi:volume-off"

    def __init__(self, coordinator: YapaiaCoordinator) -> None:
        super().__init__(coordinator, "mute", "switch")

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get("muted"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.command("/api/volume", {"muted": True})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.command("/api/volume", {"muted": False})
