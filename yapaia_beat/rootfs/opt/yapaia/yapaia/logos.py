"""Station logos.

Order of preference:
1. logo uploaded by the user in the web UI
2. logo found online, cached in /data/logos:
   a) RadioDNS -- the broadcaster's own logo, found by the identifiers the
      station transmits (DAB SId/EId, FM PI), like car radios do
   b) radio-browser.info by name
3. generated placeholder (SVG with the station initials)

Cached logos are checked for completeness (a half-transferred image was
saved as a "half logo") and looked up again every REFRESH seconds, so a new
logo of the station arrives and a lost one comes back.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

import aiohttp

from . import radiodns
from .store import display_name, normalize_name

_LOGGER = logging.getLogger(__name__)

RADIO_BROWSER = [
    "https://all.api.radio-browser.info",
    "https://de1.api.radio-browser.info",
    "https://de2.api.radio-browser.info",
    "https://fi1.api.radio-browser.info",
]
USER_AGENT = "YapaiaBeat/1.0 (Home Assistant add-on)"
EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
}
CTYPE = {v: k for k, v in EXT.items()}
RETRY_AFTER = 24 * 3600
REFRESH = 14 * 24 * 3600
SI_CACHE = 24 * 3600
PALETTE = ["#ff6b35", "#f7c548", "#2ec4b6", "#e71d36", "#8338ec", "#3a86ff", "#06d6a0", "#ef476f"]


class LogoManager:
    def __init__(self, directory: Path, online: bool, country: str) -> None:
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "custom").mkdir(exist_ok=True)
        self.online = online
        self.country = (country or "").upper()
        self._lock = asyncio.Lock()
        self._session: aiohttp.ClientSession | None = None
        self._si: dict[str, tuple[float, bytes]] = {}

    async def close(self) -> None:
        if self._session:
            await self._session.close()

    # ------------------------------------------------------------------
    def _find(self, folder: Path, station_id: str) -> Path | None:
        for ext in CTYPE:
            p = folder / f"{station_id}{ext}"
            if p.exists():
                return p
        return None

    def path(self, station_id: str) -> Path | None:
        return self._find(self.dir / "custom", station_id) or self._find(self.dir, station_id)

    def version(self, station_id: str) -> int:
        p = self.path(station_id)
        return int(p.stat().st_mtime) if p else 0

    def needs_lookup(self, station: dict[str, Any]) -> bool:
        """No logo, a broken cached one, or a cached one due for a refresh."""
        sid = station["id"]
        if self._find(self.dir / "custom", sid):
            return False
        p = self._find(self.dir, sid)
        if not p:
            return True
        if not image_complete(p.read_bytes(), self.content_type(p)):
            return True
        return time.time() - p.stat().st_mtime > REFRESH

    def has_logo(self, station_id: str) -> bool:
        return self.path(station_id) is not None

    @staticmethod
    def content_type(path: Path) -> str:
        return CTYPE.get(path.suffix, "application/octet-stream")

    def placeholder(self, station: dict[str, Any] | None) -> bytes:
        name = display_name(station) if station else "Yapaia Beat"
        words = [w for w in name.replace("-", " ").split() if w]
        if len(words) >= 2:
            initials = (words[0][0] + words[1][0]).upper()
        else:
            initials = name[:3].upper()
        color = PALETTE[int(hashlib.md5(name.encode()).hexdigest(), 16) % len(PALETTE)]
        band = (station or {}).get("band", "").upper().replace("DAB", "DAB+")
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="{color}"/><stop offset="1" stop-color="#1b1f3b"/></linearGradient></defs>
<rect width="256" height="256" rx="48" fill="url(#g)"/>
<text x="128" y="150" font-family="Arial,Helvetica,sans-serif" font-size="{96 if len(initials) < 3 else 76}"
 font-weight="700" text-anchor="middle" fill="#fff">{escape(initials)}</text>
<text x="128" y="215" font-family="Arial,Helvetica,sans-serif" font-size="28" text-anchor="middle"
 fill="#ffffffb0" letter-spacing="4">{escape(band)}</text></svg>""".encode()

    # ------------------------------------------------------------------
    def save_custom(self, station_id: str, data: bytes, content_type: str) -> None:
        ext = EXT.get(content_type.split(";")[0].strip().lower())
        if not ext:
            raise ValueError("Nicht unterstütztes Bildformat")
        self.remove_custom(station_id)
        (self.dir / "custom" / f"{station_id}{ext}").write_bytes(data)

    def remove_custom(self, station_id: str) -> None:
        p = self._find(self.dir / "custom", station_id)
        if p:
            p.unlink()

    def remove_cached(self, station_id: str) -> None:
        p = self._find(self.dir, station_id)
        if p:
            p.unlink()

    # ------------------------------------------------------------------
    def _cached_ok(self, station_id: str) -> bool:
        """Is the cached (not user-uploaded) logo a complete image?"""
        p = self._find(self.dir, station_id)
        if not p:
            return False
        if image_complete(p.read_bytes(), self.content_type(p)):
            return True
        _LOGGER.info("Logo for %s is incomplete -- fetching it again", station_id)
        p.unlink()
        return False

    async def ensure(self, station: dict[str, Any], force: bool = False) -> bool:
        """Look up a logo online if we have none, it is broken or due for a
        refresh.  Returns True if changed."""
        sid = station["id"]
        if not self.online:
            return False
        if self._find(self.dir / "custom", sid) and not force:
            return False  # the user's own logo always wins
        have = self._cached_ok(sid)
        due = have and time.time() - self.version(sid) > REFRESH
        if have and not due and not force:
            return False
        if not force and time.time() - station.get("logo_lookup", 0) < RETRY_AFTER:
            return False
        station["logo_lookup"] = time.time()
        async with self._lock:
            for url in await self._candidates(station):
                try:
                    if await self._download(url, sid):
                        station["logo_source"] = url
                        _LOGGER.info("Logo for %s: %s", display_name(station), url)
                        return True
                except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                    _LOGGER.debug("Logo download failed for %s: %s", sid, err)
            if due and have:
                # nothing new found -- keep the old one, look again next time
                os.utime(self._find(self.dir, sid))  # type: ignore[arg-type]
        return False

    async def _candidates(self, station: dict[str, Any]) -> list[str]:
        out: list[str] = []
        try:
            url = await self._radiodns(station)
            if url:
                out.append(url)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("RadioDNS failed for %s: %s", station["id"], err)
        try:
            url = await self._search(station)
            if url:
                out.append(url)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Logo lookup failed for %s: %s", station["id"], err)
            station["logo_lookup"] = time.time() - RETRY_AFTER + 600  # retry in 10 min
        return out

    async def _radiodns(self, station: dict[str, Any]) -> str | None:
        fqdn = (
            radiodns.dab_fqdn(station, self.country)
            if station.get("band") == "dab"
            else radiodns.fm_fqdn(station, self.country)
        )
        if not fqdn:
            return None
        host = await radiodns.spi_host(fqdn)
        if not host:
            return None
        url = radiodns.si_url(*host)
        cached = self._si.get(url)
        if cached and time.time() - cached[0] < SI_CACHE:
            xml = cached[1]
        else:
            async with self._http().get(url) as r:
                if r.status != 200:
                    return None
                xml = await r.content.read(20_000_000)
            self._si[url] = (time.time(), xml)
        return radiodns.logo_aus_si(xml, radiodns.bearer_ids(station, self.country))

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15), headers={"User-Agent": USER_AGENT}, trust_env=True
            )
        return self._session

    async def _query(self, path: str) -> list[dict[str, Any]]:
        last: Exception | None = None
        for host in RADIO_BROWSER:
            try:
                async with self._http().get(host + path) as r:
                    if r.status == 200:
                        data = await r.json(content_type=None)
                        return data if isinstance(data, list) else []
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
                last = err
        if last:
            raise aiohttp.ClientError(str(last))
        return []

    async def _search(self, station: dict[str, Any]) -> str | None:
        names = []
        for n in (station.get("custom_name"), station.get("name")):
            if n and n not in names:
                names.append(n)
        for name in names:
            wanted = normalize_name(name)
            if len(wanted) < 2:
                continue
            params = f"name={quote(name)}&hidebroken=true&order=clickcount&reverse=true&limit=40"
            queries = [f"/json/stations/search?{params}&countrycode={self.country}"] if self.country else []
            queries.append(f"/json/stations/search?{params}")
            for q in queries:
                candidates = [c for c in await self._query(q) if c.get("favicon")]
                best = _best_match(wanted, candidates)
                if best:
                    return best["favicon"]
        return None

    async def _download(self, url: str, station_id: str) -> bool:
        async with self._http().get(url, allow_redirects=True) as r:
            if r.status != 200:
                return False
            ctype = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
            ext = EXT.get(ctype)
            if not ext:
                lower = url.lower().split("?")[0]
                ext = next((e for e in CTYPE if lower.endswith(e)), None)
            if not ext:
                return False
            data = await r.content.read(3_000_001)
            if len(data) > 3_000_000 or len(data) < 64:
                return False
            if not image_complete(data, CTYPE.get(ext, "")):
                _LOGGER.debug("Logo from %s is incomplete", url)
                return False
        self.remove_cached(station_id)
        (self.dir / f"{station_id}{ext}").write_bytes(data)
        return True


