# Smartmeter-NG Benutzerdokumentation

## Überblick

Smartmeter-NG liest Zählerdaten auf dem LoxBerry über das externe Paket `vzlogger`. vzLogger liest den Zähler und veröffentlicht Werte per MQTT; das Plugin pflegt daraus einen lokalen Cache und stellt HTTP- und UDP-Ausgabe aus diesem Cache bereit.

Die frühere Legacy-Implementierung mit eigenem Perl-Reader wurde entfernt. Sie wird nur noch im Branch `Version1` gepflegt.

## Voraussetzungen

- LoxBerry mit installiertem Smartmeter-NG Plugin.
- Mindestens ein unterstützter optischer I/R-Lesekopf unter `/dev/serial/smartmeter/`.
- Für die Standardimplementierung: installiertes `vzlogger`-Paket und `mosquitto-clients`. Beide Pakete werden während der Plugin-Installation über LoxBerry installiert.
- Für MQTT-Transport: Die LoxBerry MQTT-Broker-Einstellungen müssen in LoxBerry verfügbar sein.

## Standardkonfiguration mit vzLogger

Öffne Smartmeter-NG im LoxBerry-Webinterface.

Ein weißes Badge mit grünem Häkchen markiert die aktive Implementierung, ein weißes Badge mit dunkelgrauem Minus eine inaktive. Der Zustand wird erst beim Speichern angewendet. Nach einer Änderung zeigen die Aktiv-Schalter von vzLogger und SmartMeter-Bridge deshalb den Hinweis **Änderung noch nicht gespeichert**.

Wähle oben bei **Implementierung** den Modus **vzLogger**, um das Auslesen zu aktivieren.

Eine bereits vorhandene gültige `vzlogger.conf` bleibt beim Deaktivieren und erneuten Aktivieren erhalten und wird unverändert weiterverwendet. Nur wenn keine gültige erzeugte vzLogger-Konfiguration vorhanden ist, wird sie einmalig aus den aktuellen Formwerten erzeugt. Ein normales **Speichern und anwenden** erzeugt die Datei dagegen weiterhin bewusst aus den angezeigten vzLogger-Einstellungen neu.

Konfigurations- und Dienstaktionen werden serialisiert. Läuft bereits eine Aktion, wird eine weitere Anfrage ohne Änderungen an Dateien oder Diensten abgewiesen. **Speichern und anwenden** erzeugt und prüft zunächst einen geschützten Staging-Satz; erst danach werden `vzlogger.conf` und Channel-Mapping ersetzt. Schlägt Prüfung oder Übernahme fehl, bleiben die letzten gültigen Laufzeitdateien erhalten, während die eingegebenen Einstellungen zur Korrektur gespeichert bleiben.

Die benutzerdefinierte JSONC-Quelle bleibt unverändert. Fehlende Channel-UUIDs werden intern in einer versionierten Datei `vzlogger_user_channel_uuids_<lesekopf>.json` gespeichert. Bei der ersten Migration bleiben bisher erzeugte UUIDs erhalten; unveränderte Channels behalten ihre UUID auch nach einer Umordnung. Wenn die Identität zusätzlich inhaltliche Änderungen am Channel überstehen muss, ist eine explizite UUID anzugeben.



### Paketinstallation

Das Plugin richtet während der Installation bzw. beim Upgrade die Volkszaehler/Cloudsmith apt-Quelle ein. LoxBerry installiert danach `vzlogger` und `mosquitto-clients` über die normale `dpkg/apt`-Paketliste des Plugins. Wenn `vzlogger` bereits installiert ist, bleibt die bestehende Paketinstallation erhalten und wird durch apt auf die verfügbare aktuelle Version gebracht.

Nach der Installation bleibt der `vzlogger`-Dienst gestoppt und deaktiviert, solange das Auslesen nicht aktiviert ist. vzLogger wird mit **Speichern und anwenden** im vzLogger-Modus gestartet; die MQTT-Bridge kann unabhängig davon deaktiviert bleiben.

### Zählereinrichtung

Ein neu erkannter Lesekopf wird bis zum nächsten **Speichern und anwenden** im Panel als **Neu / ungespeichert** markiert. Führt ein solcher Meter bereits vor dem Anwenden eine OBIS-Suche aus, speichert das Plugin ausschließlich die dabei gewählte Standardprotokoll-Auswahl SML, D0 oder OMS in einer meterbezogenen Pending-Datei zwischen. Nach einem Seiten-Reload kann die Oberfläche dadurch das Protokoll wieder auswählen und die gefundenen OBIS-Kanäle anzeigen. Andere ungespeicherte Meter-Felder und insbesondere OMS-Schlüssel werden nicht als Entwurf persistiert. **Speichern und anwenden** sowie das endgültige Löschen des Meters entfernen diese Pending-Datei.

Aktiviere **Bridge-Service aktiv**, wenn die MQTT-Bridge die vzLogger-MQTT-Werte in den Plugin-HTTP-Cache und optional per UDP weitergeben soll. Der `vzlogger`-Dienst selbst bleibt im vzLogger-Modus unabhaengig von der Bridge startbar. Das **Aktualisierungsintervall** steuert, wie oft vzLogger Zaehlerwerte per MQTT veroeffentlicht; die Bridge verwendet denselben Takt fuer HTTP-Cache-Schreibungen und UDP-Sendungen. Das MQTT-Basis-Topic ist eine uebergreifende Einstellung und bleibt unabhaengig von den Dienstschaltflaechen konfigurierbar.

