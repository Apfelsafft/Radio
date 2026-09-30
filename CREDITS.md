# Credits

Yapaia Beat steht auf den Schultern großartiger Open-Source-Projekte.
Vielen Dank an alle Autorinnen und Autoren!

Der eigene Quellcode dieses Repositories (Radio-Dienst, Web-Oberfläche,
Home-Assistant-Integration, Lovelace-Karte, Skripte) wurde für Yapaia Beat neu
geschrieben und steht unter der [MIT-Lizenz](LICENSE). Code aus fremden
Repositories wurde nicht kopiert – die folgenden Projekte werden als
eigenständige Programme/Bibliotheken genutzt bzw. dienten als Vorlage.

## Im Add-on enthaltene Programme

Diese Programme werden beim Bauen des Add-on-Images heruntergeladen bzw.
installiert und behalten ihre eigenen Lizenzen.

| Projekt | Zweck | Autor:innen | Lizenz | Quelle |
|---|---|---|---|---|
| **welle.io / welle-cli** | DAB/DAB+-Empfang, DLS, Slideshow | Albrecht Lohofener, Matthias P. Brändli und Mitwirkende | GPL-2.0-or-later | <https://github.com/AlbrechtL/welle.io> |
| **redsea** | RDS-Decoder (PS, RadioText, RT+, AF, PI …) | Oona Räisänen (OH2EIQ) | MIT | <https://github.com/windytan/redsea> |
| **rtl-sdr** (`rtl_fm`, `rtl_power`, librtlsdr) | Ansteuerung des RTL-SDR Sticks, FM-Demodulation, Spektrumsmessung | Osmocom / Steve Markgraf und Mitwirkende | GPL-2.0-or-later | <https://osmocom.org/projects/rtl-sdr> |
| **liquid-dsp** | DSP-Bibliothek (von redsea genutzt) | Joseph D. Gaeddert | MIT | <https://github.com/jgaeddert/liquid-dsp> |
| **FFTW** | FFT-Bibliothek (von welle.io genutzt) | Matteo Frigo, Steven G. Johnson | GPL-2.0-or-later | <https://www.fftw.org> |
| **FAAD2** | AAC-Decoder für DAB+ (von welle.io genutzt) | M. Bakker, Nero AG und Mitwirkende | GPL-2.0-or-later | <https://github.com/knik0/faad2> |
| **LAME** | MP3-Encoder für den Stream | The LAME Project | LGPL-2.0-or-later | <https://lame.sourceforge.io> |
| **mpg123** | MP3-Decoder (DAB-Audio) | Michael Hipp, Thomas Orgis und Mitwirkende | LGPL-2.1 | <https://www.mpg123.de> |
| **libsndfile** | Audio-Bibliothek (von redsea genutzt) | Erik de Castro Lopo und Mitwirkende | LGPL-2.1-or-later | <https://github.com/libsndfile/libsndfile> |
| **nlohmann/json** | JSON-Bibliothek (Build von redsea/welle.io) | Niels Lohmann | MIT | <https://github.com/nlohmann/json> |
| **PulseAudio** (`pacat`) | Wiedergabe über die Home-Assistant-Audioausgabe | PulseAudio-Projekt | LGPL-2.1-or-later | <https://www.freedesktop.org/wiki/Software/PulseAudio/> |
| **NumPy** | Signalverarbeitung (FM-Stereo-Decoder) | NumPy Developers | BSD-3-Clause | <https://numpy.org> |
| **SciPy** | Filter/Signalverarbeitung | SciPy Developers | BSD-3-Clause | <https://scipy.org> |
| **aiohttp** | Webserver/HTTP-Client | aio-libs | Apache-2.0 | <https://github.com/aio-libs/aiohttp> |
| **Home Assistant Base Images** (Debian) | Grundlage des Add-on-Images | Home Assistant / Open Home Foundation | Apache-2.0 | <https://github.com/home-assistant/docker-base> |
| **s6-overlay** | Prozessverwaltung im Container | just-containers | ISC | <https://github.com/just-containers/s6-overlay> |
| **bashio** | Hilfsfunktionen für das Startskript | Franck Nijhof | MIT | <https://github.com/hassio-addons/bashio> |

## Icons

Die Symbole der Bedienelemente (Play, Stop, Vor/Zurück, Pfeile, Lautstärke,
Stumm, Stern, Lautsprecher, Gerät, Route) in der Web-Oberfläche und der
Lovelace-Karte verwenden SVG-Pfaddaten der
**[Google Material Icons](https://github.com/google/material-design-icons)**
(© Google, Apache-2.0).
Die Symbolnamen in Home Assistant (`mdi:radio` usw.) stammen von
**[Material Design Icons / Pictogrammers](https://pictogrammers.com/library/mdi/)**
(Apache-2.0).

Das Yapaia-Beat-Logo wurde für dieses Projekt neu gestaltet.

## Vorlagen, Standards und Dienste

- **redsea-Dokumentation** – der empfohlene `rtl_fm`-Aufruf für RDS
  (`-M fm -l 0 -A std -p 0 -F 9`) stammt aus der redsea-README
  (<https://github.com/windytan/redsea>).
- **welle.io** – die Einbettung der Web-Ressourcen beim Build (`xxd -i`) bildet
  die entsprechenden Schritte aus der CMake-Konfiguration von welle.io nach;
  die HTTP-Schnittstelle von welle-cli (`/mux.json`, `/mp3/…`, `/slide/…`) wird
  wie dort dokumentiert genutzt.
- **Home Assistant Add-on-Beispiel** – Aufbau von `config.yaml`, `build.yaml`
  und der s6-`run`/`finish`-Skripte folgt der offiziellen Vorlage
  (<https://github.com/home-assistant/addons-example>, Apache-2.0) und der
  Entwicklerdokumentation (<https://developers.home-assistant.io>).
- **ETSI EN 300 401** – Frequenztabelle der DAB-Kanäle in Band III.
- **IEC 62106 (RDS)** – Kodierung der Alternativfrequenzen (AF) und PI-Codes.
- **radio-browser.info** – freie Community-Datenbank, über deren API die
  Senderlogos gesucht werden (<https://www.radio-browser.info>). Die Logos
  selbst gehören den jeweiligen Rundfunkanbietern.
- **frenck/action-addon-linter** – Prüfung des Add-ons in der CI
  (<https://github.com/frenck/action-addon-linter>, MIT).

## Hinweis zu Lizenzen

Die oben genannten Programme werden nicht im Quellcode dieses Repositories
mitgeliefert, sondern beim Bauen des Add-on-Images aus ihren offiziellen
Quellen geladen (welle.io und redsea werden aus dem Quellcode kompiliert, die
übrigen stammen aus den Debian-Paketquellen). Für sie gelten ausschließlich
ihre eigenen Lizenzen; die MIT-Lizenz von Yapaia Beat bezieht sich nur auf den
Code in diesem Repository.
