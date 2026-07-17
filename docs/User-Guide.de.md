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

Die Tabs **Smartmeter Konfiguration (vzLogger)** und **Smartmeter Konfiguration (Legacy)** wechseln nur zwischen den Konfigurationsansichten. Ein weißes Badge mit grünem Häkchen markiert die aktive Implementierung, ein weißes Badge mit dunkelgrauem Minus eine inaktive. Legacy und vzLogger können nicht gleichzeitig aktiv sein, dürfen aber beide inaktiv sein. Das Einschalten einer Implementierung deaktiviert beim Speichern die andere; das Ausschalten aktiviert die andere nicht automatisch. Der Zustand wird erst beim Speichern angewendet. Nach einer Änderung zeigen die Aktiv-Schalter von vzLogger, SmartMeter-Bridge und Legacy deshalb den Hinweis **Änderung noch nicht gespeichert**.

Wähle oben bei **Implementierung** den Modus **vzLogger**. Beim Speichern entfernt das Plugin die Legacy-Cronjobs, damit nicht beide Reader parallel laufen.

Beim Wechsel zwischen den Implementierungen bleibt eine bereits vorhandene gültige `vzlogger.conf` erhalten. Das Aktivieren oder Deaktivieren von Legacy und der Zustand, in dem beide Implementierungen inaktiv sind, überschreiben diese Datei nicht. Wird vzLogger später wieder aktiviert, validiert und verwendet das Plugin die bestehende Konfiguration unverändert. Nur wenn keine gültige erzeugte vzLogger-Konfiguration vorhanden ist, werden die aktuellen Legacy-/Formwerte einmalig in eine neue `vzlogger.conf` migriert. Ein normales **Speichern und anwenden** innerhalb des bereits aktiven vzLogger-Modus erzeugt die Datei dagegen weiterhin bewusst aus den angezeigten vzLogger-Einstellungen neu.

Auch die Legacy-Zählerkonfiguration bleibt unabhängig erhalten. Zählerauswahl, manuelles Protokoll, Baudraten, Timeout, Delay, Handshake, Datenbits, Stoppbits, Parität und CRC werden intern in eigenen `LEGACY_*`-Schlüsseln gespeichert. Beim ersten Aufruf nach dem Update übernimmt das Plugin vorhandene Legacy-Werte einmalig in diesen Bereich. Danach verändert das Speichern einer vzLogger-Konfiguration diese Legacy-Werte nicht mehr. Beim Zurückschalten auf Legacy verwendet sowohl die Oberfläche als auch der Legacy-Abfrageprozess wieder die unveränderten Legacy-Einstellungen.

### Paketinstallation

Das Plugin richtet während der Installation bzw. beim Upgrade die Volkszaehler/Cloudsmith apt-Quelle ein. LoxBerry installiert danach `vzlogger` und `mosquitto-clients` über die normale `dpkg/apt`-Paketliste des Plugins. Wenn `vzlogger` bereits installiert ist, bleibt die bestehende Paketinstallation erhalten und wird durch apt auf die verfügbare aktuelle Version gebracht.

Nach der Installation stoppt und deaktiviert das Plugin den `vzlogger`-Dienst wieder, solange Legacy aktiv ist. vzLogger wird mit **Speichern und anwenden** im vzLogger-Modus gestartet; die MQTT-Bridge kann unabhaengig davon deaktiviert bleiben.

### Zählereinrichtung

Ein neu erkannter Lesekopf wird bis zum nächsten **Speichern und anwenden** im Panel als **Neu / ungespeichert** markiert. Führt ein solcher Meter bereits vor dem Anwenden eine OBIS-Suche aus, speichert das Plugin ausschließlich die dabei gewählte Standardprotokoll-Auswahl SML, D0 oder OMS in einer meterbezogenen Pending-Datei zwischen. Nach einem Seiten-Reload kann die Oberfläche dadurch das Protokoll wieder auswählen und die gefundenen OBIS-Kanäle anzeigen. Andere ungespeicherte Meter-Felder und insbesondere OMS-Schlüssel werden nicht als Entwurf persistiert. **Speichern und anwenden** sowie das endgültige Löschen des Meters entfernen diese Pending-Datei.

Aktiviere **Bridge-Service aktiv**, wenn die MQTT-Bridge die vzLogger-MQTT-Werte in den Plugin-HTTP-Cache und optional per UDP weitergeben soll. Der `vzlogger`-Dienst selbst bleibt im vzLogger-Modus unabhaengig von der Bridge startbar. Das **Aktualisierungsintervall** steuert, wie oft vzLogger Zaehlerwerte per MQTT veroeffentlicht; die Bridge verwendet denselben Takt fuer HTTP-Cache-Schreibungen und UDP-Sendungen. Das MQTT-Basis-Topic ist eine uebergreifende Einstellung und bleibt unabhaengig von den Dienstschaltflaechen konfigurierbar.

