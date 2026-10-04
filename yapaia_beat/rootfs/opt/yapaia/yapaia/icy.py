"""ICY metadata ("Shoutcast") in the MP3 stream.

Music Assistant, VLC and most internet-radio players ask for it with the
request header ``Icy-MetaData: 1``.  They then expect every ``icy-metaint``
bytes of audio a metadata block – a length byte (×16) followed by
``StreamTitle='…';`` – and show that title as the current song.  Without it,
Music Assistant names the radio after its URL ("stream?authSig=…").
"""

from __future__ import annotations

from typing import Any

METAINT = 16000
ICY_NAME = "Yapaia Beat"


def icy_name(status: dict[str, Any]) -> str:
    """Name of the stream: "<station> via Yapaia Beat" (Music Assistant shows it
    as the radio's name; sent when a player connects)."""
    station = (status.get("station") or {}).get("name")
    return f"{station} via {ICY_NAME}" if station else ICY_NAME


def jetzt_titel(status: dict[str, Any]) -> str:
    """What is on now, as "Artist - Title" (Music Assistant splits it there)."""
    station = (status.get("station") or {}).get("name") or ""
    if not status.get("playing"):
        return station
    title, artist = status.get("title"), status.get("artist")
    if title and artist:
        return f"{artist} - {title}"
    return title or status.get("radiotext") or station


def icy_block(title: str | None) -> bytes:
    """One metadata block; an unchanged title is sent as an empty block (b"\\0")."""
    if title is None:
        return b"\0"
    text = title.replace("'", "’").replace("\n", " ").strip()[:200]
    raw = f"StreamTitle='{text}';".encode()
    raw = raw[: 255 * 16]
    n = -(-len(raw) // 16)  # blocks of 16 bytes, rounded up
    return bytes([n]) + raw.ljust(n * 16, b"\0")


class IcyWriter:
    """Interleaves audio with metadata blocks every ``metaint`` bytes."""

    def __init__(self, metaint: int = METAINT) -> None:
        self.metaint = metaint
        self._bis = metaint  # audio bytes until the next block
        self._gesendet: str | None = None

    def feed(self, audio: bytes, title: str) -> bytes:
        out = bytearray()
        while audio:
            k = min(self._bis, len(audio))
            out += audio[:k]
            audio = audio[k:]
            self._bis -= k
            if self._bis == 0:
                neu = title if title != self._gesendet else None
                out += icy_block(neu)
                self._gesendet = title
                self._bis = self.metaint
        return bytes(out)
