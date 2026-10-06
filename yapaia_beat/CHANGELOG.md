# Changelog

## 1.11.0

- **Senderlogos wie im Autoradio (RadioDNS):** Gemeldet: Logos fehlten auch
  bei großen Sendern wie DASDING, „Logo online suchen“ brachte nichts Neues.
  Beat fragt jetzt zuerst RadioDNS — darüber veröffentlichen die Sender ihre
  Logos selbst, gefunden über die Kennungen, die sie aussenden (DAB+: SId und
  Ensemble-Kennung, UKW: RDS-PI-Code und Frequenz). Erst danach wird wie
  bisher nach dem Namen gesucht. Gilt für DAB+ und UKW, braucht Internet.
- **Kein halbes Logo mehr:** Ein Bild, dessen Übertragung abbrach, wurde
  trotzdem gespeichert. Jetzt wird jedes Bild vor dem Speichern auf
  Vollständigkeit geprüft; ein schon gespeichertes kaputtes wird neu geholt.
- **Logos bleiben aktuell:** Geladene Logos werden alle zwei Wochen und beim
  Abspielen neu gesucht — bekommt ein Sender ein neues Logo oder geht eines
  verloren, kommt es wieder. Selbst hochgeladene Logos bleiben unangetastet.
- Für DAB+-Sender aus einem älteren Suchlauf wird die Ensemble-Kennung beim
  ersten Abspielen nachgetragen; ein neuer Suchlauf ist nicht nötig.
- Warum nicht direkt aus dem DAB-Signal: der Decoder (welle-cli) liest nur
  die Songbilder (Slideshow), nicht den Datendienst mit den Senderlogos.

## 1.10.2

- **Sendername in Music Assistant beim Senderwechsel:** Nach dem Wechsel von
  SWR3 auf Beats Radio stand im Player weiter „SWR3 via Yapaia Beat“. Der
  Player liest den Sendernamen nur beim Verbinden, und der Stream läuft über
  den Wechsel hinweg. Jetzt bekommt der Player den Stream neu, sobald der neue
  Sender etwa drei Sekunden spielt — beim schnellen Durchschalten nur einmal,
  für den letzten. Das gilt für jede Ausgabe, nicht nur für Music Assistant.
  Dabei gibt es eine kurze Pause, wie beim Umschalten ohnehin.
- Das Albumbild sucht Music Assistant selbst im Netz zum laufenden Titel;
  wie schnell es kommt, liegt bei Music Assistant.

## 1.10.1

- **Music Assistant ließ sich nicht mehr öffnen:** Im Protokoll von Music
  Assistant stand im Sekundentakt „Ingress auth failed for sendspin proxy“.
  „Music Assistant in diesem Browser“ hatte seine Ingress-Sitzung angelegt,
  während Home Assistant noch startete. Eine solche Sitzung trägt keinen
  Benutzer, und Music Assistant lehnt sie ab. Der Player versuchte es dann
  jede Sekunde neu und schrieb dabei jedes Mal das Ingress-Cookie neu. Das
  Cookie gilt für alle Add-on-Seiten, so bekam auch die Seite von Music
  Assistant die Sitzung ohne Benutzer und lud nicht mehr. Jetzt:
  - wartet der Player, bis Home Assistant ganz gestartet ist
  - schreibt er das Cookie nur, wenn er eine neue Sitzung anlegt
  - holt er nach drei Ablehnungen eine frische Sitzung; nach zehn macht er
    fünf Minuten Pause, statt im Sekundentakt anzuklopfen

## 1.10.0

- **Favoriten mit einem Tippen wechseln:** Auf iPad und iPhone zeigte das
  erste Tippen nur die kleinen Pfeile zum Umsortieren, erst das zweite
  wechselte den Sender. Jetzt wechselt ein Tippen sofort
- **Favoriten bearbeiten mit langem Drücken:** Eine halbe Sekunde halten
  öffnet den Favoriten mit großen Pfeilen zum Verschieben und einem
  Mülleimer zum Entfernen (wie der Stern in der Senderliste). Der Favorit
  bleibt nach einem Pfeil offen und kann so mehrere Plätze wandern. Ein
  Tippen daneben schließt ihn wieder
- **Lautstärke-Regler:** Der farbige Balken lief ab etwa 80 % dem Regler
  voraus, und der Regler erreichte das rechte Ende nicht. Der Regler ist
  jetzt selbst gezeichnet, der Balken endet genau unter seiner Mitte (auch
  in der Karte)
