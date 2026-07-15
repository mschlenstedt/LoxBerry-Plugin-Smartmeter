# SmartMeter v2 Benutzerdokumentation

## Überblick

SmartMeter v2 liest Zählerdaten auf dem LoxBerry. Die Standardimplementierung verwendet das externe Paket `vzlogger`. vzLogger liest den Zähler und veröffentlicht Werte per MQTT; das Plugin pflegt daraus einen lokalen Cache und stellt HTTP- und UDP-Ausgabe aus diesem Cache bereit.

Die Legacy-Implementierung bleibt weiterhin verfügbar. Verwende sie, wenn eine bestehende Installation auf dem alten Reader basiert oder wenn vzLogger eine benötigte Zählerkonfiguration noch nicht abdeckt.

## Voraussetzungen

- LoxBerry mit installiertem SmartMeter v2 Plugin.
- Mindestens ein unterstützter optischer I/R-Lesekopf unter `/dev/serial/smartmeter/`.
- Für die Standardimplementierung: installiertes `vzlogger`-Paket und `mosquitto-clients`. Beide Pakete werden während der Plugin-Installation über LoxBerry installiert.
- Für MQTT-Transport: Die LoxBerry MQTT-Broker-Einstellungen müssen in LoxBerry verfügbar sein.

## Standardkonfiguration mit vzLogger

Öffne SmartMeter v2 im LoxBerry-Webinterface und nutze die Seite **Smartmeter Konfiguration (vzLogger)**.

Die Tabs **Smartmeter Konfiguration (vzLogger)** und **Smartmeter Konfiguration (Legacy)** wechseln nur zwischen den Konfigurationsansichten. Der aktive Reader wird über das Feld **Implementierung** gewählt und erst beim Speichern angewendet.

Wähle oben bei **Implementierung** den Modus **vzLogger**. Beim Speichern entfernt das Plugin die Legacy-Cronjobs, damit nicht beide Reader parallel laufen.

### Paketinstallation

Das Plugin richtet während der Installation bzw. beim Upgrade die Volkszaehler/Cloudsmith apt-Quelle ein. LoxBerry installiert danach `vzlogger` und `mosquitto-clients` über die normale `dpkg/apt`-Paketliste des Plugins. Wenn `vzlogger` bereits installiert ist, bleibt die bestehende Paketinstallation erhalten und wird durch apt auf die verfügbare aktuelle Version gebracht.

Nach der Installation stoppt und deaktiviert das Plugin den `vzlogger`-Dienst wieder, solange Legacy aktiv ist. vzLogger wird mit **Speichern und anwenden** im vzLogger-Modus gestartet; die MQTT-Bridge kann unabhaengig davon deaktiviert bleiben.

### Zählereinrichtung

Aktiviere **Bridge-Service aktiv**, wenn die MQTT-Bridge die vzLogger-MQTT-Werte in den Plugin-HTTP-Cache und optional per UDP weitergeben soll. Der `vzlogger`-Dienst selbst bleibt im vzLogger-Modus unabhaengig von der Bridge startbar. Das **Aktualisierungsintervall** steuert, wie oft vzLogger Zaehlerwerte per MQTT veroeffentlicht; die Bridge verwendet denselben Takt fuer HTTP-Cache-Schreibungen und UDP-Sendungen. Das MQTT-Basis-Topic ist eine uebergreifende Einstellung und bleibt unabhaengig von den Dienstschaltflaechen konfigurierbar.

Schließe einen I/R-Lesekopf an und wähle **Nach I/R Leseköpfen suchen**. Wähle danach den erkannten Lesekopf und eine Zählervorgabe. Ein erkannter Lesekopf ohne Zählervorgabe reicht nicht aus; die Validierung bricht ab, weil vzLogger sonst ohne Meter starten würde. Der aktuelle Generator bildet Vorgaben auf die vzLogger-Protokolle `sml` oder `d0` ab. Für D0-Zähler können manuelle serielle Einstellungen gesetzt werden, wenn die Vorgaben nicht ausreichen.

Das Plugin erzeugt:

- `vzlogger.conf` im Plugin-Konfigurationsverzeichnis.
- `vzlogger_channels.json` mit der stabilen Zuordnung von Channel-UUIDs zu SmartMeter-Cache-Namen.