Schließe einen I/R-Lesekopf an und wähle **Nach I/R Leseköpfen suchen**. Die Suche läuft per AJAX und zeigt währenddessen ein nicht schließbares Overlay. Die Geräteprüfung selbst ist ein kurzer Verzeichniszugriff; antwortet die Anfrage dennoch 15 Sekunden lang nicht, wird sie als Fehler beendet. Nach Abschluss meldet das Overlay, ob keine Geräte, keine neuen Geräte, wirklich neue Leseköpfe oder angeschlossene, nur im Browser zum Löschen vorgemerkte Leseköpfe gefunden wurden. Wirklich neue und vorgemerkte Treffer können im selben Suchlauf auftreten und werden getrennt als `Name: Gerätepfad` aufgelistet. Vorgemerkte Treffer werden mitsamt ihren ungespeicherten Eingaben wieder eingeblendet; neue Lesekopf-Bereiche werden direkt in die bestehende Seite eingefügt. Es erfolgt kein Seiten-Reload. Nur wenn weder neue noch vorgemerkte Treffer gefunden wurden, schließt das Overlay nach einem sichtbaren Drei-Sekunden-Countdown automatisch. Ergebnisse mit neuen oder vorgemerkten Geräten, keine gefundenen Geräte und Fehler bleiben bis **Schließen** sichtbar. Unter dem Suchknopf erscheint für jeden erkannten Lesekopf ein eigener, zunächst eingeklappter Bereich. In dessen Überschrift stehen Name, Gerätepfad und gewähltes Protokoll. Zur Auswahl stehen SML, D0, OMS und **Benutzerdefiniert (JSON)**. Je nach Auswahl zeigt die Oberfläche ausschließlich die von diesem Protokoll unterstützten Meter-Parameter. Beim ersten Speichern werden bestehende SML- und D0-Zählervorgaben automatisch in das neue Schema überführt; ihre bekannten Baudraten und seriellen Werte bleiben erhalten. Ein Lesekopf ohne ausgewähltes Protokoll wird nicht als Meter erzeugt.

SML, D0 und OMS zeigen die OBIS-Suche und einen einheitlichen Channel-Editor für gefundene und manuell ergänzte Kanäle. Die Suche verwendet die aktuellen, noch nicht angewendeten Formulareinstellungen des Meters; nach dem erneuten Anlegen eines Meters ist deshalb kein vorheriges **Speichern und anwenden** nötig. Neue Identifier werden als aktive Zeile mit `api: null` ergänzt; ein bereits vorhandener vollständiger Identifier erzeugt beim Suchlauf keine weitere Zeile. Manuell darf derselbe Identifier dagegen mehrfach als eigenständiger vzLogger-Channel mit eigener UUID angelegt werden. Die Suche startet als browserunabhängiger Hintergrundauftrag. Ein Warte-Overlay mit Spinner fragt den Status jede Sekunde ab, bleibt nach einem Neuladen der Seite sichtbar und bietet **Suche abbrechen** an. Schließen, Neuladen oder Zurücknavigieren beendet den Auftrag nicht; der Hintergrundprozess speichert die gefundenen Kanäle selbst. Beim kontrollierten Abbruch stellt er den regulären vzLogger-Dienst wieder her. Für die Suche wird dieser Dienst kurz angehalten und ein unabhängig zeitlich begrenzter vzLogger-Testlauf im Vordergrund ausgeführt. Der Suchlauf prüft die Logdatei jede Sekunde und endet vorzeitig, sobald jeder erkannte OBIS-Kanal mindestens zweimal vorgekommen ist; 15 Sekunden bleiben die Sicherheitsobergrenze. Start, Stop und Restart entfernen zusätzlich passende Plugin-Testprozesse. Danach wird der reguläre Dienst wieder gestartet. Schlägt nur diese Wiederherstellung fehl, zeigt die Oberfläche eine Warnung; gefundene Kanäle bleiben erhalten. Nach einer erfolgreichen Suche aktualisiert die Oberfläche den Editor direkt ohne Seiten-Reload. Es werden sowohl vollständige Identifier wie `1-0:1.8.0` als auch kurze D0-Formen wie `1.8.0` akzeptiert. Falls das installierte vzLogger OMS nicht unterstützt, kennzeichnet die Oberfläche den Lesekopf und deaktiviert dessen OBIS-Suche; Prüfen und Anwenden melden dann ebenfalls die fehlende Runtime-Unterstützung.

