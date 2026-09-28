"""Base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION
from .coordinator import YapaiaCoordinator


class YapaiaEntity(CoordinatorEntity[YapaiaCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: YapaiaCoordinator, key: str, platform: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_translation_key = key
        # predictable entity ids (media_player.yapaia_beat, sensor.yapaia_beat_station, …)
        self.entity_id = f"{platform}.yapaia_beat" + (f"_{key}" if key != "radio" else "")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Yapaia Beat",
            manufacturer="Yapaia",
            model="RTL-SDR FM/DAB+ Radio",
            sw_version=VERSION,
        )
