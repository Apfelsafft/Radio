"""Media source: the live radio stream, playable on "this device" (browser)
or any other media player from the Home Assistant media panel."""

from __future__ import annotations

from homeassistant.components.media_player import MediaClass, MediaType
from homeassistant.components.media_source import BrowseMediaSource, MediaSource, MediaSourceItem, PlayMedia
from homeassistant.core import HomeAssistant

from .const import DOMAIN, LOGO_URL, STREAM_URL


async def async_get_media_source(hass: HomeAssistant) -> MediaSource:
    return YapaiaMediaSource(hass)


class YapaiaMediaSource(MediaSource):
    name = "Yapaia Beat"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        # relative URL → Home Assistant signs it for the requesting browser
        return PlayMedia(STREAM_URL, "audio/mpeg")

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        live = BrowseMediaSource(
            domain=DOMAIN,
            identifier="live",
            media_class=MediaClass.CHANNEL,
            media_content_type=MediaType.MUSIC,
            title="Yapaia Beat – Live",
            can_play=True,
            can_expand=False,
            thumbnail=LOGO_URL.format("current"),
        )
        if item.identifier == "live":
            return live
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=None,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title="Yapaia Beat",
            can_play=False,
            can_expand=True,
            children=[live],
            children_media_class=MediaClass.CHANNEL,
        )
