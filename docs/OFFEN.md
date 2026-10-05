# Offene Punkte (Stand 2026-10-05)

Übergabe, damit nach der Pause nahtlos weitergearbeitet werden kann.

## Yapaia Beat

### 1. Senderlogos fehlen oder sind abgeschnitten
Gemeldet: Logos werden oft nicht gefunden, auch bei großen Sendern (DASDING);
„Logo online suchen“ bringt nichts Neues; bei einem Sender fehlte die Hälfte
des Logos (Screenshot: egoFM, nur oberes Viertel sichtbar). „Das Radio in
meinem Auto findet sie auch.“

Ansätze zum Prüfen:
- **Logos aus dem DAB-Signal selbst** (wie das Autoradio): DAB+ überträgt
  Senderlogos über SPI (Service and Programme Information, ETSI TS 102 818)
  bzw. MOT-Slideshow (ETSI TS 101 499). Prüfen, ob der Decoder die
  SPI-/MOT-Daten liefert und `yapaia/logos.py` sie übernehmen kann.
- **Online-Quellen**: welche Quelle `logos.py` heute nutzt; radio-browser.info
  (`favicon`), RadioDNS (SPI über DNS, `<sid>.<eid>.<ecc>.dab.radiodns.org`) als
  zusätzliche Quelle; Namensnormalisierung (DASDING vs. „DASDING“, Umlaute,
  „SWR3“ vs. „SWR 3“).
- **Halbes Logo**: wahrscheinlich ein abgebrochener Download oder eine
  unvollständige MOT-Übertragung, die trotzdem gespeichert wurde. Vor dem
  Speichern prüfen, ob das Bild vollständig decodierbar ist (PIL `verify()`),
  sonst verwerfen.

### 2. DAB-Empfang softwareseitig verbessern
Gemeldet: DAB-Sender werden gefunden, lassen sich aber oft nicht abspielen;
Antenne am RTL-SDR vermutlich schwach. Hinweis: eine Android-App („Dream DAB“
o. ä.) wurde allein durch ein Software-Update deutlich besser.

Zu recherchieren und zu messen:
- Verstärkung: feste Gain-Stufe statt AGC, oder AGC mit Nachregelung;
  Gain-Suche je Kanal und das Ergebnis speichern.
- Frequenzkorrektur (PPM) automatisch bestimmen und speichern.
- Soft-Decision-Viterbi, Fehlerkorrektur (Reed-Solomon im DAB+-Superframe),
  Zeitsynchronisation/Coarse-/Fine-Frequency-Korrektur im verwendeten Decoder
  (welle.io/dablin/eti-cmdline?) — Versionen und Optionen vergleichen.
- Ausgaben/Kennzahlen (SNR, FIC-CRC-Fehler, Superframe-Fehler) im UI zeigen,
  damit Verbesserungen messbar sind.
- Puffer gegen Aussetzer (Audio-Puffer vergrößern, Fehlerverschleierung).

## Yapaia Go
- 0.40.0 ist ausgeliefert. Der Betreiber muss noch „Fehlendes bauen“ ausführen
  (die Schweiz fehlte im Routing-Graphen). Ergebnis abwarten: erscheint am Ende
  „im Routing fehlt …“, das Add-on-Protokoll ansehen (Download des Extrakts?).
