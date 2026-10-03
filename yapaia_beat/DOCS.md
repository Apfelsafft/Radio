# Yapaia Beat – FM & DAB+ Radio

Yapaia Beat macht aus einem günstigen **RTL-SDR USB-Stick** ein vollwertiges
UKW- und DAB+-Radio für Home Assistant – ideal für Camper, Wohnmobil,
Boot oder Ferienhaus, weil es **komplett offline** funktioniert.

## Funktionen

- **UKW (FM)** mit Stereo-Decoder und **RDS**: Sendername (PS), Radiotext,
  RadioText+ (Interpret/Titel), Programmtyp, Verkehrsfunk-Kennung (TP),
  Alternativfrequenzen (AF) und PI-Code
- **DAB/DAB+** mit **DLS**-Text (Interpret – Titel) und **MOT-Slideshow**
- **Automatischer Suchlauf** für FM und DAB+ (mit Schnellvorauswahl per
  Spektrumsmessung) – Sender mit gleichem PI-Code werden zusammengefasst
- **Favoriten** auswählen, sortieren, umbenennen
- **Suche** nach Sendername oder – bei UKW – nach Frequenz (z. B. `98,3`),
  jede Frequenz kann auch direkt eingestellt werden
- **Senderlogos**: automatisch über [radio-browser.info](https://www.radio-browser.info)
  (lokal zwischengespeichert, funktioniert danach offline), eigene Logos
  hochladen oder automatisch generierte Logos
- **Automatische Senderverfolgung** für unterwegs: wird der Empfang schlecht,
  sucht Yapaia Beat denselben Sender auf einer besseren Frequenz
  (RDS-AF-Liste, bekannte Frequenzen, Bandsuche nach PI-Code), auf einem anderen
  DAB-Kanal oder wechselt zwischen UKW und DAB+
- Wiedergabe über die **Audioausgabe von Home Assistant** (Lautsprecher am
  Host) und zusätzlich als **MP3-Stream** (`/stream.mp3`)
- **Home-Assistant-Integration** mit Entitäten für die Standard-Karten
  (Media-Control, Kachel, Entitäten, Bild) und eine eigene **Radio-Karte**

## Hardware

- Ein RTL-SDR Stick (RTL2832U + R820T/R828D, z. B. RTL-SDR Blog V3/V4,
  NooElec NESDR). Andere DVB-T-Sticks mit RTL2832U funktionieren meist auch.
- Eine Antenne für UKW **und** Band III (174–240 MHz). Eine einfache
  Teleskop- oder Dipolantenne reicht für starke Sender; im Camper ist eine
  aktive Dachantenne (FM/DAB) mit Adapter auf SMA/MCX ideal.
- Tipp: den Stick über ein kurzes USB-Verlängerungskabel anschließen (weg von
  USB-3-Ports, die im 2,4-GHz- und UKW-Bereich stören können).

Ein Stick kann immer nur eine Sache gleichzeitig: während eines Suchlaufs oder
einer Senderverfolgungs-Suche ist die Wiedergabe kurz unterbrochen.

## Installation

1. Repository hinzufügen:
   [![Repository hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fapfelsafft%2Fradio)
   oder *Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories* →
   `https://github.com/apfelsafft/radio`
   (alternativ das Skript `install.sh` aus dem Repository verwenden).
2. **Yapaia Beat** installieren und starten. Das Image wird lokal gebaut –
   auf einem Raspberry Pi dauert das beim ersten Mal 15–30 Minuten.
3. Beim ersten Start installiert das Add-on die **Yapaia Beat Integration**
   nach `/config/custom_components/yapaia_beat` und zeigt eine Benachrichtigung.
   **Home Assistant einmal neu starten.**
4. *Einstellungen → Geräte & Dienste*: „Yapaia Beat" wurde entdeckt →
   **Konfigurieren**. (Manuell: Integration hinzufügen → Yapaia Beat, Host =
   Hostname des Add-ons, z. B. `local-yapaia-beat` bzw. `xxxxxxxx-yapaia-beat`,
   Port `8099`.)
5. In der Seitenleiste **Yapaia Beat** öffnen → **Suchlauf** → *Beides*.
6. Unter **Sender** die Favoriten mit ☆ markieren.

## Bedienoberfläche (Seitenleiste)

- **Jetzt läuft**: Logo, Sender, Frequenz/Kanal, PI-Code, Programmtyp,
  Lauftext (RDS/DLS), Interpret – Titel, Empfangsqualität, Stereo/TP,
  DAB+-Slideshow, Steuerung, Lautstärke, Senderverfolgung
- **Favoriten**: Kacheln zum Abspielen, mit ‹ › sortieren
- **Sender**: Suche nach Name oder Frequenz, Filter FM/DAB+, Favorit ☆,
  Bearbeiten ✎ (Name ändern, Logo hochladen/online suchen, Sender löschen)
- **Suchlauf**: FM, DAB+ oder beides

## Dashboards

### Eigene Radio-Karte

Die Karte wird von der Integration automatisch geladen – im Dashboard einfach
*Karte hinzufügen → „Yapaia Beat"* wählen oder per YAML:

```yaml
type: custom:yapaia-beat-card
entity: media_player.yapaia_beat
style: retro          # retro (Holz & LCD) oder modern
max_presets: 12       # Anzahl Favoriten-Tasten, 0 = aus
show_slide: true      # DAB+-Slideshow anzeigen
show_output: true     # Tasten Mini-PC / dieses Gerät
follow_entity: switch.yapaia_beat_auto_follow
```

### Standard-Karten

```yaml
# Senderanzeige mit Logo, Radiotext und Steuerung
type: media-control
entity: media_player.yapaia_beat
```

```yaml
# Favoriten-Auswahl als Kachel mit Dropdown
type: tile
entity: select.yapaia_beat_favorite
features:
  - type: select-options
```

```yaml
# Senderlogo groß
type: picture-entity
entity: image.yapaia_beat_logo
show_state: false
```

```yaml
type: entities
title: Radio
entities:
  - sensor.yapaia_beat_station          # zeigt das Logo als Symbol
  - sensor.yapaia_beat_frequency
  - sensor.yapaia_beat_now_playing
  - sensor.yapaia_beat_radiotext
  - sensor.yapaia_beat_signal
  - switch.yapaia_beat_auto_follow
  - button.yapaia_beat_next
  - button.yapaia_beat_scan_all
```

Favoriten-Tasten mit Standard-Karten (Beispiel):

```yaml
type: button
name: SWR3
icon: mdi:radio
tap_action:
  action: perform-action
  perform_action: yapaia_beat.play
  data:
    station: SWR3
```

## Entitäten

| Entität | Beschreibung |
|---|---|
| `media_player.yapaia_beat` | Radio: Play/Stop, Lautstärke, Quelle = Favoriten, vor/zurück, Medien durchsuchen (Favoriten/UKW/DAB+) |
| `select.yapaia_beat_favorite` | Favorit auswählen |
| `sensor.yapaia_beat_station` | Aktueller Sender (mit Logo als Bild) |
| `sensor.yapaia_beat_radiotext` | RDS-Radiotext bzw. DAB-DLS |
| `sensor.yapaia_beat_now_playing` | Interpret – Titel (RadioText+ / DLS) |
| `sensor.yapaia_beat_signal` | Empfangsqualität in % |
| `sensor.yapaia_beat_frequency` | Frequenz bzw. DAB-Kanal & Ensemble |
| `sensor.yapaia_beat_program_type` | Programmtyp (PTY) |
| `sensor.yapaia_beat_scan` / `_follow` | Status Suchlauf / Senderverfolgung |
| `switch.yapaia_beat_auto_follow` | Automatische Senderverfolgung |
| `switch.yapaia_beat_mute` | Stumm |
| `switch.yapaia_beat_local_output` | Lautsprecher am Mini-PC an/aus (Browser-Stream läuft weiter) |
| `select.yapaia_beat_output` | Ausgabe: Mini-PC, nur Browser oder ein anderer Media Player (Sonos, Chromecast, Music Assistant …) |
| `button.yapaia_beat_*` | Suchlauf FM/DAB+/beide, nächster/vorheriger Favorit, FM ±, Favorit umschalten |
| `image.yapaia_beat_logo` / `_slideshow` | Senderlogo / DAB+-Slideshow |

Attribute von `media_player.yapaia_beat`: `station_id`, `station_name`,
`band`, `frequency`, `channel`, `ensemble`, `pi`, `program_type`,
`radiotext`, `signal`, `stereo`, `logo`, `slide`, `favorites` (Liste mit
Namen und Logo-URLs) u. a.

## Aktionen (Dienste)

- `yapaia_beat.play` – `station` (Name), `station_id` oder `frequency` (MHz)
- `yapaia_beat.scan` – `band`: `fm`, `dab` oder `all`
- `yapaia_beat.set_favorite` – `station_id` (leer = aktueller Sender), `favorite`
- `yapaia_beat.set_output` – `output`: `local` (Mini-PC), `none` (nur
  Browser) oder die Entitäts-ID eines Media Players, z. B.
  `media_player.wohnzimmer`
- `yapaia_beat.announce` – `message` (Text), optional `engine` (TTS-Entität,
  leer = Standard), `language`, `priority` (`navigation`, `hinweis`, `info`):
  spricht den Text **in das laufende Radio** – siehe „Ansagen einmischen"
- sowie alle `media_player.*`-Aktionen, z. B. `media_player.select_source`
  mit dem Namen eines Favoriten oder `media_player.play_media` mit
  `media_content_id: "98.3"`

Beispiel-Automation: morgens SWR3 im Camper

```yaml
triggers:
  - trigger: time
    at: "07:30:00"
actions:
  - action: yapaia_beat.play
    data:
      station: SWR3
  - action: media_player.volume_set
    target:
      entity_id: media_player.yapaia_beat
    data:
      volume_level: 0.3
```

## Ausgabe wählen: Mini-PC, dieses Gerät oder andere Lautsprecher

Wie bei Spotify („Mit einem Gerät verbinden") wählst du, wo das Radio zu hören
ist:

- **Dieses Gerät** – das Gerät, mit dem du gerade Home Assistant bedienst
  (iPad, Handy, Android-Autoradio), im Browser bzw. in der App
- **Mini-PC** – die Lautsprecher am Home-Assistant-Rechner
- **Mini-PC + dieses Gerät**
- **Home-Assistant-Lautsprecher** – jeder Media Player in Home Assistant,
  der Musik von einer Adresse abspielen kann: Sonos, Chromecast/Google Nest,
  Music-Assistant-Player, DLNA-Geräte, Kodi … Die Liste füllt sich
  automatisch, sobald die Integration eingerichtet ist.

So geht's:

- **Add-on-Oberfläche** (Seitenleiste „Yapaia Beat"): Schaltfläche neben
  *Ausgabe* antippen → Gerät wählen.
- **Radio-Karte**: Taste 🔈 → Gerät wählen.
- **Standard-Karten/Automationen**: `select.yapaia_beat_output` oder die
  Aktion `yapaia_beat.set_output`.

Bei einem Home-Assistant-Lautsprecher startet die Integration den
Live-Stream auf dem Gerät, sobald das Radio läuft, und stoppt ihn, wenn du
das Radio ausschaltest. Senderwechsel laufen ohne Unterbrechung im selben
Stream weiter; der Lautstärkeregler steuert dann die Lautstärke des
Lautsprechers. Der Lautsprecher bekommt eine signierte Adresse von Home
Assistant (keine Portfreigabe nötig); dafür muss unter *Einstellungen → System
→ Netzwerk* eine im Heimnetz erreichbare URL stehen (Standard).

Der Ton auf „Dieses Gerät" läuft weiter, wenn du die Add-on-Seite verlässt
und zu einem anderen Dashboard wechselst – nur Neuladen oder Schließen von Home
Assistant beendet ihn. (Dafür muss die Integration eingerichtet sein; die
Add-on-Seite über Port 8099 ohne Home Assistant spielt nur, solange sie offen
ist.)

Die DAB+-Slideshow lässt sich antippen, um sie groß anzuzeigen.

Die Auswahl „Dieses Gerät" wird pro Gerät/Browser gespeichert, die übrigen
Ausgaben gelten für alle. Der Mini-PC lässt sich zusätzlich über
`switch.yapaia_beat_local_output` schalten (z. B. in einer Automation, wenn das
Autoradio verbunden ist).

Hinweise:

- Browser (vor allem Safari auf iPad/iPhone) erlauben Ton erst, nachdem man
  die Seite berührt hat. Beim Umschalten auf „Dieses Gerät" startet der Ton
  sofort. Wird die Seite neu geladen, startet er beim ersten Tippen irgendwo
  auf der Seite (z. B. auf einen Favoriten) – eine eigene Taste ist dafür
  nicht nötig.
- Die Wiedergabe im Browser ist ca. 2–4 Sekunden verzögert.
- Auf iPad/iPhone regelt man die Lautstärke mit den Gerätetasten (Safari
  erlaubt keine Lautstärkeregelung per Webseite). Auf Android funktioniert
  der Regler.
- Sender, Logo und die Tasten vor/zurück erscheinen auch auf dem
  Sperrbildschirm bzw. im Medien-Widget des Android-Autoradios.
- Die Home-Assistant-App (Companion) pausiert den Ton evtl., wenn sie in den
  Hintergrund geht. Fürs Autoradio daher die App/den Browser im Vordergrund
  lassen – oder den MP3-Stream (siehe unten) in einer Radio-/Player-App wie
  VLC öffnen, die im Hintergrund weiterspielt.

## Ansagen einmischen

Andere Yapaia-Module – zuerst die Navigation von **Yapaia Go** – und eigene
Automationen können etwas sagen, ohne das Radio zu unterbrechen: die Musik
wird in 0,3 s leiser (Option `announce_music_level`, Standard 20 %), die
Ansage darübergelegt und die Musik danach wieder lauter. Gemischt wird im
Add-on selbst, also für jede Ausgabe gleich: Mini-PC-Lautsprecher, Browser
und andere Lautsprecher bekommen einen durchgehenden Stream – nichts wird
gestoppt oder neu gestartet.

Mehrere Ansagen kommen nacheinander, `navigation` vor `hinweis` vor `info`.
Die Sprache erzeugt die Sprachausgabe (TTS) von Home Assistant.

Spielt gerade nichts (Radio aus und kein Player am Stream), schlägt die
Aktion fehl – Yapaia Go spricht dann wie gewohnt über `tts.speak`.

```yaml
actions:
  - action: yapaia_beat.announce
    data:
      message: Der Frischwassertank ist fast leer.
      priority: hinweis
```

### Mit Music Assistant

Ist Music Assistant installiert, als Ausgabe von Beat einfach den Player von
Music Assistant wählen (er steht in der Ausgabe-Liste mit 🎵 und dem Zusatz
„Music Assistant“).

Damit er dort erscheint, braucht es zweierlei:

1. Music Assistant als **Integration** in Home Assistant (Einstellungen →
   Geräte & Dienste → Music Assistant) – das Add-on allein reicht nicht.
2. In Music Assistant je Player: Einstellungen → Wiedergabegeräte → Player
   wählen → **„Dieses Wiedergabegerät für Home Assistant freigeben“**
   einschalten und speichern.

Ansagen gehen dann direkt an Music Assistant: die Musik wird
kurz pausiert bzw. bei Snapcast und Sonos leiser gemischt und läuft danach
weiter – ohne die Verzögerung des Streams. Die Antwort von
`yapaia_beat.announce` sagt, welcher Weg genommen wurde (`weg`:
`lautsprecher` oder `gemischt`).

#### Der Browser als Player von Music Assistant

Der Web-Player von Music Assistant („Web (Chrome on iPad)“) spielt nur,
solange die Seite von Music Assistant offen ist – wechselt man das
Dashboard, verstummt er. Yapaia Beat bringt deshalb einen eigenen mit, der im
Home-Assistant-Fenster selbst läuft und auf jedem Dashboard weiterspielt:

1. In Beat unter der Ausgabe **„Music Assistant in diesem Browser“**
   einschalten. Der Browser meldet sich als Player „Yapaia iPad“ (bzw.
   iPhone, Android-Tablet, Browser) bei Music Assistant an.
2. Music Assistant fragt einmal, ob es den Player zulassen soll: in Music
   Assistant → Einstellungen → Wiedergabegeräte → „Yapaia iPad“ öffnen und
   **ohne Kopplung verbinden**. Beat zeigt so lange „Music Assistant muss den
   Player einmal zulassen“.
3. Sobald Music Assistant ihn an Home Assistant weitergibt, steht er in der
   Ausgabe-Liste (🎵, „dieser Browser“) – auswählen.

Dann läuft das Radio über Music Assistant in diesem Browser, mit nur etwa
einer halben Sekunde Puffer, und Ansagen von Yapaia Go mischt Music
Assistant ein. Nach dem Neuladen von Home Assistant verlangt der Browser
einmal ein Tippen, bevor er Ton ausgeben darf.

Die Verbindung läuft über den Ingress von Music Assistant – derselbe Weg,
den dessen eigene Seite nimmt; es braucht keinen weiteren Port und keine
eigene Anmeldung. Gesucht wird das Add-on „Music Assistant“ (für
Administratoren jedes Add-on mit `music_assistant` im Namen).

Für andere Programme: `POST /api/announce?format=wav|mp3&priority=…` mit den
Audiodaten im Body (Antwort 409, wenn niemand zuhört).

## MP3-Stream

Unter `http://<home-assistant>:8099/stream.mp3` steht das laufende Programm als
MP3-Stream bereit (z. B. für Sonos, Chromecast oder das Handy). Dazu im Add-on
unter *Netzwerk* den Port `8099` freigeben. Der Port ist ohne Anmeldung
erreichbar – nur in vertrauenswürdigen Netzen freigeben.

Auf einem anderen Media Player abspielen:

```yaml
action: media_player.play_media
target:
  entity_id: media_player.wohnzimmer
data:
  media_content_id: http://homeassistant.local:8099/stream.mp3
  media_content_type: music
```

## Standby

Hört niemand zu – Lautsprecher am Mini-PC ausgeschaltet und kein Browser oder
Player mit dem Stream verbunden – stoppt Yapaia Beat nach `standby_minutes`
(Standard 10 Minuten) den Empfang. Das schont den RTL-SDR Stick (Wärme,
Stromverbrauch). Der Sender bleibt gespeichert: Sobald sich wieder ein Browser
verbindet, die Mini-PC-Lautsprecher eingeschaltet werden oder Play gedrückt
wird, geht es automatisch weiter. `standby_minutes: 0` schaltet den Standby ab.

## Automatische Senderverfolgung

Sinkt die Empfangsqualität länger als *Verzögerung* unter die *Schwelle*,
sucht Yapaia Beat in dieser Reihenfolge:

1. **UKW**: Frequenzen aus der RDS-AF-Liste und alle bekannten Frequenzen des
   Senders – nur Frequenzen mit **gleichem PI-Code** werden akzeptiert.
   **DAB+**: andere Kanäle, auf denen die Service-ID bekannt ist.
2. Wenn erlaubt: derselbe Sender **im anderen Band** (PI-Code = Service-ID
   oder gleicher Name, z. B. SWR3 UKW ↔ SWR3 DAB+).
3. Wenn erlaubt: **Bandsuche** nach PI-Code bzw. Service-ID.

Findet sich nichts Besseres, bleibt der Sender eingestellt und die Suche
pausiert zwei Minuten. Nach einem Ortswechsel lohnt sich ein neuer Suchlauf –
Favoriten bleiben erhalten und werden automatisch zugeordnet.

## Optionen

| Option | Beschreibung |
|---|---|
| `audio_output` | `local`: über HA-Audio + Stream, `stream`: nur MP3-Stream |
| `default_volume` | Lautstärke beim ersten Start |
| `rtl_gain` | `auto` oder Verstärkung in dB (z. B. `29.7`); bei Übersteuerung nahe starker Sender reduzieren |
| `ppm_correction` | Frequenzkorrektur des Sticks |
| `auto_follow` | Senderverfolgung (auch im Dashboard schaltbar) |
| `follow_threshold` / `follow_delay_s` | Schwelle in % / Verzögerung in s |
| `follow_cross_band` | Wechsel zwischen UKW und DAB+ erlauben |
| `follow_full_search` | Bandsuche als letzte Möglichkeit |
| `logo_lookup_online` / `country_code` | Logosuche online / Land |
| `fm_step_khz` | Kanalraster 100 kHz (Europa) oder 50 kHz |
| `fm_scan_threshold_db` | Empfindlichkeit des FM-Suchlaufs |
| `fm_deemphasis_us` | 50 µs (Europa) / 75 µs (Amerika) |
| `dab_prefilter` | DAB-Schnellsuchlauf |
| `mp3_bitrate` | Bitrate des MP3-Streams |
| `rtl_device_index` | Bei mehreren Sticks |
| `resume_last_station` | Nach Neustart weiterspielen |
| `install_integration` | Integration automatisch installieren/aktualisieren |

## Fehlersuche

- **„Kein RTL-SDR Stick gefunden"**: Yapaia Beat versucht alle 15 s, den
  Stick wieder anzusprechen, und spielt danach den letzten Sender weiter. Hilft
  das nicht, Stick kurz abziehen und wieder einstecken. Tritt es häufig auf:
  USB-Verlängerung/aktiven Hub verwenden (manche Sticks brauchen viel Strom
  und werden sehr warm).
  Unter *Einstellungen → System → Hardware* muss ein Gerät „RTL2838" o. ä.
  auftauchen. Läuft ein anderes Add-on mit dem Stick (z. B. rtl_433), dieses
  stoppen – ein Stick kann nur von einem Programm genutzt werden.
- **Proxmox / VM mit USB-Durchreichung**: Auf dem Proxmox-Host den
  DVB-T-Treiber sperren, sonst greift sich der Host den Stick nach jedem
  USB-Reset und streitet mit der VM darum:
  ```bash
  echo "blacklist dvb_usb_rtl28xxu" > /etc/modprobe.d/blacklist-rtlsdr.conf
  update-initramfs -u   # danach Host neu starten
  ```
  Den Stick in Proxmox per *Vendor/Device ID* (0bda:2838) an die VM geben.
- **Stick wird heiß / NESDR SMArTee**: Diese Sticks haben eine immer
  eingeschaltete Bias-Tee (4,5 V an der Antennenbuchse). Passive Antennen mit
  Gleichstrom-Kurzschluss (viele Dipole/Balun-Antennen) belasten den Stick
  dann dauerhaft – einen SMA-DC-Blocker zwischen Stick und Antenne setzen.
- **Kein Ton**: Unter *Einstellungen → Add-ons → Yapaia Beat → Audio* das
  richtige Ausgabegerät wählen. Der MP3-Stream funktioniert unabhängig davon.
- **Rauschen / wenige Sender**: Antenne verbessern, `rtl_gain` testen
  (z. B. `38.6`), `fm_scan_threshold_db` verkleinern.
- **Keine Logos**: Beim Suchlauf/Abspielen muss einmalig Internet vorhanden
  sein. Logos können auch im Sender-Dialog hochgeladen werden.
- **Integration nicht gefunden**: Home Assistant nach dem ersten Add-on-Start
  neu starten; prüfen, ob `/config/custom_components/yapaia_beat` existiert.
- Mehr Details: Option `log_level: debug` setzen und das Add-on-Log ansehen.

## Verwendete Software

- [welle.io / welle-cli](https://github.com/AlbrechtL/welle.io) (GPL-2.0) für DAB/DAB+
- [redsea](https://github.com/windytan/redsea) (MIT) für RDS
- [rtl-sdr](https://osmocom.org/projects/rtl-sdr) (GPL-2.0), LAME, mpg123, PulseAudio-Tools

Eine vollständige Liste aller verwendeten Projekte, Icons und Lizenzen steht in
[CREDITS.md](https://github.com/apfelsafft/radio/blob/main/CREDITS.md).