Schließe einen I/R-Lesekopf an und wähle **Nach I/R Leseköpfen suchen**. Die Suche läuft per AJAX und zeigt währenddessen ein nicht schließbares Overlay. Die Geräteprüfung selbst ist ein kurzer Verzeichniszugriff; antwortet die Anfrage dennoch 15 Sekunden lang nicht, wird sie als Fehler beendet. Nach Abschluss meldet das Overlay, ob keine Geräte, keine neuen Geräte, wirklich neue Leseköpfe oder angeschlossene, nur im Browser zum Löschen vorgemerkte Leseköpfe gefunden wurden. Wirklich neue und vorgemerkte Treffer können im selben Suchlauf auftreten und werden getrennt als `Name: Gerätepfad` aufgelistet. Vorgemerkte Treffer werden mitsamt ihren ungespeicherten Eingaben wieder eingeblendet; neue Lesekopf-Bereiche werden direkt in die bestehende Seite eingefügt. Es erfolgt kein Seiten-Reload. Nur wenn weder neue noch vorgemerkte Treffer gefunden wurden, schließt das Overlay nach einem sichtbaren Drei-Sekunden-Countdown automatisch. Ergebnisse mit neuen oder vorgemerkten Geräten, keine gefundenen Geräte und Fehler bleiben bis **Schließen** sichtbar. Unter dem Suchknopf erscheint für jeden erkannten Lesekopf ein eigener, zunächst eingeklappter Bereich. In dessen Überschrift stehen Name, Gerätepfad und gewähltes Protokoll. Zur Auswahl stehen SML, D0, OMS und **Benutzerdefiniert (JSON)**. Je nach Auswahl zeigt die Oberfläche ausschließlich die von diesem Protokoll unterstützten Meter-Parameter. Beim ersten Speichern werden bestehende SML- und D0-Zählervorgaben automatisch in das neue Schema überführt; ihre bekannten Baudraten und seriellen Werte bleiben erhalten. Ein Lesekopf ohne ausgewähltes Protokoll wird nicht als Meter erzeugt.

SML, D0 und OMS zeigen die OBIS-Suche und einen einheitlichen Channel-Editor für gefundene und manuell ergänzte Kanäle. Die Suche verwendet die aktuellen, noch nicht angewendeten Formulareinstellungen des Meters, darf aber erst gestartet werden, nachdem vzLogger mit **Speichern und anwenden** als aktive Implementierung gespeichert wurde. Neue Identifier werden als aktive Zeile mit `api: null` ergänzt; ein bereits vorhandener vollständiger Identifier erzeugt beim Suchlauf keine weitere Zeile. Manuell darf derselbe Identifier dagegen mehrfach als eigenständiger vzLogger-Channel mit eigener UUID angelegt werden. Die Suche startet als browserunabhängiger Hintergrundauftrag. Ein Warte-Overlay mit Spinner fragt den Status jede Sekunde ab, bleibt nach einem Neuladen der Seite sichtbar und bietet **Suche abbrechen** an. Schließen, Neuladen oder Zurücknavigieren beendet den Auftrag nicht; der Hintergrundprozess speichert die gefundenen Kanäle selbst. Beim kontrollierten Abbruch stellt er den regulären vzLogger-Dienst wieder her. Für die Suche wird dieser Dienst kurz angehalten und ein unabhängig zeitlich begrenzter vzLogger-Testlauf im Vordergrund ausgeführt. Der Suchlauf prüft die Logdatei jede Sekunde und endet vorzeitig, sobald jeder erkannte OBIS-Kanal mindestens zweimal vorgekommen ist; 15 Sekunden bleiben die Sicherheitsobergrenze. Start, Stop und Restart entfernen zusätzlich passende Plugin-Testprozesse. Danach wird der reguläre Dienst wieder gestartet. Schlägt nur diese Wiederherstellung fehl, zeigt die Oberfläche eine Warnung; gefundene Kanäle bleiben erhalten. Nach einer erfolgreichen Suche aktualisiert die Oberfläche den Editor direkt ohne Seiten-Reload. Es werden sowohl vollständige Identifier wie `1-0:1.8.0` als auch kurze D0-Formen wie `1.8.0` akzeptiert. Falls das installierte vzLogger OMS nicht unterstützt, kennzeichnet die Oberfläche den Lesekopf und deaktiviert dessen OBIS-Suche; Prüfen und Anwenden melden dann ebenfalls die fehlende Runtime-Unterstützung.

Für SML, D0 und OMS können außerdem die allgemeinen Meter-Parameter `enabled`, `allowskip` und `aggtime` eingestellt werden. `aggtime` ist nicht SML-spezifisch, sondern für alle Meter-Protokolle zulässig; `-1` deaktiviert die Aggregation. Leere optionale Felder werden nicht in `vzlogger.conf` geschrieben. Insbesondere bleiben SML-Baudrate und -Parity standardmäßig leer, sodass vzLogger seine internen Standardwerte verwendet. Eine ausdrücklich gesetzte Baudrate oder Parity wird dagegen übernommen. Die Standardformulare verwenden immer den lokalen Gerätepfad des erkannten Lesekopfs. Ein SML- oder D0-Meter mit TCP-`host` wird deshalb ausschließlich als **Benutzerdefiniert (JSON)** angelegt.