Für SML, D0 und OMS können außerdem die allgemeinen Meter-Parameter `enabled`, `allowskip` und `aggtime` eingestellt werden. `aggtime` ist nicht SML-spezifisch, sondern für alle Meter-Protokolle zulässig; `-1` deaktiviert die Aggregation. Leere optionale Felder werden nicht in `vzlogger.conf` geschrieben. Insbesondere bleiben SML-Baudrate und -Parity standardmäßig leer, sodass vzLogger seine internen Standardwerte verwendet. Eine ausdrücklich gesetzte Baudrate oder Parity wird dagegen übernommen. Die Standardformulare verwenden immer den lokalen Gerätepfad des erkannten Lesekopfs. Ein SML- oder D0-Meter mit TCP-`host` wird deshalb ausschließlich als **Benutzerdefiniert (JSON)** angelegt.

Nach der Auswahl von SML oder D0 steht **Aus Vorlage initialisieren** zur Verfügung. Das Dropdown zeigt nur zum gewählten Protokoll passende Zählermodelle. Eine SML-Vorlage setzt ausschließlich Baudrate und seriellen Modus. Eine D0-Vorlage setzt die anfängliche Kommunikationsbaudrate, die Lesebaudrate, den seriellen Modus und das Lese-Timeout. Name, Aktivierung, Gerät, Intervalle, Sequenzen, OBIS-Kanäle und alle weiteren Meter-Einstellungen bleiben unverändert. Die übernommenen Werte sind zunächst nur im Browser geändert und müssen mit **Speichern und anwenden** gespeichert werden. Bei Zählermodellen, deren frühere Implementierung zusätzliche Sondersequenzen verwendet, weist die Oberfläche darauf hin, dass nur die verfügbaren Basiswerte übernommen werden.

Legacy und vzLogger verwenden denselben zentralen Zählervorlagenkatalog. Darin sind die Baudraten neutral als anfängliche Kommunikationsbaudrate und Betriebs-/Lesebaudrate hinterlegt. Legacy bildet diese Werte auf `STARTBAUDRATE` und `BAUDRATE` ab. Bei vzLogger verwendet SML die Betriebs-/Lesebaudrate als `baudrate`; D0 verwendet die anfängliche Kommunikationsbaudrate als `baudrate` und die Lesebaudrate als `baudrate_read`. Zählermodelle, serielle Einstellungen und Legacy-Sondersequenzen müssen dadurch nur noch an einer Stelle gepflegt werden.

**Benutzerdefiniert (JSON)** ist nur der GUI-Modus. Der Editor enthält genau ein vollständiges vzLogger-Meter-Objekt; dessen echtes `protocol`, beispielsweise `exec` oder `s0`, muss im Objekt stehen. Root-Sektionen wie `meters`, `mqtt` oder `local` sind nicht erlaubt. Die Eingabe wird mit Kommentaren und Formatierung unverändert als `vzlogger_meter_<lesekopf>.jsonc` gespeichert (maximal 64 KiB). Für `vzlogger.conf` werden Kommentare entfernt und gültiges JSON erzeugt. Meter-Defaults werden dabei nicht ergänzt. Nur innerhalb vorhandener `channels` ergänzt das Plugin eine fehlende stabile UUID und ein fehlendes `api` mit `"null"`; die JSONC-Quelldatei bleibt unverändert.

Ist ein benutzerdefiniertes Objekt syntaktisch oder strukturell ungültig, bleibt die Eingabe gespeichert, der betroffene Lesekopf erhält ein rotes Warnsymbol und die konkrete Fehlermeldung erscheint beim Aufklappen. Dieses Meter wird aus der neu erzeugten `vzlogger.conf` und aus `vzlogger_channels.json` ausgelassen, während andere gültige Meter erhalten bleiben. Ein nicht vorhandener absoluter `device`-Pfad wird ebenfalls sichtbar gewarnt, verhindert die Übernahme des Meter-Objekts aber nicht.