def _best_match(wanted: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored = []
    for c in candidates:
        n = normalize_name(c.get("name", ""))
        if not n:
            continue
        if n == wanted:
            score = 100
        elif n.startswith(wanted) or wanted.startswith(n):
            score = 70 - abs(len(n) - len(wanted))
        elif wanted in n:
            score = 50 - abs(len(n) - len(wanted))
        else:
            continue
        # prefer real logos over tiny favicons
        fav = c.get("favicon", "").lower()
        if fav.endswith(".ico") or "favicon" in fav:
            score -= 15
        scored.append((score, int(c.get("clickcount") or 0), c))
    if not scored:
        return None
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    return scored[0][2] if scored[0][0] >= 30 else None


def image_complete(data: bytes, content_type: str) -> bool:
    """Is this a whole image?  A transfer that broke off half-way still
    starts like an image -- and was shown as a logo cut off in the middle."""
    tail = data.rstrip(b"\x00 \r\n\t")
    if content_type == "image/png":
        return data.startswith(b"\x89PNG") and b"IEND" in data[-32:]
    if content_type in ("image/jpeg", "image/jpg"):
        return data.startswith(b"\xff\xd8") and tail.endswith(b"\xff\xd9")
    if content_type == "image/gif":
        return data.startswith(b"GIF8") and tail.endswith(b"\x3b")
    if content_type == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP" and int.from_bytes(data[4:8], "little") + 8 <= len(data)
    if content_type == "image/svg+xml":
        return b"</svg>" in data[-200:].lower()
    return True