Nach der Auswahl von SML oder D0 steht **Aus Vorlage initialisieren** zur Verfügung. Das Dropdown zeigt nur zum gewählten Protokoll passende Zählermodelle. Eine SML-Vorlage setzt ausschließlich Baudrate und seriellen Modus. Eine D0-Vorlage setzt die anfängliche Kommunikationsbaudrate, die Lesebaudrate, den seriellen Modus und das Lese-Timeout. Name, Aktivierung, Gerät, Intervalle, Sequenzen, OBIS-Kanäle und alle weiteren Meter-Einstellungen bleiben unverändert. Die übernommenen Werte sind zunächst nur im Browser geändert und müssen mit **Speichern und anwenden** gespeichert werden. Bei Zählermodellen, deren frühere Implementierung zusätzliche Sondersequenzen verwendet, weist die Oberfläche darauf hin, dass nur die verfügbaren Basiswerte übernommen werden.

Der zentrale Zählervorlagenkatalog enthält die Baudraten und Protokolleinstellungen der unterstützten Zähler.

**Benutzerdefiniert (JSON)** ist nur der GUI-Modus. Der Editor enthält genau ein vollständiges vzLogger-Meter-Objekt; dessen echtes `protocol`, beispielsweise `exec` oder `s0`, muss im Objekt stehen. Root-Sektionen wie `meters`, `mqtt` oder `local` sind nicht erlaubt. Die Eingabe wird mit Kommentaren und Formatierung unverändert als `vzlogger_meter_<lesekopf>.jsonc` gespeichert (maximal 64 KiB). Für `vzlogger.conf` werden Kommentare entfernt und gültiges JSON erzeugt. Meter-Defaults werden dabei nicht ergänzt. Nur innerhalb vorhandener `channels` ergänzt das Plugin eine fehlende stabile UUID und ein fehlendes `api` mit `"null"`; die JSONC-Quelldatei bleibt unverändert.

Ist ein benutzerdefiniertes Objekt syntaktisch oder strukturell ungültig, bleibt die Eingabe gespeichert, der betroffene Lesekopf erhält ein rotes Warnsymbol und die konkrete Fehlermeldung erscheint beim Aufklappen. Dieses Meter wird aus der neu erzeugten `vzlogger.conf` und aus `vzlogger_channels.json` ausgelassen, während andere gültige Meter erhalten bleiben. Ein nicht vorhandener absoluter `device`-Pfad wird ebenfalls sichtbar gewarnt, verhindert die Übernahme des Meter-Objekts aber nicht.

Am Ende jedes Lesekopf-Bereichs kann **Meter-Konfiguration entfernen** die Konfiguration zum Löschen vormerken. Der Bereich verschwindet sofort nur in der aktuellen Browseransicht; ein Neuladen oder erneutes Öffnen ohne **Speichern und anwenden** verwirft die Vormerkung vollständig. Erst **Speichern und anwenden** entfernt den Abschnitt aus `smartmeter.json`, die zugehörigen Einträge aus `vzlogger_channels.json` sowie meterbezogene JSONC-, OBIS-, Pending-, Test-, Log- und Runtime-Cachedateien. Dabei wird auch der Channel-Zustand der aktuellen Browseransicht verworfen. Wird das letzte Meter entfernt, ist eine Konfiguration ohne Meter ein gültiger ausgeschalteter Zustand: vzLogger und Bridge werden gestoppt und der SmartMeter-Service-Override wird entfernt. Ein entfernter, weiterhin angeschlossener Lesekopf bleibt bei normalen Seitenaufrufen ausgeblendet. **Nach I/R Leseköpfen suchen** hebt diese Markierung für aktuell erkannte Geräte auf und legt deren Standardeinstellungen ohne frühere OBIS-Kanäle wieder an; Protokoll, Meter- und Kanalauswahl müssen danach erneut konfiguriert und angewendet werden.

Das Plugin erzeugt:

- `vzlogger.conf` im Plugin-Konfigurationsverzeichnis.
- `vzlogger_channel_definitions.json` mit allen aktiven und inaktiven Channel-Definitionen sowie den je API gespeicherten Zielparametern.
- `vzlogger_channels.json` ausschließlich mit aktiven Plugin-Ausgaben und der stabilen Zuordnung von Channel-UUIDs zu SmartMeter-Ausgabeschlüsseln.

Verwende **Speichern und anwenden** für den normalen Ablauf; die Aktion speichert die aktuellen Formularwerte, erzeugt und prüft die Konfiguration und aktiviert sie. **Konfiguration prüfen** übernimmt die aktuellen Formularwerte dagegen nur in einen temporären Entwurf und erzeugt und prüft daraus temporäre Dateien. Dabei werden weder `smartmeter.json` noch `vzlogger.conf`, `vzlogger_channels.json` oder benutzerdefinierte Zählerdateien verändert und es werden keine Dienste gesteuert. Beide Aktionen laufen per AJAX ohne Seiten-Reload; das Overlay zeigt dabei die aktuelle Laufzeit. Erzeugen, Prüfen und Anwenden besitzen gemeinsam ein serverseitiges Zeitlimit von 60 Sekunden. Wird es erreicht, beendet das Plugin den gerade laufenden Unterprozess und zeigt den Fehler im Overlay. Bei **Speichern und anwenden** können Einstellungen oder bereits erfolgreich abgeschlossene Teilschritte zu diesem Zeitpunkt schon übernommen worden sein; der angezeigte Fehler und der Dienststatus müssen deshalb geprüft werden. Das Prüfergebnis bleibt im Overlay stehen, bis es aktiv geschlossen wird. Nach erfolgreichem Anwenden schließt das Overlay nach einem sichtbaren Drei-Sekunden-Countdown; Fehler bleiben zur Bestätigung geöffnet. Die Prüfung kontrolliert Wertebereiche und Datentypen, protokollspezifische SML-/D0-/OMS-Felder, Aggregationsabhängigkeiten, MQTT- und TLS-Kombinationen, API-Pflichtfelder, Geräte- und Zertifikatpfade sowie die UUID-, Identifier- und `chnN`-Zuordnung zwischen Channel-Definitionen, erzeugter vzLogger-Konfiguration und Bridge-Mapping. Bei aktivem vzLogger muss mindestens ein aktives Meter existieren; ein aktives Meter ohne Channels bleibt für die OBIS-Suche zulässig und erzeugt nur eine Warnung. Vorübergehend nicht erreichbare Netzwerkziele werden nicht als Konfigurationsfehler behandelt.