Verwende **Speichern und anwenden** fuer den normalen Ablauf; die Aktion schreibt, prueft und aktiviert die Konfiguration. Verwende **Konfiguration pruefen**, um eine gespeicherte oder manuell bearbeitete Konfiguration ohne Anwenden zu pruefen.

Der Bridge-Service fuer HTTP-Cache und UDP ist optional und bei Neuinstallationen standardmaessig ausgeschaltet.

Pro Lesekopf koennen bekannte OBIS-Kanaele ausgewaehlt und weitere zaehlerspezifische OBIS-Kanaele zeilenweise ergaenzt werden. Ein optionaler `*255`-Suffix wird beim Speichern entfernt, weil die erzeugte vzLogger-Konfiguration die Identifier ohne Suffix verwendet. Die bekannten Kanaele enthalten auch Hersteller-ID (`1-0:96.50.1`) und Server-ID (`1-0:96.1.0`), wenn der Zaehler diese Werte liefert.

### Anwenden

Mit **Speichern und anwenden** wird die Konfiguration erzeugt und geprüft. Das Plugin richtet fuer den `vzlogger`-Dienst einen systemd-Drop-in ein, der vzLogger direkt mit `/opt/loxberry/config/plugins/smartmeter-v2/vzlogger.conf` startet. Danach wird der Dienst fuer den Start nach einem LoxBerry-Neustart aktiviert und neu gestartet. Wenn **Bridge-Service aktiv** eingeschaltet ist, wird zusätzlich die MQTT-Bridge als systemd-Service installiert und gestartet; andernfalls wird nur die Bridge gestoppt.

Die erzeugte `vzlogger.conf` ordnet Sektionen und Parameter entsprechend der vzLogger-Dokumentation an. Die Root-Parameter beginnen mit `retry`, `verbosity` und `log`; anschließend folgen `local`, `mqtt` und `meters` mit jeweils fester Parameterreihenfolge.

Wenn der Legacy-Modus aktiv ist, stoppt das Anwenden vzLogger und die Bridge und entfernt den Plugin-Drop-in wieder. Eine fremde `/etc/vzlogger.conf` wird dabei nicht veraendert.

### Dienststeuerung

Die vzLogger-Seite zeigt oben im Bereich **Betrieb** zwei getrennte Dienst-Panels. Das erste Panel steuert den eigentlichen `vzlogger`-Dienst und enthält Status, Start/Stop/Restart, Log, Debug-Log, Log-Level und Live-Daten. Das zweite Panel steuert die **SmartMeter-Bridge**, einen Plugin-Zusatzdienst für HTTP-Cache und UDP; dessen Debug-Log-Schalter steht direkt neben der Loganzeige. Die Bridge kann nur aktiviert und gestartet werden, wenn die vzLogger-Implementierung und deren MQTT-Ausgabe aktiv sind; Stop bleibt verfügbar, falls ein bereits laufender Dienst beendet werden muss. Start- und Restart-Aktionen erzeugen und pruefen die gespeicherte Konfiguration vor dem Dienststart neu. **Live-Daten (JSON) öffnen** ruft den integrierten vzLogger-HTTP-Dienst auf; `/` liefert wegen der aktivierten Indexfunktion alle konfigurierten Kanäle, `/<UUID>` einen einzelnen Kanal.

Zähler, Leseköpfe, Protokolle und OBIS-Kanäle gehören ausschließlich zur vzLogger-Konfiguration. vzLogger liest die Geräte und veröffentlicht die Messwerte über MQTT. Die SmartMeter-Bridge abonniert diese MQTT-Nachrichten und verwendet zusätzlich `vzlogger_channels.json`, um UUID beziehungsweise `chnX` auf Lesekopf, OBIS-Identifier und Ausgabename abzubilden. Die Bridge greift nicht direkt auf Zähler oder serielle Geräte zu. Aktualisierungsintervall, HTTP-Cache und UDP befinden sich deshalb in einem separaten, standardmäßig eingeklappten Bereich **SmartMeter-Bridge – Einstellungen**.

Unter **Erweiterte vzLogger-Diensteinstellungen** befindet sich die selten benoetigte Wiederholungswartezeit (`retry`). Der Bereich ist standardmaessig eingeklappt. `retry` legt die Wartezeit in Sekunden nach einer fehlgeschlagenen Anfrage fest und wird bei jeder Neuerzeugung der `vzlogger.conf` uebernommen. Debug-Log und Log-Level (`verbosity`) stehen direkt in der sichtbaren vzLogger-Dienstzeile.

