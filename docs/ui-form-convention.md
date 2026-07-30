# UI-Konvention: Formularaufbau & Service-Status-Block

Grundsatzentscheidungen für alle Tabs (angelehnt an das Gateway-Tab von
LoxBerry-Plugin-Audioserver4Home, umgesetzt im LoxBerry Design System).

## 1. Formularzeile

Aufbau: **Label links, Eingabefeld rechts, kurzer Hilfetext darunter** (in der
Feldspalte). Direkt rechts neben dem Label steht ein kleiner grauer
**„?"-Button** (`.sm-help`), der in die passende Stelle im Volkszähler-Wiki
verweist (neuer Tab).

Markup-Muster (statisch im Template; Werte kommen per Ajax/JS):

```html
<div class="lb-form-row">
	<label class="lb-form-label" for="FIELD_ID">
		<TMPL_VAR VZLOGGER.SOME_LABEL>
		<a class="sm-help" href="https://wiki.volkszaehler.org/…#anker" target="_blank" rel="noopener" title="Hilfe">?</a>
	</label>
	<div class="lb-form-field">
		<input class="lb-input" type="text" id="FIELD_ID">
	</div>
	<div class="lb-form-help"><TMPL_VAR VZLOGGER.SOME_LABEL_HELP></div>
</div>
```

- `lb-form-row` / `lb-form-label` / `lb-form-field` / `lb-form-help` sind
  DS-Klassen. `lb-form-help` sitzt automatisch in der Feldspalte.
- `.sm-help` wird von `templates/javascript.js` per injiziertem `<style>`
  definiert (grauer Kreis mit „?"). Das ist das Pendant zum kleinen Icon-Button
  im I/R-Köpfe-Tab, hier grau und als Wiki-Link. `.lb-form-label` ist auf
  `white-space:nowrap` gesetzt, damit der „?"-Button nie in eine zweite Zeile
  umbricht (Labels kurz halten).
- **Wiki-Anchor immer setzen:** die vzLogger-Parameterseite hat die Anker
  `#root`, `#local`, `#mqtt`, `#meters` (unter `#meters` weitere). Auf den
  passenden Abschnitt verlinken, nicht nur auf die Seite.
- Für Dropdowns `lb-select`, für Textareas `lb-textarea` verwenden. Enum-Werte
  und Defaults stammen aus `docs/analyse-vzlogger-config-format.md`.

## 2. vzLogger-Service-Status-Block

Wird oben auf **jedem Tab außer Live-Daten und Logdateien** angezeigt. Er
reproduziert **exakt** den Gateway-Service-Block aus Audioserver4Home: zentriert
Label + Status-Icon (Original-Bilder `check_20/error_20/unknown_20.png`) + eine
Status-Box, die auf Grün (`#6dac20`, „PID: n") bzw. Orange (`#FF6339`,
„gestoppt") umschaltet, daneben zwei graue Icon-Buttons **(Neu-)Starten** und
**Stoppen**, darunter `<hr>`. Nachbau per eigenem CSS (`.vzsvc*`), weil wir das
LoxBerry DS (nojqm) statt jQuery Mobile nutzen.

Einbindung: im Template genügt der Mountpunkt

```html
<div id="vz-service"></div>
```

`templates/javascript.js` rendert den Block hinein, pollt alle 5 s
`ajax.cgi?action=vz-status` und schaltet die Buttons auf `vz-restart` /
`vz-stop`. Diese Ajax-Aktionen rufen `bin/watchdog.pl` auf
(`--action=pid|restart|stop`). Die `pid`-Aktion ist bewusst ungeloggt/lockfrei,
weil sie im Polling-Takt läuft.

Lokalisierte Strings: `COMMON.SERVICE_*`.