Der Bridge-Service fuer HTTP-Cache und UDP ist optional und bei Neuinstallationen standardmaessig ausgeschaltet.

In der mobilen vzLogger-Ansicht stehen Einstellungsname und Eingabefeld als zusammengehörige Gruppe enger beieinander; Hilfstexte sind grau und durch eine dezente Linie abgesetzt, danach folgt ein größerer Abstand zur nächsten Einstellung. Textfelder, Auswahllisten und Schalter beginnen einheitlich an derselben linken Kante; dies gilt auch innerhalb der Konfigurationsgruppen auf dem Desktop.

Pro Lesekopf verwaltet der Editor jede Channel-Instanz mit Aktivierung, OBIS-Identifier, Herkunft, API und optionaler SmartMeter-Ausgabe. Die Channel-Karten nutzen die gesamte Breite des aufgeklappten Lesekopfbereichs; auf Smartphones bleiben Konfigurationsbereiche, Collapsibles, Tabellen und Eingabefelder innerhalb der verfügbaren Displaybreite. Nur der tatsächlich geöffnete Einstellungsinhalt wird durch einen sehr hellen pastellgelben Hintergrund und einen feinen Rand hervorgehoben. Kurze, dauerhaft sichtbare Hilfstexte stehen direkt unter den allgemeinen und API-spezifischen Eingabefeldern. Beim Ändern eines Feldes bleibt der Offen-/Geschlossen-Zustand der erweiterten Einstellungen je Channel erhalten. Der interne OBIS-Katalog zeigt einen deutschen oder englischen Kurznamen, Langbeschreibung, erwartete Einheit und eine fachliche Kategorie; bei unbekannten oder herstellerspezifischen Codes bleibt der Channel vollständig konfigurierbar und die A–F-Gruppen werden lesbar zerlegt. Ein eigener fachlicher Anzeigename überschreibt nur die Darstellung. Er wird ebenso wenig wie der technische **Ausgabeschlüssel (Cache/UDP)** in `vzlogger.conf` geschrieben, denn vzLogger kennt keinen allgemeinen Channel-Namen. Neue Ausgabeschlüssel werden aus technischen Metadaten des OBIS-Katalogs als `<Klar_Name>_OBIS_<OBIS-Kurzcode>` vorbelegt, beispielsweise `Delivery_Total_OBIS_2.8.0`; ein vorhandener Speicherindex bleibt wie in `Delivery_Total_OBIS_2.8.0*5` sichtbar. Bereits gespeicherte Schlüssel werden nicht umbenannt. Der Schlüssel ist die einzige über HTTP-Cache und UDP veröffentlichte Kennung, kann geändert werden und muss pro Lesekopf unter aktiven Plugin-Ausgaben ohne Beachtung der Groß-/Kleinschreibung eindeutig sein. Zulässig sind 1 bis 64 Buchstaben, Ziffern, Leerzeichen sowie `_ # | ( ) [ ] / ' % $ ! . * -`; `:` und `;` bleiben als Cache-/UDP-Trennzeichen ausgeschlossen. Browser- und Backend-Fehler nennen das geforderte Format vollständig.

Jede Channel-Zeile zeigt den aktuell angewendeten vzLogger-/MQTT-DATA-Index als **Kanal N**. Die Nummer wird aus der erzeugten `vzlogger.conf` gelesen und entspricht damit der Kanalnummer auf der Live-Daten-Seite; nicht angewendete oder inaktive Definitionen erscheinen als **Kanal –**. Im Kopf der erweiterten Einstellungen steht zusätzlich die persistente UUID in Grau. Nach erfolgreichem **Speichern und anwenden** aktualisiert die Seite die angewendeten Nummern ohne Neuladen.

Manuell angelegte Channel-Definitionen besitzen am Ende der erweiterten Einstellungen die Aktion **OBIS-Kanal entfernen**. Nach einer Bestätigung mit Kanalnummer, OBIS-Identifier und UUID wird die Karte nur im aktuellen Browserentwurf ausgeblendet. Ein Neuladen vor **Speichern und anwenden** verwirft die Vormerkung. Erst das Anwenden entfernt die Definition dauerhaft und erzeugt `vzlogger.conf` sowie `vzlogger_channels.json` ohne diesen Kanal neu. Gefundene Kanäle werden stattdessen über **Aktiv** deaktiviert, da sie bei einem späteren Suchlauf erneut erkannt werden können.

