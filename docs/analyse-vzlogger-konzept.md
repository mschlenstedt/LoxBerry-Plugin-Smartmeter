# Analyse: vzLogger-Konfigurationskonzept (Stand vor dem Tab-Umbau)

Diese Analyse beschreibt, wie die Erzeugung der `vzlogger.conf` und die
zugehörige Konfiguration aktuell umgesetzt sind. Das **Backend (Generator,
Validator, Orchestrator, Kanalmodell) bleibt unverändert**; nur das UI wird von
der alten Single-Page-`settings.html` in das neue Tab-Konzept überführt.

Erstellt am 2026-07-26 als Grundlage für den Neubau des vzLogger-Tabs.

---

## 1. Datenmodell — drei Schichten

### a) `smartmeter.json` (via `bin/SmartMeterConfig.pm`, API `param("SECTION.KEY")`)

- `MAIN.IMPLEMENTATION` = `none | vzlogger` — Master-Schalter (liest überhaupt
  jemand aus?). Alt-Werte wie `legacy` werden als `none` behandelt
  (`implementation_mode()` in `SmartMeterVZLoggerConfig.pm`).
- `MAIN.MQTTTOPIC` — Basis-Topic für MQTT.
- `VZLOGGER.*` — Dienst-/Global-Einstellungen:
  - Local-httpd: `LOCALENABLED`, `LOCALPORT` (18080), `LOCALINDEX`,
    `LOCALTIMEOUT`, `LOCALBUFFER`
  - MQTT: `MQTTENABLED`, `MQTTHOST`, `MQTTPORT`, `MQTTKEEPALIVE`, `MQTTID`,
    `MQTTRETAIN`, `MQTTRAWANDAGG`, `MQTTQOS`, `MQTTTIMESTAMP`,
    `MQTTUSER`/`MQTTPASS`, Cert-Auth (`MQTTCAFILE`, `MQTTCERTFILE`, …)
  - Sonstiges: `RETRY`, `LOGLEVEL`, `VZLOGGERDEBUG`, `EXPERTMODE`
- `METERS` — pro Zähler ein Abschnitt mit: `SERIAL`, `METER` (Typ/Modus),
  `PROTOCOL` (`sml | d0 | oms`), `DEVICE`, `ENABLED`, `ALLOWSKIP`, `AGGTIME`,
  `INTERVAL`, `BAUDRATE`, `PARITY…`, `OBISCHANNELS`, protokollspezifische Extras
  (`PULLSEQ`, `ACKSEQ`, `OMSKEY`, `WAITSYNC`, …).

### b) `vzlogger_channel_definitions.json` (via `bin/SmartMeterVZLoggerChannels.pm`)

Das eigentliche **Kanal-Dokument pro Zähler**: welche OBIS-Kanäle vorhanden sind,
`enabled`-Flag, `plugin_output` (Ausgabe-Key), stabile `uuid`, Anzeigename.
- Alt-Konfigurationen werden **einmalig** per `migrate_legacy_meter()` aus den
  `METERS`-Feldern hierher migriert.
- Custom-/User-Kanäle: `bin/SmartMeterVZLoggerCustomChannels.pm` vergibt stabile
  UUIDs und legt sie in Registry-Dateien pro Serial ab
  (`vzlogger_user_channel_uuids_<serial>.json`).

### c) Referenzdaten (Template-Verzeichnis, read-only)

- `templates/obis_catalog.json` — OBIS-Nachschlagewerk (Name de/en, Einheit,
  Kategorie). Dient der Anzeige/Live-Metadaten.
- `templates/meter_templates.json` — vordefinierte Zähler-Vorlagen für das
  Dropdown „Meter Template".

---

## 2. Erzeugung der `vzlogger.conf` — `bin/vzlogger_config.pl` (~675 Zeilen)

Der Kern der Umsetzung. Eingaben: `smartmeter.json` (flach importiert) +
Kanaldefinitionen + OBIS-Katalog + MQTT-Settings.

Ablauf:
1. Iteriert alle Meter-Abschnitte (Keys mit `.SERIAL`), bestimmt den Modus über
   `normalized_meter_mode()` (`sml/d0/oms/user`, `0` = aus → übersprungen).
2. **Standard-Zähler:** `standard_meter_config()` baut den protokollspezifischen
   Meter-Block (setzt optionale Felder je nach `sml`/`d0`/`oms`). Kanaldefinition
   wird geladen bzw. migriert; jeder aktive Kanal wird über `native_channel()` zu
   einem vzLogger-Kanal mit `mqtt_topic = <serial>/<output-key>`.
3. **User-Zähler:** `read_user_meter_json()` + `assign_custom_channel_uuids()` +
   `enrich_user_channels()`.
4. Parallel entsteht ein **`channel_mapping`** (uuid → Live-Metadaten:
   Katalogname de/en, Einheit, Kategorie, `display_factor`, Kanal-Index) für die
   Live-Ansicht.
5. Zusammenbau des Config-Objekts: `retry`, `verbosity`/`log`,
   `local {enabled,port,index,timeout,buffer}`, `mqtt {…}`, `meters[]`.

**Ausgaben** (ins Config-Verzeichnis `config/plugins/<folder>/`):
- `vzlogger.conf` — die echte vzLogger-Konfiguration (JSON), via
  `write_ordered_vzlogger_json()`.
