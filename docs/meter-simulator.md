# Meter-Simulator (Test ohne echten Lesekopf)

Zum Testen ohne Hardware liegt ein kleines Bash-Skript bei, das einen seriellen
SML-Zähler simuliert: `bin/simulate_meter.sh`. Es erzeugt mit `socat` ein
virtuelles serielles Gerät und speist ein mitgeliefertes SML-Dump
(`data/testdata/sample.bin`, ein echtes SML-Telegramm) in einer Schleife ein.
vzLogger liest es wie einen echten Lesekopf. **Nicht** in der WebUI eingebunden.

## Verwendung

```
sudo /opt/loxberry/bin/plugins/smartmeter-ng/simulate_meter.sh
```

- Voraussetzung: `socat` (`sudo apt-get install socat`).
- **Muss als root laufen** (`sudo`) — sonst bricht es mit Hinweis ab, weil das
  Gerät unter `/dev` angelegt wird.
- Erzeugt standardmäßig das Gerät **`/dev/serial/smartmeter/SIM`** — also genau
  dort, wo die udev-Regel echte Köpfe anlegt. Dadurch wird es vom Plugin
  **automatisch erkannt**. Les-/gruppenbar für `loxberry` (vzLogger läuft als
  `loxberry`). Anpassbar über `SMARTMETER_SIM_DEVICE`, Intervall über
  `SMARTMETER_SIM_INTERVAL`.
- Dump-Datei optional als Argument:
  - **ohne Argument** → Standard-Sample `data/testdata/sample.bin`,
  - **nur ein Dateiname** (ohne Pfad) → wird in `data/testdata/` gesucht (auch
    mit angehängtem `.bin`), z. B.
    `simulate_meter.sh ISKRA_MT631-D2A51-V22-K0z_without_PIN.bin`,
  - **absoluter/relativer Pfad** → wird direkt verwendet.
  - In `data/testdata/` liegen ~37 SML-Aufzeichnungen realer Zähler (Quelle:
    <https://github.com/devZer0/libsml-testing>), siehe `data/testdata/README.md`.

## Im Plugin testen

1. **I/R Leseköpfe** → der Sim-Kopf `SIM` erscheint unter „Automatisch erkannte
   IR-Leseköpfe" (kein manuelles Hinzufügen nötig).
2. **Smartmeter** → SML-Meter auf diesem Device anlegen (Baudrate 9600,
   Parität 8n1) und speichern.
3. Beim Speichern läuft die **Auto-Discovery** und liest den simulierten Strom;
   die gefundenen OBIS-Kanäle erscheinen im **Kanäle**-Tab.

Das Standard-Sample `data/testdata/sample.bin` stammt aus
<https://github.com/hn/smldump> (dort `sample.dmp`).

## Hinweis: CRC-Korrektur des Standard-Samples

`sample.bin` enthält drei SML-Messages (OPEN_RESPONSE, GET_LIST_RESPONSE mit den
Messwerten, CLOSE_RESPONSE). Die auf dem LoxBerry installierte `libsml`
(Debian-Paket `libsml1`) **prüft die Per-Message-CRC** und verwirft Messages
mit falscher Prüfsumme (`sml_message_parse(): crc mismatch, dropping message`).
Im Original-Dump von hn/smldump waren die CRCs von OPEN_ und GET_LIST_RESPONSE
falsch — damit wurde ausgerechnet die Message mit den OBIS-Werten verworfen und
die Discovery fand keine Kanäle (`Got 0 new readings`).

Die CRCs in `data/testdata/sample.bin` wurden daher mit `sml_crc16` neu berechnet
(jede Message-CRC über den Bereich vom Message-Start `0x76` bis vor das CRC-Tag
`0x63`, big-endian, plus die abschließende Transport-CRC über den ganzen Frame,
CRC-16/X-25). Danach akzeptiert libsml alle drei Messages und vzLogger liefert
die Kennzahlen `1-0:1.8.0` (Bezug), `1-0:2.8.0` (Einspeisung) und
`1-0:16.7.0` (Leistung). Die Korrektur wurde als Pull Request an hn/smldump
zurückgemeldet.