SML und D0 unterstützen einen optionalen Speicher-/Abrechnungsindex `*F`. Werte von 0 bis 254 wählen einen Wert, den der Zähler tatsächlich mit diesem vollständigen Identifier liefert; sie starten keine historische Abfrage und lesen kein Lastprofil. Den standardisierten unbenutzten Wert 255 stellt der Editor als **Nicht angegeben (255)** dar. Bestehende leere Werte, `null` und `*255` werden in diesen Zustand überführt und nicht als unnötiger `*255`-Suffix ausgegeben. Bei OMS ist das Feld deaktiviert und wird auch backendseitig ignoriert. **Aggregation** (`none`, `avg`, `max`, `sum`) ist eine zeitliche vzLogger-Verarbeitungseinstellung und keine Wertart. Sie ist nur bei meterweitem `aggtime > 0` aktiv. Neue bekannte Kanäle erhalten dann die Katalogempfehlung, bestehende Werte werden nicht überschrieben.

Die APIs schalten ausschließlich ihre eigenen Parameter frei. `null` besitzt keine Zielparameter. Volkszähler benötigt `middleware`; InfluxDB benötigt `host` und bietet Version-/Datenbank- beziehungsweise Bucket-, Organisations-, Messreihen-, Tag-, Authentifizierungs-, Timeout-, Batch/Puffer-, UUID- und TLS-Werte; MySmartGrid benötigt `middleware`, `secretKey`, `device` und `type` und kennzeichnet `name` ausdrücklich als MySmartGrid-Registrierungsname. `duplicates` gilt nur für Volkszähler und InfluxDB. Werte anderer APIs bleiben gespeichert, werden aber weder validiert noch in `vzlogger.conf` erzeugt. Im benutzerdefinierten JSON-Modus bleiben Channels Bestandteil des eingegebenen Meter-Objekts; deshalb wird dort kein separater Editor angezeigt.

### Anwenden

Mit **Speichern und anwenden** wird die Konfiguration erzeugt und geprüft. Das Plugin richtet fuer den `vzlogger`-Dienst einen systemd-Drop-in ein, der vzLogger direkt mit `/opt/loxberry/config/plugins/smartmeter-ng/vzlogger.conf` startet. Danach wird der Dienst fuer den Start nach einem LoxBerry-Neustart aktiviert und neu gestartet. Wenn **Bridge-Service aktiv** eingeschaltet ist, wird zusätzlich die MQTT-Bridge als systemd-Service installiert und gestartet; andernfalls wird nur die Bridge gestoppt.

Die erzeugte `vzlogger.conf` ordnet Sektionen und Parameter entsprechend der vzLogger-Dokumentation an. Die Root-Parameter beginnen mit `retry`, `verbosity` und `log`; anschließend folgen `local`, `mqtt` und `meters` mit jeweils fester Parameterreihenfolge.



### Expert Mode

Der Schalter **Expert Mode** rechts neben der Überschrift der vzLogger-Konfiguration wird sofort per AJAX gespeichert; die Seite wird dabei nicht neu geladen und geöffnete Bereiche bleiben erhalten. Beim ersten Einschalten muss bereits eine `vzlogger.conf` vorhanden sein. Nur wenn noch kein Expert-Entwurf existiert, wird sie einmalig als `vzlogger_expert.conf` übernommen. Ein vorhandener Expert-Entwurf wird bei späterem Aus- und Einschalten weder ersetzt noch automatisch als Laufzeitkonfiguration aktiviert. Solange der Expert Mode aktiv ist, sind alle Bedienelemente innerhalb der **vzLogger-Konfiguration** schreibgeschützt und **Speichern und anwenden** erzeugt die Datei niemals aus diesen Feldern neu. Aktivierung, Debug-Log und Log-Level des vzLogger-Dienstes sowie alle Einstellungen der SmartMeter-Bridge bleiben editierbar.

**vzLogger-Konfiguration bearbeiten** öffnet das vollständige, unmaskierte JSON in einem authentifizierten Browser-Tab. **Abbrechen** verwirft die Änderungen im Browser. **Speichern & Schließen** speichert den Expert-Entwurf immer und validiert ihn. Ein gültiger Entwurf wird ohne automatischen Dienstneustart zur laufzeitrelevanten `vzlogger.conf`; ein ungültiger Entwurf bleibt zur Korrektur erhalten, während die letzte gültige Laufzeitdatei unverändert bleibt. Ist ein reaktivierter Expert-Entwurf noch nicht identisch mit der aktiven `vzlogger.conf`, bleiben Start und Restart gesperrt, bis er über **Speichern & Schließen** oder **Speichern und anwenden** übernommen wurde. Bei einem ungültigen Entwurf bleibt zusätzlich Anwenden gesperrt; Stop bleibt immer möglich. Unbekannte vzLogger-Erweiterungen werden als Warnung gemeldet und nicht entfernt. Vorhandene SmartMeter-Ausgaben bleiben über identische Kanal-UUIDs zugeordnet; neue UUIDs werden gemeldet, aber nicht automatisch von der Bridge veröffentlicht.

