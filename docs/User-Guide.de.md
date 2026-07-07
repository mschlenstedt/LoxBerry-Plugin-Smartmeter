# SmartMeter v2 Benutzerdokumentation

## Überblick

SmartMeter v2 liest Zählerdaten auf dem LoxBerry. Die Standardimplementierung verwendet das externe Paket `vzlogger`. vzLogger liest den Zähler und veröffentlicht Werte per MQTT; das Plugin pflegt daraus einen lokalen Cache und stellt HTTP- und UDP-Ausgabe aus diesem Cache bereit.

Die Legacy-Implementierung bleibt weiterhin verfügbar. Verwende sie, wenn eine bestehende Installation auf dem alten Reader basiert oder wenn vzLogger eine benötigte Zählerkonfiguration noch nicht abdeckt.

## Voraussetzungen

- LoxBerry mit installiertem SmartMeter v2 Plugin.
- Mindestens ein unterstützter optischer I/R-Lesekopf unter `/dev/serial/smartmeter/`.
- Für die Standardimplementierung: installiertes `vzlogger`-Paket und `mosquitto-clients`.
- Für MQTT-Transport: Die LoxBerry MQTT-Broker-Einstellungen müssen in LoxBerry verfügbar sein.

## Standardkonfiguration mit vzLogger

Öffne SmartMeter v2 im LoxBerry-Webinterface und nutze die Seite **Smartmeter Konfiguration (vzLogger)**.

### Paketinstallation

Wenn `vzlogger` fehlt, verwende **vzLogger-Paket installieren**. Der Helfer richtet das Volkszaehler/Cloudsmith apt-Repository ein und installiert `vzlogger` per apt. Diese Aktion benötigt Root-Rechte auf dem Zielsystem.

`mosquitto-clients` bleibt eine reguläre Plugin-Abhängigkeit, weil die MQTT-Bridge `mosquitto_sub` verwendet.

### Zählereinrichtung

Aktiviere **Zähler lesen**, damit vzLogger und die MQTT-Bridge Live-Werte bereitstellen.

Wähle den erkannten I/R-Lesekopf und eine Zählervorgabe. Der aktuelle Generator bildet Vorgaben auf die vzLogger-Protokolle `sml` oder `d0` ab. Für D0-Zähler können manuelle serielle Einstellungen gesetzt werden, wenn die Vorgaben nicht ausreichen.

Das Plugin erzeugt:

- `vzlogger.conf` im Plugin-Konfigurationsverzeichnis.
- `vzlogger_channels.json` mit der stabilen Zuordnung von Channel-UUIDs zu SmartMeter-Cache-Namen.

Verwende **Speichern und Konfiguration erzeugen**, um die Dateien zu schreiben und strukturell zu prüfen. Verwende **Konfiguration prüfen**, um die Prüfung ohne Anwenden erneut auszuführen.

### Anwenden

Mit **Speichern und anwenden** wird die Konfiguration erzeugt und geprüft, nach `/etc/vzlogger.conf` kopiert, `vzlogger` neu gestartet und die MQTT-Bridge gestartet.

Wenn das Zählerlesen deaktiviert ist, stoppt das Anwenden vzLogger und die Bridge.

### Bridge-Service

Mit **Bridge-Service installieren** wird die MQTT-Bridge als systemd-Service installiert. Ohne Service kann das Control-Skript weiterhin einen direkt gestarteten Bridge-Prozess als Fallback verwenden.

Der Service heißt:

```text
smartmeter-v2-vzlogger-bridge
```

## MQTT-, HTTP- und UDP-Datenfluss

vzLogger veröffentlicht unter:

```text
<Basis-Topic>/vzlogger
```

Die MQTT-Bridge abonniert:

```text
<Basis-Topic>/vzlogger/#
```

Die Bridge wandelt erkannte vzLogger-Nachrichten in Legacy-kompatible `.data`-Cachedateien um:

```text
/var/run/shm/<Plugin-Ordner>/
```

Der bestehende HTTP-Endpunkt liefert weiterhin Werte aus diesen Cachedateien. Wenn UDP aktiviert ist, sendet die Bridge die gecachten Werte zyklisch an alle konfigurierten Miniservers.

## Debug-Log

