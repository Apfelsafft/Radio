"""Senderlogos über RadioDNS (ETSI TS 103 270 / SPI, ETSI TS 102 818).

So finden auch Autoradios die Logos: aus den Kennungen, die der Sender
selbst aussendet -- bei DAB+ SId und EId, bei UKW der RDS-PI-Code und die
Frequenz. Daraus entsteht ein DNS-Name, der Sender (bzw. sein Dienstleister)
verweist per CNAME und SRV auf seine Programminformation (``SI.xml``), und
darin stehen die Logos in mehreren Größen.

Warum nicht aus dem DAB-Signal: welle-cli dekodiert nur die MOT-Slideshow
(Songbilder), nicht den SPI-Datendienst, in dem die Senderlogos kommen.
RadioDNS liefert dieselben Logos, braucht aber Internet.
"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Extended Country Code je Land (ETSI TS 101 756). Wird gebraucht, solange
# der Empfänger ihn nicht selbst liefert.
ECC = {"DE": "e0", "AT": "e0", "CH": "e1", "LI": "e2", "IT": "e0", "NL": "e3", "BE": "e0", "LU": "e1", "FR": "e1", "DK": "e1"}


def _hex(value: Any, digits: int) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lower().removeprefix("0x")
    try:
        n = int(s, 16)
    except ValueError:
        return None
    return f"{n:0{digits}x}"


def gcc(id_hex: str, ecc: str) -> str:
    """Global Country Code: erste Ziffer der Kennung + ECC."""
    return f"{id_hex[0]}{ecc}"


def dab_fqdn(station: dict[str, Any], country: str) -> str | None:
    sid = _hex(station.get("sid"), 4)
    eid = _hex(station.get("eid"), 4)
    ecc = _hex(station.get("ecc"), 2) or ECC.get(country.upper())
    if not sid or not eid or not ecc:
        return None
    return f"0.{sid}.{eid}.{gcc(sid, ecc)}.dab.radiodns.org"


def fm_fqdn(station: dict[str, Any], country: str) -> str | None:
    pi = _hex(station.get("pi"), 4)
    ecc = _hex(station.get("ecc"), 2) or ECC.get(country.upper())
    freq = station.get("freq")
    if not pi or not ecc or not isinstance(freq, (int, float)):
        return None
    return f"{round(freq * 100):05d}.{pi}.{gcc(pi, ecc)}.fm.radiodns.org"


def bearer_ids(station: dict[str, Any], country: str) -> set[str]:
    """Die Bearer-Kennungen, unter denen SI.xml diesen Sender führt."""
    out: set[str] = set()
    if station.get("band") == "dab":
        sid, eid = _hex(station.get("sid"), 4), _hex(station.get("eid"), 4)
        ecc = _hex(station.get("ecc"), 2) or ECC.get(country.upper())
        if sid and eid and ecc:
            out.add(f"dab:{gcc(sid, ecc)}.{eid}.{sid}.0")
    elif station.get("band") == "fm":
        pi = _hex(station.get("pi"), 4)
        ecc = _hex(station.get("ecc"), 2) or ECC.get(country.upper())
        if pi and ecc:
            for f in [station.get("freq"), *[x.get("freq") for x in station.get("freqs", [])]]:
                if isinstance(f, (int, float)):
                    out.add(f"fm:{gcc(pi, ecc)}.{pi}.{round(f * 100):05d}")
            out.add(f"fm:{gcc(pi, ecc)}.{pi}.*")
    return out


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def logo_aus_si(xml: bytes, bearers: set[str]) -> str | None:
    """Die beste Logo-URL für den Sender mit einem dieser Bearer.

    Bevorzugt quadratische Bilder um 320–600 Pixel; `logo_colour_square`
    (32×32) nur, wenn es nichts anderes gibt.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    for service in root.iter():
        if _local(service.tag) != "service":
            continue
        ids = {
            (b.get("id") or "").lower()
            for b in service.iter()
            if _local(b.tag) == "bearer"
        }
        if not ids & {x.lower() for x in bearers} and not _fm_wildcard(ids, bearers):
            continue
        kandidaten = []
        for m in service.iter():
            if _local(m.tag) != "multimedia" or not m.get("url"):
                continue
            w, h = int(m.get("width") or 0), int(m.get("height") or 0)
            typ = m.get("type") or ""
            if typ == "logo_colour_square":
                w = h = w or 32
            elif typ == "logo_colour_rectangle":
                w, h = w or 112, h or 32
            quadrat = 1 if w and h and abs(w - h) <= max(w, h) * 0.1 else 0
            groesse = min(max(w, h), 600)
            kandidaten.append((quadrat, groesse, m.get("url")))
        if kandidaten:
            kandidaten.sort(reverse=True)
            return kandidaten[0][2]
    return None


def _fm_wildcard(ids: set[str], bearers: set[str]) -> bool:
    """`fm:de0.d3c3.*` im SI passt auf jede Frequenz dieses PI."""
    for b in bearers:
        if b.startswith("fm:"):
            stem = b.rsplit(".", 1)[0].lower()
            if any(i.startswith(stem + ".") for i in ids):
                return True
    return False


async def spi_host(fqdn: str) -> tuple[str, int] | None:
    """CNAME und SRV `_radioepg._tcp` auflösen (dnspython, im Executor)."""
    try:
        import dns.resolver  # type: ignore[import-not-found]
    except ImportError:
        _LOGGER.debug("dnspython fehlt -- RadioDNS nicht verfügbar")
        return None

    def lookup() -> tuple[str, int] | None:
        try:
            cname = dns.resolver.resolve(fqdn, "CNAME")
            target = str(cname[0].target).rstrip(".")
            srv = dns.resolver.resolve(f"_radioepg._tcp.{target}", "SRV")
            best = sorted(srv, key=lambda r: (r.priority, -r.weight))[0]
            return str(best.target).rstrip("."), int(best.port)
        except Exception as err:  # noqa: BLE001 -- jeder DNS-Fehler heißt: kein RadioDNS
            _LOGGER.debug("RadioDNS %s: %s", fqdn, err)
            return None

    return await asyncio.get_running_loop().run_in_executor(None, lookup)


def si_url(host: str, port: int) -> str:
    scheme = "https" if port == 443 else "http"
    standard = 443 if scheme == "https" else 80
    return f"{scheme}://{host}{'' if port == standard else f':{port}'}/radiodns/spi/3.1/SI.xml"