Die Bridge liest MQTT-Verbindung und Topic aus der gültigen, übernommenen Expert-Konfiguration. Aktivierung, Debug, Aktualisierungsintervall, Cache und UDP stammen weiterhin aus der normalen UI. Das Ausschalten des Expert Mode verändert weder `vzlogger.conf` noch `vzlogger_expert.conf`. Das anschließend bestätigte **Speichern und anwenden** im Standardmodus erzeugt nur `vzlogger.conf` aus den erhaltenen Standardwerten neu; der Expert-Entwurf bleibt als inaktiver Arbeitsstand erhalten. Beim erneuten Einschalten wird dieser Entwurf wieder angezeigt, aber erst durch Speichern oder Anwenden erneut zur Laufzeitkonfiguration. **Aus aktueller vzlogger.conf neu initialisieren** ist die einzige automatische Übernahme in Gegenrichtung: Nach einer Sicherheitsabfrage überschreibt sie den gespeicherten Expert-Entwurf bewusst mit der aktuell aktiven `vzlogger.conf`.

### Dienststeuerung

Die vzLogger-Seite zeigt oben im Bereich **Betrieb** zwei getrennte Dienst-Panels. Das erste Panel steuert den eigentlichen `vzlogger`-Dienst und enthält Status, Start/Stop/Restart, Log, Debug-Log, Log-Level und Live-Daten. Start, Stop und Restart besitzen jeweils einen eigenen Tooltip; beim automatischen Wechsel zwischen Start und Stop wechselt damit auch der angezeigte Hinweis. Die Aktionshinweise für diese Dienstschalter, die Lesekopf-Suche, die OBIS-Suche und **Generierte Konfiguration anzeigen** stehen zusätzlich in der rechten Hilfsspalte. **Generierte Konfiguration anzeigen** steht unten direkt vor dem Pfad zur erzeugten Konfiguration und öffnet `/opt/loxberry/config/plugins/smartmeter-ng/vzlogger.conf` schreibgeschützt und mit Zeilennummern in einem neuen Browser-Tab; `pass` und `keypass` werden dabei maskiert. Das zweite Panel steuert die **SmartMeter-Bridge**, einen Plugin-Zusatzdienst für HTTP-Cache und UDP; ihre Loganzeige öffnet das aktuelle Bridge-Log. Die Bridge-Einstellungen können im Formular vorbereitet werden; Start und Restart werden jedoch erst nach erfolgreichem **Speichern und anwenden** der vzLogger- und Bridge-Aktivierung freigegeben. Alle Bridge-Einstellungen einschließlich HTTP-Cache-Status werden erst bei aktiver Bridge freigegeben; der UDP-Port benötigt zusätzlich **UDP senden**. Stop bleibt für einen bereits laufenden Dienst verfügbar. Der Offen-/Geschlossen-Zustand aller aufklappbaren Bereiche wird lokal im Browser gespeichert und nach einem manuellen Reload wiederhergestellt.

Die Dienstzustaende werden im sichtbaren Browser-Tab alle drei Sekunden aktualisiert. Waehrend Start/Stop/Restart pausiert dieses Polling; ein Overlay benennt die laufende Aktion, und ihre AJAX-Antwort aktualisiert den echten Dienststatus direkt nach Abschluss. Bei Erfolg schliesst das Overlay automatisch. Dauert die Aktion laenger als 15 Sekunden, weist das Overlay darauf hin. **Ausblenden** schliesst nur das Overlay, waehrend der bereits gestartete Systemvorgang im Hintergrund weiterlaeuft; ein Fehler oeffnet das Overlay wieder und kann mit **Schliessen** bestaetigt werden. Start/Stop/Restart laufen ohne Seiten-Reload. Start/Restart werden erst freigegeben, wenn die zugehoerige Aktivierung erfolgreich mit **Speichern und anwenden** gespeichert wurde und eine gueltige erzeugte Konfiguration vorhanden ist; fuer die Bridge muss MQTT zusaetzlich gespeichert und in der erzeugten `vzlogger.conf` aktiv sein. Die Dienstschalter führen selbst keinen Implementierungswechsel durch. Beim vzLogger werden außerdem Debug-Log und Log-Level dauerhaft gespeichert und in der vorhandenen `vzlogger.conf` aktualisiert, die Bridge hat keinen eigenen Debug-Schalter mehr; ihre Ausführlichkeit steuert der zentrale Log-Level. Andere noch nicht gespeicherte Eingaben bleiben im Browser erhalten und werden erst mit **Speichern und anwenden** uebernommen. Stop bleibt bei einem laufenden Dienst unabhaengig von Aktiv-Schaltern und Konfigurationsfehlern verfuegbar. Start/Restart pruefen die vorhandene Konfiguration, erzeugen sie aber nicht neu; fehlt sie oder ist sie ungueltig, muss zuerst **Speichern und anwenden** ausgefuehrt werden. **Live-Daten (JSON) öffnen** ruft den integrierten vzLogger-HTTP-Dienst auf; `/` liefert wegen der aktivierten Indexfunktion alle konfigurierten Kanäle, `/<UUID>` einen einzelnen Kanal.

Unterhalb der Dienststeuerung sind die Einstellungen optisch in **vzLogger-Konfiguration** und **SmartMeter-Bridge-Konfiguration** getrennt und jeweils kurz beschrieben. Zaehler und I/R-Lesekoepfe gehoeren zur vzLogger-Konfiguration. Aktualisierungsintervall, HTTP-Cache und UDP-Ausgabe gehoeren zur Bridge-Konfiguration. Deaktivierte Bereiche grauen Eingabefelder, Beschriftungen und Hilfetexte gemeinsam aus, ohne ihre Werte zu veraendern. Bei einem inaktiven SML-, D0- oder OMS-Zaehler bleiben nur Beschreibung und **Meter aktiv** bearbeitbar. Der UDP-Port folgt dem noch nicht gespeicherten Schalter **UDP senden** sofort und wird nur bei aktiver Bridge und eingeschalteter UDP-Ausgabe bearbeitbar.

