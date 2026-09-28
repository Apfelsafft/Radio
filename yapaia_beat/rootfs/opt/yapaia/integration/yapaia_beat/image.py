"""Image entities: station logo and DAB+ slideshow (picture-entity card)."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import YapaiaCoordinator
from .entity import YapaiaEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coord = entry.runtime_data
    async_add_entities([YapaiaLogoImage(hass, coord), YapaiaSlideImage(hass, coord)])


class _YapaiaImage(YapaiaEntity, ImageEntity):
    def __init__(self, hass: HomeAssistant, coordinator: YapaiaCoordinator, key: str) -> None:
        YapaiaEntity.__init__(self, coordinator, key, "image")
        ImageEntity.__init__(self, hass)
        self._key: str | None = None
        self._attr_image_last_updated = dt_util.utcnow()

    def _current_key(self) -> str | None:
        raise NotImplementedError

    def _path(self) -> str | None:
        raise NotImplementedError

    @callback
    def _handle_coordinator_update(self) -> None:
        key = self._current_key()
        if key != self._key:
            self._key = key
            self._attr_image_last_updated = dt_util.utcnow()
            self._cached_image = None
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        path = self._path()
        if not path:
            return None
        res = await self.coordinator.fetch(path)
        if not res:
            return None
        self._attr_content_type = res[1].split(";")[0]
        return res[0]


class YapaiaLogoImage(_YapaiaImage):
    def __init__(self, hass: HomeAssistant, coordinator: YapaiaCoordinator) -> None:
        super().__init__(hass, coordinator, "logo")

    def _current_key(self) -> str | None:
        st = self.coordinator.station
        return st["logo_url"] if st else None

    def _path(self) -> str | None:
        st = self.coordinator.station
        return f"/{st['logo_url']}" if st else "/api/logo/current"


class YapaiaSlideImage(_YapaiaImage):
    def __init__(self, hass: HomeAssistant, coordinator: YapaiaCoordinator) -> None:
        super().__init__(hass, coordinator, "slideshow")

    def _current_key(self) -> str | None:
        v = (self.coordinator.data or {}).get("slide_version")
        return str(v) if v else None

    def _path(self) -> str | None:
        return "/api/slide" if self._current_key() else None

    @property
    def available(self) -> bool:
        return super().available and self._current_key() is not None
