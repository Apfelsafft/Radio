"""Sensors: station, radio text, now playing, signal, frequency …"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import YapaiaCoordinator
from .entity import YapaiaEntity


def _text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    value = str(value)
    return value if len(value) <= 250 else value[:247] + "…"


def _now_playing(c: YapaiaCoordinator) -> str | None:
    d = c.data or {}
    if d.get("title"):
        return _text(f"{d['artist']} – {d['title']}" if d.get("artist") else d["title"])
    return None


def _signal(c: YapaiaCoordinator) -> int | None:
    d = c.data or {}
    if not d.get("playing") or d.get("signal") is None:
        return None
    return int(round(d["signal"] / 5.0) * 5)


def _scan(c: YapaiaCoordinator) -> str:
    scan = (c.data or {}).get("scan") or {}
    if scan.get("running"):
        return f"{scan.get('progress', 0)} %"
    return "Fehler" if scan.get("error") else "Bereit"


@dataclass(frozen=True, kw_only=True)
class YapaiaSensorDescription(SensorEntityDescription):
    value: Callable[[YapaiaCoordinator], Any]
    picture: bool = False
    attrs: Callable[[YapaiaCoordinator], dict[str, Any]] | None = None


SENSORS: tuple[YapaiaSensorDescription, ...] = (
    YapaiaSensorDescription(
        key="station",
        icon="mdi:radio-tower",
        value=lambda c: (c.station or {}).get("name"),
        picture=True,
        attrs=lambda c: {
            "station_id": (c.station or {}).get("id"),
            "band": (c.data or {}).get("band"),
            "location": c.location(),
            "logo": c.logo_url(c.station),
            "playing": (c.data or {}).get("playing"),
        },
    ),
    YapaiaSensorDescription(key="radiotext", icon="mdi:message-text", value=lambda c: _text((c.data or {}).get("radiotext"))),
    YapaiaSensorDescription(
        key="now_playing",
        icon="mdi:music-note",
        value=_now_playing,
        attrs=lambda c: {"artist": (c.data or {}).get("artist"), "title": (c.data or {}).get("title")},
    ),
    YapaiaSensorDescription(
        key="signal",
        icon="mdi:signal",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value=_signal,
        attrs=lambda c: {"snr_db": (c.data or {}).get("snr"), "stereo": (c.data or {}).get("stereo")},
    ),
    YapaiaSensorDescription(key="frequency", icon="mdi:sine-wave", value=lambda c: c.location()),
    YapaiaSensorDescription(key="program_type", icon="mdi:tag-text", value=lambda c: _text((c.data or {}).get("pty"))),
    YapaiaSensorDescription(
        key="scan",
        icon="mdi:radar",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=_scan,
        attrs=lambda c: dict((c.data or {}).get("scan") or {}, station_count=(c.data or {}).get("station_count")),
    ),
    YapaiaSensorDescription(
        key="follow",
        icon="mdi:map-marker-path",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda c: _text(((c.data or {}).get("follow") or {}).get("message")) or "–",
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities(YapaiaSensor(entry.runtime_data, d) for d in SENSORS)


class YapaiaSensor(YapaiaEntity, SensorEntity):
    entity_description: YapaiaSensorDescription

    def __init__(self, coordinator: YapaiaCoordinator, description: YapaiaSensorDescription) -> None:
        super().__init__(coordinator, description.key, "sensor")
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator)

    @property
    def entity_picture(self) -> str | None:
        if self.entity_description.picture:
            return self.coordinator.logo_url(self.coordinator.station)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs
        return fn(self.coordinator) if fn else None