Zähler, Leseköpfe, Protokolle und OBIS-Kanäle gehören ausschließlich zur vzLogger-Konfiguration. vzLogger liest die Geräte und veröffentlicht die Messwerte über MQTT. Die SmartMeter-Bridge abonniert diese MQTT-Nachrichten und verwendet zusätzlich `vzlogger_channels.json`, um UUID beziehungsweise `chnX` auf Lesekopf, OBIS-Identifier und Ausgabename abzubilden. Die Bridge greift nicht direkt auf Zähler oder serielle Geräte zu. Aktualisierungsintervall, HTTP-Cache und UDP befinden sich deshalb in einem separaten, standardmäßig eingeklappten Bereich **SmartMeter-Bridge – Einstellungen**.

Unter **Erweiterte vzLogger-Diensteinstellungen** befindet sich die selten benoetigte Wiederholungswartezeit (`retry`). Der Bereich ist standardmaessig eingeklappt. `retry` legt die Wartezeit in Sekunden nach einer fehlgeschlagenen Anfrage fest und wird bei jeder Neuerzeugung der `vzlogger.conf` uebernommen. Debug-Log und Log-Level (`verbosity`) stehen direkt in der sichtbaren vzLogger-Dienstzeile.

Der ebenfalls eingeklappte Bereich **vzLogger HTTP-Dienst (local)** enthält alle Einstellungen des integrierten vzLogger-HTTP-Dienstes: `enabled`, `port`, `index`, `timeout` und `buffer`. Die Plugin-Standardwerte sind `true`, `18080`, `true`, `30` und `-1`. Beim Ringspeicher geben positive Werte die Anzahl Sekunden und negative Werte die Anzahl Datensätze je Kanal an. Alle Werte werden beim Neuerzeugen der `vzlogger.conf` übernommen.

Im eingeklappten Bereich **MQTT** sind die Einstellungen in **Verbindung und Veröffentlichung**, **Authentifizierung – Benutzer/Passwort** und **Authentifizierung – Zertifikat** gegliedert. Broker, Port und Benutzer zeigen den tatsächlich verwendeten Wert: Ein Plugin-Override hat Vorrang, danach folgt die LoxBerry-MQTT-Systemeinstellung und für Broker/Port zuletzt `127.0.0.1:1883`. Unveränderte Systemwerte werden beim Speichern nicht als Plugin-Override dupliziert; ein geleertes Feld schaltet wieder auf LoxBerry-Vererbung. Passwortfelder bleiben leer und maskiert und zeigen lediglich an, ob ein eigenes oder das LoxBerry-Passwort verwendet wird. Die erzeugte `vzlogger.conf` enthält die für vzLogger erforderlichen effektiven Zugangsdaten, lässt aber leere Client-ID-, Benutzer-, Passwort- und Zertifikatsparameter aus. Gespeicherte Passwörter werden weder in das GUI-HTML noch unmaskiert in Diagnoseausgaben geschrieben. Generator, interne MQTT-Bridge und Diagnose-Capture verwenden dieselben Verbindungseinstellungen. Da `mosquitto_sub` in der internen Bridge kein Schlüsselpasswort über die Kommandozeile übernimmt, muss der dort verwendete private Schlüssel ohne interaktive Rückfrage lesbar sein.

Neben den rohen JSON-Daten gibt es eine gerenderte Webseite, die sich alle zwei Sekunden aktualisiert. Sie gruppiert die Werte nach I/R-Lesekopf und Kanal und zeigt Kanalnummer, eigenen fachlichen Anzeigenamen beziehungsweise ersatzweise den deutschen OBIS-Katalog-Kurznamen, OBIS-Identifier, UUID sowie den rohen Timestamp mit lesbarer lokaler Zeit. Messwerte werden mit der Katalogeinheit dargestellt; elektrische SML-Zählerstände werden dabei vom vzLogger-Rohwert in Wh nach kWh umgerechnet, der Rohwert bleibt als Tooltip sichtbar. Die Kanal-Metadaten stammen aus `vzlogger_channels.json` und werden im Browser nur neu geladen, wenn sich das erzeugte Mapping ändert.

Unter den Tabellen zeichnet die Live-Seite die seit dem Öffnen empfangenen Werte in einem gemeinsamen Chart. Beim ersten Aufruf sind die vorzeichenbehaftete Gesamtwirkleistung beziehungsweise ersatzweise Bezugs- und Lieferleistung sowie die Gesamtzähler für Netzbezug und Netzeinspeisung ausgewählt. Bezug wird positiv und Einspeisung negativ dargestellt; kumulative Bezugs- und Lieferenergie bleiben positive Größen. Energie wird standardmäßig als Änderung seit dem Öffnen angezeigt, kann aber auf absolute Zählerstände umgeschaltet werden. Eine kompakte Übersicht zeigt pro Lesekopf Netzbezug, Netzeinspeisung, Netzbilanz, aktuellen Netzfluss sowie die höchsten beobachteten Bezugs- und Einspeiseleistungen. Diese Werte beschreiben ausschließlich den Austausch mit dem Netz und nicht Erzeugung, Hausverbrauch, Eigenverbrauch oder Autarkie.