Am Ende jedes Lesekopf-Bereichs kann **Meter-Konfiguration entfernen** die Konfiguration zum Löschen vormerken. Der Bereich verschwindet sofort nur in der aktuellen Browseransicht; ein Neuladen oder erneutes Öffnen ohne **Speichern und anwenden** verwirft die Vormerkung vollständig. Erst **Speichern und anwenden** entfernt den Abschnitt aus `smartmeter.cfg`, die zugehörigen Einträge aus `vzlogger_channels.json` sowie meterbezogene JSONC-, OBIS-, Pending-, Test-, Log- und Runtime-Cachedateien. Dabei wird auch der Channel-Zustand der aktuellen Browseransicht verworfen. Wird das letzte Meter entfernt, ist eine Konfiguration ohne Meter ein gültiger ausgeschalteter Zustand: vzLogger und Bridge werden gestoppt und der SmartMeter-Service-Override wird entfernt. Ein entfernter, weiterhin angeschlossener Lesekopf bleibt bei normalen Seitenaufrufen ausgeblendet. **Nach I/R Leseköpfen suchen** hebt diese Markierung für aktuell erkannte Geräte auf und legt deren Standardeinstellungen ohne frühere OBIS-Kanäle wieder an; Protokoll, Meter- und Kanalauswahl müssen danach erneut konfiguriert und angewendet werden.

Das Plugin erzeugt:

- `vzlogger.conf` im Plugin-Konfigurationsverzeichnis.
- `vzlogger_channel_definitions.json` mit allen aktiven und inaktiven Channel-Definitionen sowie den je API gespeicherten Zielparametern.
- `vzlogger_channels.json` ausschließlich mit aktiven Plugin-Ausgaben und der stabilen Zuordnung von Channel-UUIDs zu SmartMeter-Ausgabeschlüsseln.

Verwende **Speichern und anwenden** für den normalen Ablauf; die Aktion speichert die aktuellen Formularwerte, erzeugt und prüft die Konfiguration und aktiviert sie. **Konfiguration prüfen** übernimmt die aktuellen Formularwerte dagegen nur in einen temporären Entwurf und erzeugt und prüft daraus temporäre Dateien. Dabei werden weder `smartmeter.cfg` noch `vzlogger.conf`, `vzlogger_channels.json` oder benutzerdefinierte Zählerdateien verändert und es werden keine Dienste gesteuert. Beide Aktionen laufen per AJAX ohne Seiten-Reload; das Overlay zeigt dabei die aktuelle Laufzeit. Erzeugen, Prüfen und Anwenden besitzen gemeinsam ein serverseitiges Zeitlimit von 60 Sekunden. Wird es erreicht, beendet das Plugin den gerade laufenden Unterprozess und zeigt den Fehler im Overlay. Bei **Speichern und anwenden** können Einstellungen oder bereits erfolgreich abgeschlossene Teilschritte zu diesem Zeitpunkt schon übernommen worden sein; der angezeigte Fehler und der Dienststatus müssen deshalb geprüft werden. Das Prüfergebnis bleibt im Overlay stehen, bis es aktiv geschlossen wird. Nach erfolgreichem Anwenden schließt das Overlay nach einem sichtbaren Drei-Sekunden-Countdown; Fehler bleiben zur Bestätigung geöffnet. Die Prüfung weist auch ungültige oder unrealistisch große Baudraten zurück.

Der Bridge-Service fuer HTTP-Cache und UDP ist optional und bei Neuinstallationen standardmaessig ausgeschaltet.

Pro Lesekopf verwaltet der Editor jede Channel-Instanz mit Aktivierung, OBIS-Identifier, Herkunft, API und optionaler SmartMeter-Ausgabe. Die Channel-Karten nutzen die gesamte Breite des aufgeklappten Lesekopfbereichs; nur der tatsächlich geöffnete Einstellungsinhalt wird durch einen sehr hellen pastellgelben Hintergrund und einen feinen Rand hervorgehoben. Kurze, dauerhaft sichtbare Hilfstexte stehen direkt unter den allgemeinen und API-spezifischen Eingabefeldern. Beim Ändern eines Feldes bleibt der Offen-/Geschlossen-Zustand der erweiterten Einstellungen je Channel erhalten. Der interne OBIS-Katalog zeigt einen deutschen oder englischen Kurznamen, Langbeschreibung, erwartete Einheit und eine fachliche Kategorie; bei unbekannten oder herstellerspezifischen Codes bleibt der Channel vollständig konfigurierbar und die A–F-Gruppen werden lesbar zerlegt. Ein eigener fachlicher Anzeigename überschreibt nur die Darstellung. Er wird ebenso wenig wie der technische **Ausgabeschlüssel (Cache/UDP)** in `vzlogger.conf` geschrieben, denn vzLogger kennt keinen allgemeinen Channel-Namen. Der Ausgabeschlüssel wird beim Anlegen aus dem OBIS-Identifier vorbelegt, kann anschließend geändert werden und ist die einzige über HTTP-Cache und UDP veröffentlichte Kennung. Er ist pro Lesekopf unter aktiven Plugin-Ausgaben ohne Beachtung der Groß-/Kleinschreibung eindeutig, maximal 64 Zeichen lang und auf Buchstaben, Ziffern und Unterstriche beschränkt.

