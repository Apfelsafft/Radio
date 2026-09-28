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

- **„Kein RTL-SDR Stick gefunden"**: Stick neu einstecken, Add-on neu starten.
  Unter *Einstellungen → System → Hardware* muss ein Gerät „RTL2838" o. ä.
  auftauchen. Läuft ein anderes Add-on mit dem Stick (z. B. rtl_433), dieses
  stoppen – ein Stick kann nur von einem Programm genutzt werden.
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