Der ebenfalls eingeklappte Bereich **vzLogger HTTP-Dienst (local)** enthält alle Einstellungen des integrierten vzLogger-HTTP-Dienstes: `enabled`, `port`, `index`, `timeout` und `buffer`. Die Plugin-Standardwerte sind `true`, `18080`, `true`, `30` und `-1`. Beim Ringspeicher geben positive Werte die Anzahl Sekunden und negative Werte die Anzahl Datensätze je Kanal an. Alle Werte werden beim Neuerzeugen der `vzlogger.conf` übernommen.

Im eingeklappten Bereich **MQTT** sind die Einstellungen in **Verbindung und Veröffentlichung**, **Authentifizierung – Benutzer/Passwort** und **Authentifizierung – Zertifikat** gegliedert. Broker, Port und Benutzer zeigen den tatsächlich verwendeten Wert: Ein Plugin-Override hat Vorrang, danach folgt die LoxBerry-MQTT-Systemeinstellung und für Broker/Port zuletzt `127.0.0.1:1883`. Unveränderte Systemwerte werden beim Speichern nicht als Plugin-Override dupliziert; ein geleertes Feld schaltet wieder auf LoxBerry-Vererbung. Passwortfelder bleiben leer und maskiert und zeigen lediglich an, ob ein eigenes oder das LoxBerry-Passwort verwendet wird. Die erzeugte `vzlogger.conf` enthält die für vzLogger erforderlichen effektiven Zugangsdaten, lässt aber leere Client-ID-, Benutzer-, Passwort- und Zertifikatsparameter aus. Gespeicherte Passwörter werden weder in das GUI-HTML noch unmaskiert in Diagnoseausgaben geschrieben. Generator, interne MQTT-Bridge und Diagnose-Capture verwenden dieselben Verbindungseinstellungen. Da `mosquitto_sub` in der internen Bridge kein Schlüsselpasswort über die Kommandozeile übernimmt, muss der dort verwendete private Schlüssel ohne interaktive Rückfrage lesbar sein.

Neben den rohen JSON-Daten gibt es eine gerenderte Webseite, die sich alle zwei Sekunden aktualisiert. Sie gruppiert die Werte nach I/R-Lesekopf und Kanal und zeigt Kanalnummer, konfigurierten Namen, OBIS-Identifier, UUID sowie den rohen Timestamp mit lesbarer lokaler Zeit. Die Kanal-Metadaten stammen aus `vzlogger_channels.json` und werden im Browser nur neu geladen, wenn sich das erzeugte Mapping ändert.

Wenn der Zaehler keinen Momentanleistungswert liefert, berechnet die MQTT-Bridge zusaetzlich `Consumption_CalculatedPower_OBIS_1.99.0` aus `1.8.0` und `Delivery_CalculatedPower_OBIS_2.99.0` aus `2.8.0`, sobald zwei unterschiedliche Zaehlerstaende vorliegen. Die Einheit folgt der Einheit des vom Zaehler gelieferten Zaehlerstands pro Stunde.

Das Bridge-Log liegt unter `/opt/loxberry/log/plugins/smartmeter-v2/vzlogger_mqtt_bridge.log` und wird bei 2 MB rotiert. Das Control-Log liegt unter `/opt/loxberry/log/plugins/smartmeter-v2/vzlogger_control.log` und wird bei 512 KB rotiert. Apply- und Diagnose-Logs werden ebenfalls im Plugin-Logverzeichnis abgelegt; von `vzlogger_debug_*.log` bleiben die letzten fuenf Dateien erhalten. Das separate vzLogger-Debug-Log `/opt/loxberry/log/plugins/smartmeter-v2/vzlogger.log` wird nur bei aktivierter vzLogger-Debugoption geschrieben. Im Normalbetrieb schreibt vzLogger kein Dateilog.

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

Die Bridge sammelt erkannte vzLogger-Nachrichten im Arbeitsspeicher und schreibt sie im Aktualisierungsintervall als Legacy-kompatible `.data`-Cachedateien:

```text
/var/run/shm/<Plugin-Ordner>/
```

