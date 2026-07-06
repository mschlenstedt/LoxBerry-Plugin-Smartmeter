# SmartMeter v2 Benutzerdokumentation

## Überblick

SmartMeter v2 liest Zählerdaten auf dem LoxBerry. Die Legacy-Konfiguration unterstützt optische I/R-Leseköpfe, die unter `/dev/serial/smartmeter/` eingebunden sind.

Das Plugin kann die gelesenen Werte über mehrere Ausgänge bereitstellen:

- HTTP: Werte können über das Plugin-Webfrontend gelesen werden.
- UDP: Werte werden an alle konfigurierten Miniservers gesendet.
- MQTT: Werte werden über das LoxBerry MQTT Gateway veröffentlicht.

MQTT und UDP verwenden denselben Wertesatz.

## Voraussetzungen

- LoxBerry mit installiertem SmartMeter v2 Plugin.
- Mindestens ein unterstützter optischer I/R-Lesekopf.
- Ein konfigurierter Zähler in der Legacy-Konfiguration von SmartMeter v2.
- Für MQTT: Das LoxBerry MQTT Gateway muss installiert und konfiguriert sein.

## Konfiguration

Öffne SmartMeter v2 im LoxBerry-Webinterface und wechsle in die Legacy-Konfiguration.

### Automatisches Auslesen

Aktiviere das regelmäßige Auslesen, wenn das Plugin die Zähler automatisch lesen soll.

Mögliche Intervalle sind:

- minimal
- jede Minute
- alle 3, 5, 10, 15, 30 oder 60 Minuten

Ein manuelles Auslesen ist ebenfalls über das Plugin-Webinterface möglich.

### UDP-Ausgabe

Aktiviere **Daten per UDP senden**, um die Zählerwerte an die konfigurierten Miniservers zu senden.

Der UDP-Port kann in den Plugin-Einstellungen gesetzt werden. Die Daten werden an alle konfigurierten Miniservers gesendet.

### MQTT-Ausgabe

Aktiviere **Daten per MQTT senden**, um Zählerwerte über das LoxBerry MQTT Gateway zu veröffentlichen.

Das Plugin verwendet den UDP-Eingangsport des LoxBerry MQTT Gateways aus `general.json`. Im Plugin müssen keine separaten Broker-Zugangsdaten gepflegt werden.

Das MQTT-Basis-Topic kann in den Plugin-Einstellungen gesetzt werden.

Standard:

```text
smartmeter
```

Topic-Struktur:

```text
<Basis-Topic>/<Zähler>/<WertName>
```

Beispiel:

```text
smartmeter/ABC123/Consumption_Total_OBIS_1.8.0
```

Der MQTT-Payload enthält nur den Wert.

Beispiel-Payload:

```text
12345.678
```

Die Nachrichten werden mit Retain-Flag veröffentlicht.

## Zählerwerte

Die Wertnamen werden durch den Zählerleser erzeugt. Typische Beispiele sind:

- `Last_Update`
- `Last_UpdateLoxEpoche`
- `Consumption_Total_OBIS_1.8.0`
- `Consumption_Power_OBIS_1.7.0`
- `Delivery_Total_OBIS_2.8.0`
- `Total_Power_OBIS_15.7.0`

Die tatsächlich verfügbaren Werte hängen vom Zählertyp und Protokoll ab.

## Fehlersuche

### UDP funktioniert, aber MQTT-Werte erscheinen nicht

Prüfe folgende Punkte:

- MQTT-Ausgabe ist in den Plugin-Einstellungen aktiviert.
- Das MQTT-Basis-Topic ist nicht leer und enthält keine MQTT-Wildcards `#` oder `+`.
- Das LoxBerry MQTT Gateway ist installiert und läuft.
- Der UDP-Eingangsport des MQTT Gateways ist in LoxBerry konfiguriert.
- Im MQTT Gateway oder mit einem MQTT-Client auf `<Basis-Topic>/#` abonnieren.

### Es sind keine Zählerdaten verfügbar

Prüfe folgende Punkte:

- Der I/R-Lesekopf ist angeschlossen.
- Das Gerät existiert unter `/dev/serial/smartmeter/`.
- Die Zählerkonfiguration ist vollständig.
- Manuelles Auslesen über das Plugin-Webinterface funktioniert.

### Logdateien

Das Plugin schreibt Laufzeitlogs in das LoxBerry-Plugin-Logverzeichnis. In der Legacy-Oberfläche können die Logs über die Logansicht geprüft werden.