Jede Channel-Zeile zeigt den aktuell angewendeten vzLogger-/MQTT-DATA-Index als **Kanal N**. Die Nummer wird aus der erzeugten `vzlogger.conf` gelesen und entspricht damit der Kanalnummer auf der Live-Daten-Seite; nicht angewendete oder inaktive Definitionen erscheinen als **Kanal –**. Im Kopf der erweiterten Einstellungen steht zusätzlich die persistente UUID in Grau. Nach erfolgreichem **Speichern und anwenden** aktualisiert die Seite die angewendeten Nummern ohne Neuladen.

Manuell angelegte Channel-Definitionen besitzen am Ende der erweiterten Einstellungen die Aktion **OBIS-Kanal entfernen**. Nach einer Bestätigung mit Kanalnummer, OBIS-Identifier und UUID wird die Karte nur im aktuellen Browserentwurf ausgeblendet. Ein Neuladen vor **Speichern und anwenden** verwirft die Vormerkung. Erst das Anwenden entfernt die Definition dauerhaft und erzeugt `vzlogger.conf` sowie `vzlogger_channels.json` ohne diesen Kanal neu. Gefundene Kanäle werden stattdessen über **Aktiv** deaktiviert, da sie bei einem späteren Suchlauf erneut erkannt werden können.

SML und D0 unterstützen einen optionalen Speicher-/Abrechnungsindex `*F`. Werte von 0 bis 254 wählen einen Wert, den der Zähler tatsächlich mit diesem vollständigen Identifier liefert; sie starten keine historische Abfrage und lesen kein Lastprofil. Den standardisierten unbenutzten Wert 255 stellt der Editor als **Nicht angegeben (255)** dar. Bestehende leere Werte, `null` und `*255` werden in diesen Zustand überführt und nicht als unnötiger `*255`-Suffix ausgegeben. Bei OMS ist das Feld deaktiviert und wird auch backendseitig ignoriert. **Aggregation** (`none`, `avg`, `max`, `sum`) ist eine zeitliche vzLogger-Verarbeitungseinstellung und keine Wertart. Sie ist nur bei meterweitem `aggtime > 0` aktiv. Neue bekannte Kanäle erhalten dann die Katalogempfehlung, bestehende Werte werden nicht überschrieben.

Die APIs schalten ausschließlich ihre eigenen Parameter frei. `null` besitzt keine Zielparameter. Volkszähler benötigt `middleware`; InfluxDB benötigt `host` und bietet Version-/Datenbank- beziehungsweise Bucket-, Organisations-, Messreihen-, Tag-, Authentifizierungs-, Timeout-, Batch/Puffer-, UUID- und TLS-Werte; MySmartGrid benötigt `middleware`, `secretKey`, `device` und `type` und kennzeichnet `name` ausdrücklich als MySmartGrid-Registrierungsname. `duplicates` gilt nur für Volkszähler und InfluxDB. Werte anderer APIs bleiben gespeichert, werden aber weder validiert noch in `vzlogger.conf` erzeugt. Im benutzerdefinierten JSON-Modus bleiben Channels Bestandteil des eingegebenen Meter-Objekts; deshalb wird dort kein separater Editor angezeigt.

### Anwenden

Mit **Speichern und anwenden** wird die Konfiguration erzeugt und geprüft. Das Plugin richtet fuer den `vzlogger`-Dienst einen systemd-Drop-in ein, der vzLogger direkt mit `/opt/loxberry/config/plugins/smartmeter-v2/vzlogger.conf` startet. Danach wird der Dienst fuer den Start nach einem LoxBerry-Neustart aktiviert und neu gestartet. Wenn **Bridge-Service aktiv** eingeschaltet ist, wird zusätzlich die MQTT-Bridge als systemd-Service installiert und gestartet; andernfalls wird nur die Bridge gestoppt.

Die erzeugte `vzlogger.conf` ordnet Sektionen und Parameter entsprechend der vzLogger-Dokumentation an. Die Root-Parameter beginnen mit `retry`, `verbosity` und `log`; anschließend folgen `local`, `mqtt` und `meters` mit jeweils fester Parameterreihenfolge.