Kanäle derselben Einheit teilen eine Achse; höchstens zwei Einheitengruppen können gleichzeitig ausgewählt werden. Farbe, Strichmuster und halbtransparente Linien unterscheiden Kurven. Beim Zeigen auf eine Kurve wird sie hervorgehoben und die übrigen werden abgeblendet; Tooltips nennen alle Werte am gewählten Zeitpunkt. Messlücken werden nicht mit Nullwerten aufgefüllt oder mit einer durchgehenden Linie verdeckt. Ein sinkender kumulativer Zählerstand erzeugt eine neue, gekennzeichnete Basis.

Verlauf und Sitzungskennzahlen existieren nur im Arbeitsspeicher des Tabs und beginnen nach Reload oder erneutem Öffnen von vorn. Die Kanalauswahl, der Energiemodus und die Option zur Hintergrund-Erfassung werden dagegen lokal im Browser gespeichert; entfernte Kanal-UUIDs werden beim nächsten Öffnen aus dieser Auswahl entfernt. Standardmäßig pausieren die Datenabfragen bei einem verborgenen Tab. **Datenerfassung im Hintergrund versuchen** lässt die Abfragen ohne sichtbares Neuzeichnen bestmöglich weiterlaufen, kann aber von Browser oder Betriebssystem gedrosselt beziehungsweise angehalten werden und benötigt besonders auf Mobilgeräten zusätzliche Leistung und Akkukapazität. Die Seite verwendet die mit dem Plugin lokal ausgelieferte Chart.js-Version und lädt keine Bibliothek, Schrift oder Telemetrie von einem Drittanbieter.

Wenn der Zaehler keinen Momentanleistungswert liefert, berechnet die MQTT-Bridge zusaetzlich `Consumption_CalculatedPower_OBIS_1.99.0` aus `1.8.0` und `Delivery_CalculatedPower_OBIS_2.99.0` aus `2.8.0`, sobald zwei unterschiedliche Zaehlerstaende vorliegen. Die Einheit folgt der Einheit des vom Zaehler gelieferten Zaehlerstands pro Stunde.

Das Bridge-Log liegt unter `/opt/loxberry/log/plugins/smartmeter-ng/vzlogger_mqtt_bridge.log` und wird bei 2 MB rotiert. Das Control-Log liegt unter `/opt/loxberry/log/plugins/smartmeter-ng/vzlogger_control.log`, wird bei 512 KB rotiert und kann über **Control-Log anzeigen** direkt unter den beiden Dienstbereichen geöffnet werden. Erfolgreiche Start-, Stop- und Restart-Aktionen werden kurz grün bestätigt; Warnungen und Fehler bleiben mit ihren Details im Aktionsfenster geöffnet. Apply- und Diagnose-Logs werden ebenfalls im Plugin-Logverzeichnis abgelegt; von `vzlogger_debug_*.log` bleiben die letzten fuenf Dateien erhalten. Das separate vzLogger-Debug-Log `/opt/loxberry/log/plugins/smartmeter-ng/vzlogger.log` wird nur bei aktivierter vzLogger-Debugoption geschrieben. Im Normalbetrieb schreibt vzLogger kein Dateilog.

Der Service heißt:

```text
smartmeter-ng-vzlogger-bridge
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

Die Bridge sammelt erkannte vzLogger-Nachrichten im Arbeitsspeicher und schreibt sie im Aktualisierungsintervall als `.data`-Cachedateien:

```text
/var/run/shm/<Plugin-Ordner>/
```

Der bestehende HTTP-Endpunkt liefert weiterhin Werte aus diesen Cachedateien. Die vzLogger-Seite zeigt im Bereich **HTTP-Cache** den Cache-Status, die letzte Aktualisierung und einen direkten Link zum Cache-Endpunkt. Die Ausgabe beginnt immer mit `Last_Update` und `Last_UpdateLoxEpoche`. Danach folgt pro konfiguriertem Kanal ausschließlich dessen Ausgabeschlüssel, aufsteigend nach Kanalnummer (`chn0`, `chn1`, ...). Zusatzwerte ohne Kanalnummer folgen alphabetisch. Damit bleibt die Reihenfolge auch bei mehrfach identischen OBIS-Identifiern eindeutig. Wenn UDP aktiviert ist, sendet die Bridge die gecachten Werte im selben Aktualisierungsintervall und in derselben Reihenfolge an alle konfigurierten Miniservers.

## Logging und Log-Level

Das Plugin nutzt das LoxBerry-Logging. Die Logs von Control-Aktionen, der MQTT-Bridge und der Weboberfläche erscheinen in der zentralen LoxBerry-Loganzeige und werden von `log_maint.pl` automatisch aufgeräumt. Bei jedem Dienststart und jeder Aktion wird eine neue, mit Zeitstempel benannte Logdatei angelegt.

Wie ausführlich das Plugin protokolliert, steuert der **Log-Level** im LoxBerry-Plugin-Verwaltungs-Widget (Menü „Plugins" → dieses Plugin). Auf Stufe **7 (Debug)** protokolliert die MQTT-Bridge zusätzlich rohe MQTT-Topics, Payloads, UUID-Zuordnungen, erkannte Cache-Namen und ignorierte Nachrichten. Ein eigener Debug-Schalter für die Bridge ist dadurch entfallen.

Die getrennte Debug-Option beim vzLogger-Dienst steuert die Ausführlichkeit des externen `vzlogger`-Programms selbst und ist davon unabhängig.

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

### Logdateien

Das Plugin schreibt Laufzeitlogs in das LoxBerry-Plugin-Logverzeichnis und nach `/var/run/shm/<Plugin-Ordner>/`.