Der bestehende HTTP-Endpunkt liefert weiterhin Werte aus diesen Cachedateien. Die vzLogger-Seite zeigt im Bereich **HTTP-Cache** den Cache-Status, die letzte Aktualisierung und einen direkten Link zum Cache-Endpunkt. Wenn UDP aktiviert ist, sendet die Bridge die gecachten Werte im selben Aktualisierungsintervall an alle konfigurierten Miniservers.

## Debug-Log

Aktiviere **Debug-Log** in der Bridge-Zeile, bevor ein Bridge-Problem reproduziert wird. Dadurch protokolliert die MQTT-Bridge rohe MQTT-Topics, Payloads, UUID-Zuordnungen, erkannte Cache-Namen und ignorierte Nachrichten. Die getrennte Debug-Option beim vzLogger-Dienst steuert dessen eigenes Log.

Mit **Debug-Log erstellen** wird ein Diagnose-Log im Plugin-Logverzeichnis erzeugt. Es enthält:

- Paket-, apt-Source-, Service-, Bridge- und Validierungsstatus
- letzte vzLogger-Control- und Web-Aktionsausgaben
- Ausgabe von `vzlogger --version`, falls verfügbar
- aktuelle `systemctl`- und `journalctl`-Auszüge
- Plugin-Konfiguration, generierte `vzlogger.conf` und `vzlogger_channels.json`
- Ende des Bridge-Logs
- verfügbare LoxBerry-Installations- und Plugin-Logauszüge
- aktuelle `.data`-Cachedateien
- begrenzten MQTT-Mitschnitt von `<Basis-Topic>/vzlogger/#`, wenn `timeout` und `mosquitto_sub` verfügbar sind

Dieses Debug-Log enthält die Informationen, die benötigt werden, um das reale vzLogger-MQTT-Topic- und Payload-Format zu prüfen und den MQTT-Parser final anzupassen.

## Legacy-Konfiguration

Die Legacy-Implementierung bleibt über **Smartmeter Konfiguration (Legacy)** verfügbar. Sie unterstützt optische I/R-Leseköpfe unter `/dev/serial/smartmeter/` und kann Zähler weiterhin mit den älteren SmartMeter-Skripten zyklisch auslesen.

Beim Speichern der Legacy-Seite setzt das Plugin den Modus auf **Legacy**, stoppt vzLogger und die MQTT-Bridge und stellt den Legacy-Cronjob wieder her, wenn **Zähler lesen** aktiviert ist.

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

Prüfe das LoxBerry-Installationslog. Entscheidend sind die Schritte `PREROOT`, `Refreshing APT database` und `Installing additional software packages`. Wenn die Volkszaehler/Cloudsmith-Quelle für Codename oder Architektur nicht verfügbar ist, kann LoxBerry das Paket `vzlogger` nicht installieren.

### Es werden keine Cachewerte geschrieben

Prüfe folgende Punkte:

- `vzlogger` läuft.
- Die MQTT-Bridge läuft als Service oder Fallback-Prozess.
- `mosquitto_sub` ist installiert.
- `vzlogger_channels.json` existiert und validiert erfolgreich.
- Das Debug-Log enthält reale MQTT-Nachrichten unter `<Basis-Topic>/vzlogger/#`.

### HTTP oder UDP liefern keine Werte

Prüfe im Bereich **HTTP-Cache**, ob eine `.data`-Datei und eine aktuelle letzte Aktualisierung angezeigt werden. Alternativ prüfe direkt, ob `.data`-Dateien unter `/var/run/shm/<Plugin-Ordner>/` existieren. HTTP und UDP verwenden diesen Cache und fragen vzLogger nicht direkt ab.

### Legacy-Auslesen liefert keine Zählerdaten

Prüfe folgende Punkte:

- Der I/R-Lesekopf ist angeschlossen.
- Das Gerät existiert unter `/dev/serial/smartmeter/`.
- Die Legacy-Zählerkonfiguration ist vollständig.
- Manuelles Auslesen über die Legacy-Oberfläche funktioniert.

### Logdateien

Das Plugin schreibt Laufzeitlogs in das LoxBerry-Plugin-Logverzeichnis und nach `/var/run/shm/<Plugin-Ordner>/`. In der Legacy-Oberfläche können die Legacy-Lese- und Veröffentlichungslogs über die Logansicht geprüft werden.
