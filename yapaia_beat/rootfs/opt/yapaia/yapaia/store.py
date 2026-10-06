"""Persistent station list, favourites and user settings."""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    """Lower case ASCII-only representation used for matching names."""
    name = unicodedata.normalize("NFKD", name or "")
    name = name.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", name.lower())


def fm_station_id(pi: str | None, freq: float) -> str:
    if pi:
        return f"fm-{pi.lower().replace('0x', '')}"
    return f"fm-{int(round(freq * 1000))}"


def dab_station_id(sid: str) -> str:
    return f"dab-{sid.lower().replace('0x', '')}"


class Store:
    def __init__(self, path: Path) -> None:
        self._path = path
        self.stations: dict[str, dict[str, Any]] = {}
        self.favorites: list[str] = []
        self.settings: dict[str, Any] = {}
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> None:
        try:
            data = json.loads(self._path.read_text())
        except FileNotFoundError:
            return
        except ValueError as err:
            _LOGGER.error("Station database corrupt (%s), starting empty", err)
            return
        self.stations = data.get("stations", {})
        self.favorites = [f for f in data.get("favorites", []) if f in self.stations]
        self.settings = data.get("settings", {})

    def save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {"stations": self.stations, "favorites": self.favorites, "settings": self.settings},
                indent=1,
                ensure_ascii=False,
            )
        )
        tmp.replace(self._path)

    # ------------------------------------------------------------------
    def get(self, station_id: str) -> dict[str, Any] | None:
        return self.stations.get(station_id)

    def set_favorite(self, station_id: str, favorite: bool) -> None:
        if favorite and station_id in self.stations and station_id not in self.favorites:
            self.favorites.append(station_id)
        elif not favorite and station_id in self.favorites:
            self.favorites.remove(station_id)
        self.save()

    def order_favorites(self, ids: list[str]) -> None:
        ordered = [i for i in ids if i in self.favorites]
        ordered += [i for i in self.favorites if i not in ordered]
        self.favorites = ordered
        self.save()

    def rename(self, station_id: str, name: str) -> None:
        st = self.stations.get(station_id)
        if st is not None:
            st["custom_name"] = name.strip() or None
            self.save()

    def delete(self, station_id: str) -> None:
        self.stations.pop(station_id, None)
        if station_id in self.favorites:
            self.favorites.remove(station_id)
        self.save()

    def find_by_name(self, name: str, band: str | None = None) -> list[dict[str, Any]]:
        norm = normalize_name(name)
        if not norm:
            return []
        return [
            s
            for s in self.stations.values()
            if (band is None or s["band"] == band)
            and norm in (normalize_name(display_name(s)), normalize_name(s.get("name", "")))
        ]

    # ------------------------------------------------------------------
    def merge_fm(self, results: list[dict[str, Any]]) -> None:
        """Merge FM scan results; one station per PI code (multiple freqs)."""
        now = time.time()
        for st in self.stations.values():
            if st["band"] == "fm":
                st["available"] = False
        for res in results:
            sid = fm_station_id(res.get("pi"), res["freq"])
            st = self.stations.get(sid)
            if st is None:
                st = {"id": sid, "band": "fm", "freqs": []}
                self.stations[sid] = st
            if res.get("name"):
                st["name"] = res["name"]
            st.setdefault("name", f"FM {res['freq']:.1f}")
            for key in ("pi", "pty"):
                if res.get(key):
                    st[key] = res[key]
            if res.get("af"):
                st["af"] = sorted(set(st.get("af", [])) | set(res["af"]))
            known = {f["freq"]: f for f in st.get("freqs", []) if f.get("seen", 0) > now - 3600}
            known[res["freq"]] = {"freq": res["freq"], "quality": res.get("quality", 0), "seen": now}
            st["freqs"] = sorted(known.values(), key=lambda f: -f.get("quality", 0))
            st["freq"] = st["freqs"][0]["freq"]
            st["available"] = True
            st["updated"] = now
        self.save()

    def merge_dab(self, results: list[dict[str, Any]]) -> None:
        now = time.time()
        found_channels = {r["channel"] for r in results}
        for st in self.stations.values():
            if st["band"] == "dab":
                st["available"] = False
        for res in results:
            sid = dab_station_id(res["sid"])
            st = self.stations.get(sid)
            if st is None:
                st = {"id": sid, "band": "dab"}
                self.stations[sid] = st
            st.update(
                name=res["name"],
                sid=res["sid"],
                pty=res.get("pty") or st.get("pty"),
                eid=res.get("eid") or st.get("eid"),
                ecc=res.get("ecc") or st.get("ecc"),
                available=True,
                updated=now,
            )
            chans = [c for c in st.get("channels", []) if c["channel"] not in found_channels]
            chans.append(
                {
                    "channel": res["channel"],
                    "ensemble": res.get("ensemble"),
                    "quality": res.get("quality", 0),
                    "seen": now,
                }
            )
            st["channels"] = sorted(chans, key=lambda c: -c.get("quality", 0))
            st["channel"] = st["channels"][0]["channel"]
            st["ensemble"] = st["channels"][0].get("ensemble")
        self.save()

    def remember_fm_freq(self, station_id: str, freq: float, quality: float) -> None:
        st = self.stations.get(station_id)
        if not st:
            return
        freqs = [f for f in st.get("freqs", []) if abs(f["freq"] - freq) > 0.01]
        freqs.insert(0, {"freq": freq, "quality": quality, "seen": time.time()})
        st["freqs"] = freqs
        st["freq"] = freq
        self.save()

    def remember_dab_channel(self, station_id: str, channel: str, ensemble: str | None, quality: float) -> None:
        st = self.stations.get(station_id)
        if not st:
            return
        chans = [c for c in st.get("channels", []) if c["channel"] != channel]
        chans.insert(0, {"channel": channel, "ensemble": ensemble, "quality": quality, "seen": time.time()})
        st["channels"] = chans
        st["channel"] = channel
        st["ensemble"] = ensemble
        self.save()


def display_name(station: dict[str, Any]) -> str:
    return station.get("custom_name") or station.get("name") or station["id"]
