# Changelog

## 1.7.0

- **Music Assistant:** Spielt das Radio auf einem Music-Assistant-Player
  (Ausgabe wählen → der Player von Music Assistant), übernimmt Music
  Assistant die Ansagen von Yapaia Go und `yapaia_beat.announce`: die Musik
  wird kurz pausiert bzw. – bei Snapcast und Sonos – leiser gemischt und
  läuft danach weiter. Ohne den Vorrat des Streams, also ohne die
  Verzögerung von einigen Sekunden. Bei allen anderen Ausgaben mischt Beat
  weiter selbst

## 1.6.5

- **Ansagen kommen nach einer Weile früher:** Der Browser hält einige
  Sekunden Radio vorrätig – um so viel kam auch jede Ansage zu spät (~6 s;
  die Sprache selbst braucht nur Bruchteile einer Sekunde). Jetzt spielt der
  Browser das Radio 5 % schneller (Tonhöhe bleibt), solange mehr als 2 s
  vorrätig sind, und wieder normal unter 1 s. Kein Springen wie in 1.6.3;
  nach dem Start und nach jedem Stocken wird nicht eingegriffen

## 1.6.4

- **Ton im Browser wieder stabil:** Gemeldet nach 1.6.3: „spielt ganz kurz
  und bricht dann wieder ab". Das Aufholen zum Live-Ton sprang im Vorrat des
  Browsers nach vorn – der Vorrat lief leer, der Browser stockte, füllte neu
  und wurde wieder übersprungen. Das Aufholen ist wieder entfernt; die
  deutsche Aussprache der Ansagen aus 1.6.3 bleibt

## 1.6.3

- **Ansagen auf Deutsch statt mit Akzent:** Ohne Sprachangabe nahm die
  Sprachausgabe ihre Standardsprache (oft Englisch) und las den deutschen
  Text mit Akzent. Jetzt gilt die Sprache von Home Assistant (Einstellungen
  → System → Allgemein), passend zu dem, was die Stimme anbietet
- **Ansagen kommen früher:** Der Browser hielt einige Sekunden Radio
  vorrätig – um so viel kam auch jede Ansage zu spät. Jetzt holt er zum
  aktuellen Ton auf (springt bei großem Rückstand, spielt sonst kurz etwas
  schneller, ohne die Tonhöhe zu ändern)
- `yapaia_beat.announce` meldet, wie lange die Sprache gebraucht hat
  (`tts_s`)

## 1.6.2

- **Ton läuft beim Dashboard-Wechsel weiter – auch wenn der Abspieler fehlte:**
  Gemeldet: Musik startet auf der Beat-Seite, beim Wechsel zu einem anderen
  Dashboard hört sie auf. Der Ton gehört in den Abspieler im
  Home-Assistant-Fenster; fehlte der dort, spielte die Beat-Seite selbst – und
  verstummte mit ihr. Jetzt lädt die Beat-Seite den Abspieler bei Bedarf
  selbst nach. Unter der Ausgabe steht, ob der Ton beim Wechseln weiterläuft
- **Ansagen: Fehler in Klartext** – `yapaia_beat.announce` sagt Yapaia Go
  jetzt, warum es nicht geht (niemand hört zu, Radio aus, Sprachausgabe
  fehlt …) statt nur „HTTP 500"

## 1.6.1

- **Radio im Browser kommt nach einer Ansage zurück:** Spricht eine andere
  App oder Yapaia Go auf dem iPad/iPhone, hält das Gerät den Ton von Beat an
  – bisher blieb er aus, bis man Beat wieder öffnete. Jetzt spielt Beat
  danach von selbst weiter (bei Yapaia Go genau, wenn die Ansage zu Ende ist)
- **Stopp sofort, Senderwechsel schneller:** Der Browser hält einige Sekunden
  des Streams vorrätig. Beim Stopp lief das Radio deshalb noch ~5 s weiter,
  und ein neuer Sender kam erst, wenn der alte Vorrat abgespielt war. Jetzt
  verwirft der Browser den Vorrat beim Stopp und beim Senderwechsel und setzt
  beim aktuellen Ton ein. Die Zeit, bis der Empfänger einen neuen Sender
  eingestellt hat (bei DAB+ einige Sekunden), bleibt

## 1.6.0

- **Ansagen einmischen:** Yapaia Go (und jede Automation) kann jetzt in das
  laufende Radio sprechen – die Musik wird leiser, die Ansage darübergelegt,
  danach wird die Musik wieder lauter. Nichts wird gestoppt oder neu
  gestartet, das Radio läuft durch. Neue Aktion `yapaia_beat.announce`,
  neue Option `announce_music_level` (Musik während Ansagen, Standard 20 %)

## 1.5.0

- Radio im Browser spielt weiter, wenn man die Add-on-Seite in der
  Seitenleiste verlässt und zu einem anderen Dashboard wechselt (der Ton läuft
  jetzt im Home-Assistant-Hauptfenster, wie bei der Radio-Karte)
- Sender und Logo auf Sperrbildschirm/Autoradio werden auch ohne Radio-Karte
  auf dem Bildschirm aktualisiert
- DAB+-Slideshow antippen = groß anzeigen (Add-on-Seite und Radio-Karte)

## 1.4.0

- Ausgabe-Auswahl wie bei Spotify: Dieses Gerät, Mini-PC, beides – oder jeder
  Media Player in Home Assistant (Sonos, Chromecast, Music Assistant, DLNA …).
  Die Integration startet/stoppt den Stream auf dem Lautsprecher mit dem
  Radio und gleicht die Lautstärke ab
- Neu: `select.yapaia_beat_output` und Aktion `yapaia_beat.set_output`
- Ton im Browser startet ohne „Ton hier aktivieren": sofort beim Umschalten,
  nach einem Neuladen beim ersten Tippen irgendwo auf der Seite

## 1.3.0

- Standby: hört niemand zu (Mini-PC-Lautsprecher aus, kein Browser/Player am
  Stream), stoppt der Empfang nach `standby_minutes` (Standard 10, 0 = aus) –
  automatisches Weiterspielen, sobald wieder jemand zuhört
- Schonender Umgang mit dem RTL-SDR Stick: Programme werden sauber beendet
  (SIGINT statt hartem Abbruch mitten im USB-Transfer) und zwischen zwei
  Zugriffen bekommt der Stick 1,5 s Pause – schnelle Wechsel (Senderverfolgung,
  Umschalten) konnten den Stick hinter einer VM-USB-Durchreichung aufhängen
- Hängender Stick wird erkannt: kein Ton mehr vom DAB-Empfänger (30 s) bzw.
  keine Daten von rtl_fm (10 s) → automatische Wiederherstellung
- Doku: Hinweise zu Proxmox (DVB-Treiber sperren) und NESDR SMArTee (Bias-Tee)

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