Wenn der Legacy-Modus aktiv ist, stoppt das Anwenden vzLogger und die Bridge und entfernt den Plugin-Drop-in wieder. Eine fremde `/etc/vzlogger.conf` wird dabei nicht veraendert.

### Dienststeuerung

Die vzLogger-Seite zeigt oben im Bereich **Betrieb** zwei getrennte Dienst-Panels. Das erste Panel steuert den eigentlichen `vzlogger`-Dienst und enthält Status, Start/Stop/Restart, Log, Debug-Log, Log-Level und Live-Daten. Start, Stop und Restart besitzen jeweils einen eigenen Tooltip; beim automatischen Wechsel zwischen Start und Stop wechselt damit auch der angezeigte Hinweis. Die Aktionshinweise für diese Dienstschalter, die Lesekopf-Suche, die OBIS-Suche und **Generierte Konfiguration anzeigen** stehen zusätzlich in der rechten Hilfsspalte. **Generierte Konfiguration anzeigen** steht unten direkt vor dem Pfad zur erzeugten Konfiguration und öffnet `/opt/loxberry/config/plugins/smartmeter-v2/vzlogger.conf` schreibgeschützt und mit Zeilennummern in einem neuen Browser-Tab; `pass` und `keypass` werden dabei maskiert. Das zweite Panel steuert die **SmartMeter-Bridge**, einen Plugin-Zusatzdienst für HTTP-Cache und UDP; dessen Debug-Log-Schalter steht direkt neben der Loganzeige. Wird der noch ungespeicherte vzLogger-Aktiv-Schalter eingeschaltet, kann auch die Bridge sofort aktiviert werden, sofern MQTT eingeschaltet ist. Alle Bridge-Einstellungen einschließlich HTTP-Cache-Status werden erst bei aktiver Bridge freigegeben; der UDP-Port benötigt zusätzlich **UDP senden**. Stop bleibt für einen bereits laufenden Dienst verfügbar. Der Offen-/Geschlossen-Zustand aller aufklappbaren Bereiche wird lokal im Browser gespeichert und nach einem manuellen Reload wiederhergestellt.

Die Dienstzustaende werden im sichtbaren Browser-Tab alle drei Sekunden aktualisiert. Waehrend Start/Stop/Restart pausiert dieses Polling; ein Overlay benennt die laufende Aktion, und ihre AJAX-Antwort aktualisiert den echten Dienststatus direkt nach Abschluss. Bei Erfolg schliesst das Overlay automatisch. Dauert die Aktion laenger als 15 Sekunden, weist das Overlay darauf hin. **Ausblenden** schliesst nur das Overlay, waehrend der bereits gestartete Systemvorgang im Hintergrund weiterlaeuft; ein Fehler oeffnet das Overlay wieder und kann mit **Schliessen** bestaetigt werden. Start/Stop/Restart laufen ohne Seiten-Reload. Start/Restart werden freigegeben, sobald der zugehoerige Aktiv-Schalter eingeschaltet und eine gueltige erzeugte Konfiguration vorhanden ist; fuer die Bridge muss MQTT zusaetzlich gespeichert und in der erzeugten `vzlogger.conf` aktiv sein. Sie uebernehmen nur die jeweilige Dienst-Aktivierung. Beim vzLogger werden außerdem Debug-Log und Log-Level dauerhaft gespeichert und in der vorhandenen `vzlogger.conf` aktualisiert, bei der Bridge nur ihr Debug-Log-Schalter. Andere noch nicht gespeicherte Eingaben bleiben im Browser erhalten und werden erst mit **Speichern und anwenden** uebernommen. Stop bleibt bei einem laufenden Dienst unabhaengig von Aktiv-Schaltern und Konfigurationsfehlern verfuegbar. Start/Restart pruefen die vorhandene Konfiguration, erzeugen sie aber nicht neu; fehlt sie oder ist sie ungueltig, muss zuerst **Speichern und anwenden** ausgefuehrt werden. **Live-Daten (JSON) öffnen** ruft den integrierten vzLogger-HTTP-Dienst auf; `/` liefert wegen der aktivierten Indexfunktion alle konfigurierten Kanäle, `/<UUID>` einen einzelnen Kanal.

