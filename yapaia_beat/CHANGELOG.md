# Changelog

## 1.2.0

- Favoriten passen sich dem freien Platz an: Seiten statt Scrollen, wischen
  oder Punkte antippen; Zwei-Spalten-Layout für flache Querformat-Bildschirme
  (Autoradio 1024×600)
- Schnelleres Umschalten: eine Bedienung bricht eine laufende
  Senderverfolgungs-Suche sofort ab; Wechsel innerhalb desselben
  DAB-Ensembles ohne Neustart des Empfängers; sofortige Rückmeldung beim Tippen
- Senderverfolgung stört weniger: nach erfolgloser Suche wartet sie
  zunehmend länger (2, 4, 8 … 30 min), die Bandsuche läuft nur noch bei sehr
  schlechtem Empfang
- Stereo/Mono ohne Flackern: Hysterese (Stereo ab 20 dB für 2 s, Mono unter
  13 dB) und ruhigere Signalmessung
- Ersatzlogo, wenn ein gespeichertes Logo nicht geladen werden kann

## 1.1.1

- Automatische Wiederherstellung, wenn der RTL-SDR Stick verschwindet oder
  hängt (lockerer USB-Stecker, Wackelkontakt im Camper): alle 15 s ein neuer
  Versuch, danach läuft der letzte Sender automatisch weiter
- `rtl_power` (Bandmessung für Suchlauf/Senderverfolgung) hat ein festes
  Zeitlimit, wird sauber beendet und blockiert den Stick nicht mehr; bereits
  gemessene Werte werden weiterverwendet
- USB-Reset des Sticks, wenn ein Hilfsprogramm hängen bleibt
- Unerwartet beendeter Empfang wird erkannt (vorher blieb der Status auf „läuft")
- DAB-Vorauswahl misst schneller

## 1.1.0

- Radio im Browser hören: Ausgabe wählbar „Mini-PC", „Dieses Gerät" oder „Beide"
  (Add-on-Oberfläche und Radio-Karte, Einstellung wird pro Gerät gespeichert)
- Neuer Schalter `switch.yapaia_beat_local_output` für die Lautsprecher am Mini-PC
- Live-Stream als Medienquelle – im Medien-Panel auf „Diesem Gerät" abspielbar
- Senderanzeige, Logo und Tasten auf Sperrbildschirm/Autoradio (Media Session)
- MP3-Stream bleibt bei Senderwechsel, Suchlauf und Stopp verbunden

## 1.0.0

- Erste Version von Yapaia Beat
- UKW (FM) Empfang mit Stereo-Decoder und RDS (PS, RadioText, RadioText+, PTY, AF, TP)
- DAB/DAB+ Empfang über welle-cli inkl. DLS-Text und MOT-Slideshow
- Automatischer Suchlauf für FM und DAB+ (mit Schnell-Vorauswahl per Spektrumsmessung)
- Favoriten, Suche nach Name oder Frequenz, manuelles Abstimmen
- Senderlogos (radio-browser.info, eigene Uploads, generierte Platzhalter)
- Automatische Senderverfolgung (RDS-AF, PI-Code, DAB-Service-ID, Wechsel FM ↔ DAB+)
- Wiedergabe über die Home-Assistant-Audioausgabe und als MP3-Stream
- Home-Assistant-Integration (Media Player, Select, Sensoren, Schalter, Buttons, Bilder)
- Eigene Lovelace-Karte im Radio-Stil (Retro & Modern)