- `vzlogger_channels.json` — das uuid→Metadaten-Mapping (nutzt der **Live-Tab**).
- `vzlogger_channel_definitions.json` — Kanaldokument (nur bei Änderung).

Env-Flag `SMARTMETER_VALIDATION_DRAFT=1` → **Trockenlauf**, schreibt keine
Dateien (für Validierung/Vorschau).

---

## 3. Validierung & Orchestrierung — `bin/vzlogger_control.pl` (~789 Zeilen)

Kommando-Dispatcher (`$action = shift @ARGV`). Aktionen:

```
generate | validate | apply | apply-expert | activate-vzlogger |
start-vzlogger | stop-vzlogger | restart-vzlogger | disable-vzlogger |
status | debug-log
```

Zentraler Ablauf **`apply`** = `generate_validate_and_promote()`:
1. `vzlogger_config.pl` erzeugt die Dateien (in einem Stage-Verzeichnis).
2. `vzlogger_validate.pl` (~515 Zeilen) prüft die erzeugte Konfiguration.
3. Atomares Promoten der Stage-Dateien + `chown loxberry`, danach Dienst
   (neu-)starten. Bei **0 konfigurierten Metern** → Dienst stoppen.

Serialisiert über ein Config-Lock (`acquire_config_lock()` in
`/var/run/shm/<folder>`, `SmartMeterVZLoggerRuntime.pm`), damit sich parallele
Konfigurations- oder Dienstaktionen nicht überholen.

Der Dienst selbst läuft im Foreground als `loxberry` über `bin/watchdog.pl`
(kein systemd) — siehe separate Watchdog-Umsetzung.

---

## 4. Expertenmodus & `webfrontend/htmlauth/vzlogger_config.cgi` (~134 Zeilen)

Gesteuert über `VZLOGGER.EXPERTMODE`:
- **Normal (read-only):** zeigt die generierte `vzlogger.conf`, Secrets
  (`pass`/`token`/`secretKey`) geschwärzt, zeilenweise als `<li><code>` gerendert
  (`templates/vzlogger_config_readonly.html`).
- **Experte:** editierbares Textfeld für die rohe `vzlogger.conf`
  (`templates/vzlogger_config_editor.html`). POST → `validate_expert_text()` →
  atomares Promoten + neu gebautes Mapping (`build_expert_mapping()`), Ergebnis
  via `templates/vzlogger_config_result.html`. Zuständiges Modul:
  `bin/SmartMeterVZLoggerExpert.pm`.

Der raw-Text-Editor ist größenbegrenzt (1 MiB) und normalisiert CRLF→LF.

---

## 5. Das alte UI-Konzept — `templates/settings.html` (~2063 Zeilen, jQuery Mobile)

**Eine einzige Seite** mit `data-role="collapsible"`-Panels, die *alles*
bündelte:

- vzLogger-Dienst (Start/Stop/Status) **+ Paket-Sektion** (Install/Version)
  → wandert in den **Upgrade-Tab**
- „vzLogger Configuration"-Überschrift mit **Expert-Mode-Flipswitch**
- **Advanced service settings** (retry, loglevel, debug)
- **Local settings** (httpd: enabled/port/index/timeout/buffer)
- **MQTT settings** (Connection / User-Auth / Cert-Auth)
- **Meters** — pro Zähler: Meter-Template-Dropdown (`meter_templates.json`),
  Protokoll, **Device**, OBIS-Kanäle (mit OBIS-Discovery/Suche, Output-Keys)
- „Show generated config" / Expert-Edit / Reset expert config
- **Save & Apply**-Button → `run_configuration_action('apply')` →
  `vzlogger_control.pl apply`

Daten wurden **serverseitig ins Template gerendert** (`TMPL_VAR VZLOGGER_MQTTHOST`
usw.) und als großes Formular zurückgepostet; versteckte Textareas
(`channel_definitions_json`, `channel_indices_json`) trugen den Kanal-JSON-State.

---

## 6. Konsequenzen für den Tab-Umbau

Bereits abgezweigt in andere Tabs:
- **Paket/Install/Version** → Upgrade-Tab
- **Live-Ansicht** (nutzt `vzlogger_channels.json`) → Live-Daten-Tab
- **Logs** → Logfiles-Tab
- **Device-Auswahl** → I/R-Leseköpfe-Tab (liefert künftig das Device-Dropdown)

Übrig für den **vzLogger-Tab**:
1. Global-Settings: Dienst an/aus (`MAIN.IMPLEMENTATION`), Advanced, Local, MQTT
2. Meter-/Kanal-Konfiguration (der aufwändigste Teil)
3. Expertenmodus (raw-Edit + „Show generated config")
4. Save & Apply (→ `vzlogger_control.pl apply`)

Festzulegen beim Neubau:
- **Kein serverseitiges Einbetten** mehr (`TMPL_VAR`-Datenparameter). Neues
  Muster: `ajax.cgi` + `javascript.js`, relative URLs — wie beim IR-Köpfe-Tab.
  Der Meter-/Kanal-Teil ist der Hauptkandidat dafür.
- **Device eines Zählers** kommt aus dem IR-Köpfe-Dropdown (die vorbereitete
  Kopplung: automatisch erkannte + manuell hinzugefügte Köpfe).
- Struktur des Tabs: eine Seite mit DS-Collapsibles (Global / Meter / Experte)
  vs. Meter-Konfiguration als eigenständiger Unterbereich — noch zu entscheiden.