Unterhalb der Dienststeuerung sind die Einstellungen optisch in **vzLogger-Konfiguration** und **SmartMeter-Bridge-Konfiguration** getrennt und jeweils kurz beschrieben. Zaehler und I/R-Lesekoepfe gehoeren zur vzLogger-Konfiguration. Aktualisierungsintervall, HTTP-Cache und UDP-Ausgabe gehoeren zur Bridge-Konfiguration. Deaktivierte Bereiche grauen Eingabefelder, Beschriftungen und Hilfetexte gemeinsam aus, ohne ihre Werte zu veraendern. Bei einem inaktiven SML-, D0- oder OMS-Zaehler bleiben nur Beschreibung und **Meter aktiv** bearbeitbar. Der UDP-Port folgt dem noch nicht gespeicherten Schalter **UDP senden** sofort und wird nur bei aktiver Bridge und eingeschalteter UDP-Ausgabe bearbeitbar.

Zähler, Leseköpfe, Protokolle und OBIS-Kanäle gehören ausschließlich zur vzLogger-Konfiguration. vzLogger liest die Geräte und veröffentlicht die Messwerte über MQTT. Die SmartMeter-Bridge abonniert diese MQTT-Nachrichten und verwendet zusätzlich `vzlogger_channels.json`, um UUID beziehungsweise `chnX` auf Lesekopf, OBIS-Identifier und Ausgabename abzubilden. Die Bridge greift nicht direkt auf Zähler oder serielle Geräte zu. Aktualisierungsintervall, HTTP-Cache und UDP befinden sich deshalb in einem separaten, standardmäßig eingeklappten Bereich **SmartMeter-Bridge – Einstellungen**.

Unter **Erweiterte vzLogger-Diensteinstellungen** befindet sich die selten benoetigte Wiederholungswartezeit (`retry`). Der Bereich ist standardmaessig eingeklappt. `retry` legt die Wartezeit in Sekunden nach einer fehlgeschlagenen Anfrage fest und wird bei jeder Neuerzeugung der `vzlogger.conf` uebernommen. Debug-Log und Log-Level (`verbosity`) stehen direkt in der sichtbaren vzLogger-Dienstzeile.

Der ebenfalls eingeklappte Bereich **vzLogger HTTP-Dienst (local)** enthält alle Einstellungen des integrierten vzLogger-HTTP-Dienstes: `enabled`, `port`, `index`, `timeout` und `buffer`. Die Plugin-Standardwerte sind `true`, `18080`, `true`, `30` und `-1`. Beim Ringspeicher geben positive Werte die Anzahl Sekunden und negative Werte die Anzahl Datensätze je Kanal an. Alle Werte werden beim Neuerzeugen der `vzlogger.conf` übernommen.

Im eingeklappten Bereich **MQTT** sind die Einstellungen in **Verbindung und Veröffentlichung**, **Authentifizierung – Benutzer/Passwort** und **Authentifizierung – Zertifikat** gegliedert. Broker, Port und Benutzer zeigen den tatsächlich verwendeten Wert: Ein Plugin-Override hat Vorrang, danach folgt die LoxBerry-MQTT-Systemeinstellung und für Broker/Port zuletzt `127.0.0.1:1883`. Unveränderte Systemwerte werden beim Speichern nicht als Plugin-Override dupliziert; ein geleertes Feld schaltet wieder auf LoxBerry-Vererbung. Passwortfelder bleiben leer und maskiert und zeigen lediglich an, ob ein eigenes oder das LoxBerry-Passwort verwendet wird. Die erzeugte `vzlogger.conf` enthält die für vzLogger erforderlichen effektiven Zugangsdaten, lässt aber leere Client-ID-, Benutzer-, Passwort- und Zertifikatsparameter aus. Gespeicherte Passwörter werden weder in das GUI-HTML noch unmaskiert in Diagnoseausgaben geschrieben. Generator, interne MQTT-Bridge und Diagnose-Capture verwenden dieselben Verbindungseinstellungen. Da `mosquitto_sub` in der internen Bridge kein Schlüsselpasswort über die Kommandozeile übernimmt, muss der dort verwendete private Schlüssel ohne interaktive Rückfrage lesbar sein.

Neben den rohen JSON-Daten gibt es eine gerenderte Webseite, die sich alle zwei Sekunden aktualisiert. Sie gruppiert die Werte nach I/R-Lesekopf und Kanal und zeigt Kanalnummer, eigenen fachlichen Anzeigenamen beziehungsweise ersatzweise den deutschen OBIS-Katalog-Kurznamen, OBIS-Identifier, UUID sowie den rohen Timestamp mit lesbarer lokaler Zeit. Messwerte werden mit der Katalogeinheit dargestellt; elektrische SML-Zählerstände werden dabei vom vzLogger-Rohwert in Wh nach kWh umgerechnet, der Rohwert bleibt als Tooltip sichtbar. Die Kanal-Metadaten stammen aus `vzlogger_channels.json` und werden im Browser nur neu geladen, wenn sich das erzeugte Mapping ändert.