- **Sendername in Music Assistant:** „SWR3 via Yapaia Beat“ statt nur
  „Yapaia Beat“ (gilt ab dem nächsten Start der Wiedergabe)
- **„Yapaia Browser“** statt „Yapaia iPad“: So heißt der Player von „Music
  Assistant in diesem Browser“ jetzt – es ist nicht immer ein iPad. Wer ihn
  schon angemeldet hat, kann ihn in Music Assistant mit dem Stift
  umbenennen, falls der alte Name bleibt

## 1.9.0

- **Ansagen sofort, auch wenn das Radio über Music Assistant läuft:** Spielt
  das Radio über „Music Assistant in diesem Browser“ (z. B. „Yapaia iPad“),
  mischt dieser Browser die Ansagen von Yapaia Go jetzt selbst ein: Musik
  leiser, Ansage darüber, Musik wieder lauter. Bisher mischte Beat sie in
  den Stream. Den hat Music Assistant einige Sekunden auf Vorrat, und um so
  viel kam jede Ansage zu spät (im Test 5–7 s). Jetzt kommt sie, sobald
  Home Assistant die Sprache erzeugt hat. Braucht Yapaia Go 0.38

## 1.8.2

- **Songtitel in Music Assistant:** Statt „stream?authSig=…“ zeigt Music
  Assistant jetzt den laufenden Titel („Interpret - Titel“, sonst Radiotext
  oder Sender) und als Namen „Yapaia Beat“. Der MP3-Stream liefert dafür
  ICY-Metadaten, wie es Internetradios tun – aber nur Playern, die danach
  fragen (Music Assistant, VLC …). Der Browser bekommt den Stream wie bisher

## 1.8.1

- **Ansagen über Music Assistant ohne Unterbrechung:** Läuft das Radio auf
  einem Player von Music Assistant, mischt Beat Ansagen jetzt selbst in den
  Strom, den Music Assistant abspielt. Bisher übernahm Music Assistant sie.
  Dafür hielt es das Radio an, spielte einen Gong und die Ansage und
  startete das Radio neu – im Test dauerte das lange oder es blieb stumm.
  Music Assistant spricht nur noch selbst, wenn das Radio gerade nicht läuft
- **„Yapaia iPad“ nach dem Wechsel stumm:** Wechselt man von „Dieses Gerät“
  zurück zum Player von Music Assistant, gibt Beat dessen Ton im selben
  Tippen wieder frei. Pausiert das iPad ihn, während Music Assistant spielt,
  startet Beat ihn nach einer Sekunde wieder

## 1.8.0

- **Der Browser als Player von Music Assistant:** Unter „Ausgabe“ gibt es
  den Schalter „Music Assistant in diesem Browser“. Der Browser meldet sich
  dann als „Yapaia iPad“ (bzw. iPhone, Android …) bei Music Assistant an –
  aus dem Home-Assistant-Fenster heraus, darum spielt er auch beim Wechsel
  des Dashboards weiter (anders als der Web-Player in der Seite von Music
  Assistant). Music Assistant fragt einmal, ob es ihn zulassen soll; danach
  steht er in der Ausgabe-Liste. So läuft das Radio auch ohne Cast-Geräte
  über Music Assistant, mit kurzem Puffer, und Ansagen von Yapaia Go mischt
  Music Assistant ein. Beat zeigt unter dem Schalter, wie weit die
  Anmeldung ist und was noch zu tun ist
- Nutzt die offizielle Bibliothek `sendspin-js` 5.0.0 (dieselbe wie Music
  Assistant selbst), mitgeliefert in der Karte

## 1.7.1

- **Music Assistant sichtbar:** Unter „Ausgabe“ tragen Player von Music
  Assistant 🎵 und den Zusatz „Music Assistant“. Gibt es keinen, steht dort,
  warum: Music Assistant fehlt als Integration in Home Assistant, oder es
  gibt seine Player nicht an Home Assistant weiter (in Music Assistant je
  Player „Dieses Wiedergabegerät für Home Assistant freigeben“). Spielt das
  Radio über Music Assistant, sagt das der Hinweis unter der Ausgabe
- Das Medien-Gerät `media_player.yapaia_beat` meldet je Player, ob er zu
  Music Assistant gehört – Yapaia Go zeigt damit, welchen Weg seine Ansagen
  nehmen

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