Aktiviere **Debug-Log**, bevor ein Problem reproduziert wird. Dadurch protokolliert die MQTT-Bridge rohe MQTT-Topics, Payloads, UUID-Zuordnungen, erkannte Cache-Namen und ignorierte Nachrichten.

Mit **Debug-Log erstellen** wird ein Diagnose-Log im Laufzeitverzeichnis erzeugt. Es enthält:

- Paket-, apt-Source-, Service-, Bridge- und Validierungsstatus
- Ausgabe von `vzlogger --version`, falls verfügbar
- aktuelle `systemctl`- und `journalctl`-Auszüge
- Plugin-Konfiguration, generierte `vzlogger.conf` und `vzlogger_channels.json`
- Ende des Bridge-Logs
- aktuelle `.data`-Cachedateien
- begrenzten MQTT-Mitschnitt von `<Basis-Topic>/vzlogger/#`, wenn `timeout` und `mosquitto_sub` verfügbar sind

Dieses Debug-Log enthält die Informationen, die benötigt werden, um das reale vzLogger-MQTT-Topic- und Payload-Format zu prüfen und den MQTT-Parser final anzupassen.

## Legacy-Konfiguration

Die Legacy-Implementierung bleibt über **Smartmeter Konfiguration (Legacy)** verfügbar. Sie unterstützt optische I/R-Leseköpfe unter `/dev/serial/smartmeter/` und kann Zähler weiterhin mit den älteren SmartMeter-Skripten zyklisch auslesen.

Der Legacy-Pfad kann Werte über mehrere Ausgänge bereitstellen:

- HTTP: Werte können über das Plugin-Webfrontend gelesen werden.
- UDP: Werte werden an alle konfigurierten Miniservers gesendet.
- MQTT: Werte werden über das LoxBerry MQTT Gateway veröffentlicht.

Für Legacy-MQTT kann das MQTT-Basis-Topic in den Plugin-Einstellungen gesetzt werden.

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

Der Legacy-MQTT-Payload enthält nur den Wert. Die Nachrichten werden mit Retain-Flag veröffentlicht.

## Zählerwerte

Typische Wertnamen sind:

- `Last_Update`
- `Last_UpdateLoxEpoche`
- `Consumption_Total_OBIS_1.8.0`
- `Consumption_Power_OBIS_1.7.0`
- `Delivery_Total_OBIS_2.8.0`
- `Total_Power_OBIS_15.7.0`

Die tatsächlich verfügbaren Werte hängen vom Zählertyp, Protokoll und den konfigurierten OBIS-Kanälen ab.

## Fehlersuche

### vzLogger-Paketinstallation schlägt fehl

Prüfe, ob Codename und Architektur des Zielsystems vom Volkszaehler/Cloudsmith-Repository unterstützt werden. Führe den Paketinstaller als root aus und hänge das Debug-Log an, wenn die Ursache nicht offensichtlich ist.

### Es werden keine Cachewerte geschrieben

Prüfe folgende Punkte:

- `vzlogger` läuft.
- Die MQTT-Bridge läuft als Service oder Fallback-Prozess.
- `mosquitto_sub` ist installiert.
- `vzlogger_channels.json` existiert und validiert erfolgreich.
- Das Debug-Log enthält reale MQTT-Nachrichten unter `<Basis-Topic>/vzlogger/#`.

### HTTP oder UDP liefern keine Werte

Prüfe, ob `.data`-Dateien unter `/var/run/shm/<Plugin-Ordner>/` existieren. HTTP und UDP verwenden diesen Cache und fragen vzLogger nicht direkt ab.

### Legacy-Auslesen liefert keine Zählerdaten

Prüfe folgende Punkte:

- Der I/R-Lesekopf ist angeschlossen.
- Das Gerät existiert unter `/dev/serial/smartmeter/`.
- Die Legacy-Zählerkonfiguration ist vollständig.
- Manuelles Auslesen über die Legacy-Oberfläche funktioniert.

### Logdateien

Das Plugin schreibt Laufzeitlogs in das LoxBerry-Plugin-Logverzeichnis und nach `/var/run/shm/<Plugin-Ordner>/`. In der Legacy-Oberfläche können die Legacy-Lese- und Veröffentlichungslogs über die Logansicht geprüft werden.