Wenn der Zaehler keinen Momentanleistungswert liefert, berechnet die MQTT-Bridge zusaetzlich `Consumption_CalculatedPower_OBIS_1.99.0` aus `1.8.0` und `Delivery_CalculatedPower_OBIS_2.99.0` aus `2.8.0`, sobald zwei unterschiedliche Zaehlerstaende vorliegen. Die Einheit folgt der Einheit des vom Zaehler gelieferten Zaehlerstands pro Stunde.

Das Bridge-Log liegt unter `/opt/loxberry/log/plugins/smartmeter-v2/vzlogger_mqtt_bridge.log` und wird bei 2 MB rotiert. Das Control-Log liegt unter `/opt/loxberry/log/plugins/smartmeter-v2/vzlogger_control.log`, wird bei 512 KB rotiert und kann über **Control-Log anzeigen** direkt unter den beiden Dienstbereichen geöffnet werden. Erfolgreiche Start-, Stop- und Restart-Aktionen werden kurz grün bestätigt; Warnungen und Fehler bleiben mit ihren Details im Aktionsfenster geöffnet. Apply- und Diagnose-Logs werden ebenfalls im Plugin-Logverzeichnis abgelegt; von `vzlogger_debug_*.log` bleiben die letzten fuenf Dateien erhalten. Das separate vzLogger-Debug-Log `/opt/loxberry/log/plugins/smartmeter-v2/vzlogger.log` wird nur bei aktivierter vzLogger-Debugoption geschrieben. Im Normalbetrieb schreibt vzLogger kein Dateilog.

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

Der bestehende HTTP-Endpunkt liefert weiterhin Werte aus diesen Cachedateien. Die vzLogger-Seite zeigt im Bereich **HTTP-Cache** den Cache-Status, die letzte Aktualisierung und einen direkten Link zum Cache-Endpunkt. Die Ausgabe beginnt immer mit `Last_Update` und `Last_UpdateLoxEpoche`. Danach folgt pro konfiguriertem Kanal ausschließlich dessen Ausgabeschlüssel, aufsteigend nach Kanalnummer (`chn0`, `chn1`, ...). Zusatzwerte ohne Kanalnummer folgen alphabetisch. Damit bleibt die Reihenfolge auch bei mehrfach identischen OBIS-Identifiern eindeutig. Wenn UDP aktiviert ist, sendet die Bridge die gecachten Werte im selben Aktualisierungsintervall und in derselben Reihenfolge an alle konfigurierten Miniservers.

## Debug-Log

Aktiviere **Debug-Log** in der Bridge-Zeile, bevor ein Bridge-Problem reproduziert wird. Dadurch protokolliert die MQTT-Bridge rohe MQTT-Topics, Payloads, UUID-Zuordnungen, erkannte Cache-Namen und ignorierte Nachrichten. Die getrennte Debug-Option beim vzLogger-Dienst steuert dessen eigenes Log.

Mit **Debug-Log erstellen** wird ein Diagnose-Log im Plugin-Logverzeichnis erzeugt, ohne die aktuellen Formularwerte zu speichern. Ein neuer Browser-Tab öffnet sofort eine Fortschrittsanzeige, überwacht die gesamte Operation und wechselt nach Fertigstellung zur LoxBerry-Logansicht; die Einstellungsseite zeigt kein zusätzliches Overlay und wird nicht neu geladen. Serverseitig wird die Erstellung nach 45 Sekunden beendet, falls sie nicht regulär fertig wird. Wird der neue Tab vorher geschlossen, kann der bereits gestartete Serverprozess noch bis zu diesem Zeitlimit weiterlaufen. Das Log enthält:

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

Bei Auswahl einer Zählervorlage zeigt der weiterhin deaktivierte Bereich **Manuelle Einstellung** die tatsächlich von der Vorlage verwendeten Werte. Diese Vorschau überschreibt die gespeicherte manuelle Konfiguration nicht. Nach erneuter Auswahl von **Manuelle Konfiguration** werden deshalb wieder die zuvor gespeicherten manuellen Werte angezeigt.

Beim Aktivieren und Speichern der Legacy-Seite setzt das Plugin den Modus auf **Legacy**, stoppt vzLogger und die MQTT-Bridge und stellt den Legacy-Cronjob wieder her, wenn **Zähler lesen** aktiviert ist. Wird Legacy ausgeschaltet und gespeichert, bleibt auch vzLogger inaktiv, bis es ausdrücklich auf seiner eigenen Seite aktiviert und gespeichert wird.

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
