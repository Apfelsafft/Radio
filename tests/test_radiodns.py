"""Senderlogos über RadioDNS und die Prüfung auf vollständige Bilder.

Gemeldet: Logos fehlen auch bei großen Sendern (DASDING), „Das Radio in
meinem Auto findet sie“, und bei einem Sender fehlte die Hälfte des Logos.
"""

import os
import time

from yapaia import radiodns
from yapaia.logos import REFRESH, LogoManager, image_complete

SI = b"""<?xml version="1.0" encoding="UTF-8"?>
<serviceInformation xmlns="http://www.worlddab.org/schemas/spi" version="1">
 <services>
  <service>
   <shortName>DASDING</shortName>
   <mediaDescription><multimedia type="logo_colour_square" url="http://x/32.png"/></mediaDescription>
   <mediaDescription><multimedia mimeValue="image/png" url="http://x/600.png" width="600" height="600"/></mediaDescription>
   <mediaDescription><multimedia mimeValue="image/png" url="http://x/320x240.png" width="320" height="240"/></mediaDescription>
   <bearer id="dab:de0.10bc.d3d5.0" cost="20"/>
   <bearer id="fm:de0.d3d5.*" cost="40"/>
  </service>
  <service>
   <shortName>Anderer</shortName>
   <mediaDescription><multimedia mimeValue="image/png" url="http://x/falsch.png" width="600" height="600"/></mediaDescription>
   <bearer id="dab:de0.10bc.d3d6.0"/>
  </service>
 </services>
</serviceInformation>"""


def test_dns_namen_dab_und_fm():
    dab = {"band": "dab", "sid": "0xd3d5", "eid": "0x10bc"}
    assert radiodns.dab_fqdn(dab, "DE") == "0.d3d5.10bc.de0.dab.radiodns.org"
    fm = {"band": "fm", "pi": "D3D5", "freq": 99.9}
    assert radiodns.fm_fqdn(fm, "DE") == "09990.d3d5.de0.fm.radiodns.org"
    # ohne Ensemble-Kennung kein DAB-Name (alte Senderliste)
    assert radiodns.dab_fqdn({"band": "dab", "sid": "d3d5"}, "DE") is None
    # ein vom Empfänger gelieferter ECC schlägt die Ländertabelle
    assert radiodns.dab_fqdn({**dab, "ecc": "0xe1"}, "DE") == "0.d3d5.10bc.de1.dab.radiodns.org"


def test_logo_aus_si_nimmt_den_richtigen_sender_und_das_grosse_quadrat():
    dab = {"band": "dab", "sid": "d3d5", "eid": "10bc"}
    assert radiodns.logo_aus_si(SI, radiodns.bearer_ids(dab, "DE")) == "http://x/600.png"


def test_logo_aus_si_fm_ueber_platzhalter_frequenz():
    fm = {"band": "fm", "pi": "d3d5", "freq": 102.2}
    assert radiodns.logo_aus_si(SI, radiodns.bearer_ids(fm, "DE")) == "http://x/600.png"


def test_logo_aus_si_ohne_treffer_und_kaputtes_xml():
    assert radiodns.logo_aus_si(SI, {"dab:de0.1111.2222.0"}) is None
    assert radiodns.logo_aus_si(b"<kaputt", {"x"}) is None


def test_halbe_bilder_werden_erkannt():
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 100 + b"IEND\xaeB`\x82"
    assert image_complete(png, "image/png")
    assert not image_complete(png[:60], "image/png")
    jpg = b"\xff\xd8" + b"\0" * 100 + b"\xff\xd9"
    assert image_complete(jpg, "image/jpeg")
    assert not image_complete(jpg[:50], "image/jpeg")


def test_kaputtes_und_altes_logo_werden_neu_gesucht_eigenes_nie(tmp_path):
    m = LogoManager(tmp_path, online=True, country="DE")
    st = {"id": "dab_d3d5", "band": "dab"}
    assert m.needs_lookup(st)  # keins da
    (tmp_path / "dab_d3d5.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 50)  # halb
    assert m.needs_lookup(st)
    (tmp_path / "dab_d3d5.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 50 + b"IEND\xaeB`\x82")
    assert not m.needs_lookup(st)
    alt = time.time() - REFRESH - 60
    os.utime(tmp_path / "dab_d3d5.png", (alt, alt))
    assert m.needs_lookup(st)  # zwei Wochen alt: auffrischen
    (tmp_path / "custom" / "dab_d3d5.png").write_bytes(b"x")
    assert not m.needs_lookup(st)  # das eigene Logo bleibt
