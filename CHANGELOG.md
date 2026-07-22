# Changelog

All notable user-visible changes should be documented in this file. Use the latest entry as the source for GitHub Release notes.

## Unreleased

- Keep the existing mutually exclusive Legacy/vzLogger/none activation behavior while centralizing Legacy migration and cron handling, disable all Legacy actions and settings below its inactive activation switch, enable manual Legacy reads only after Legacy is saved active and the vzLogger service has stopped, preserve both implementations' saved configuration, reject concurrent Legacy/vzLogger reader access, make Legacy cache cleanup POST-only and protect runtime lock/job files, normalize Expert bridge UUIDs case-insensitively, and remove duplicated or unused runtime helpers and the obsolete String::Escape dependency.
- Regenerate the standard vzLogger runtime configuration when vzLogger is reactivated after Expert Mode was disabled, while retaining the dormant Expert draft and avoiding repeated overwrite confirmations once it is no longer active.
- Keep vzLogger/bridge Start and Restart plus OBIS discovery disabled until vzLogger and the respective bridge activation have been saved successfully; explain the lock directly at activation switches, service controls, and OBIS discovery, retain Stop and diagnostic actions, and reject forged runtime requests server-side.
- Consolidate German and English UI translations into the native LoxBerry `templates/lang/language_<language>.ini` resources, separate shared, vzLogger, and Legacy phrases, remove the duplicate legacy language files and loaders, and normalize branding, technical terminology, grammar, and Legacy wording in both languages.
- Localize the standalone vzLogger live-data and configuration pages, browser-side action and validation messages, Legacy choice labels, and generic meter-template names while deliberately keeping established technical terms, CLI output, logs, machine identifiers, and external diagnostics language-independent.
- Load shared validation/runtime modules from LoxBerry's installed plugin `bin` directory when opening the Legacy page, avoid rewriting `smartmeter.cfg` on read-only page loads, and normalize executable test-device uploads to LF so Apache can run CGI shebangs deployed from Windows.
- Keep the Expert Mode label and switch within the viewport by stacking the control below the configuration heading on mobile screens.
- Hide the Expert Mode reset-from-current-config action during the initial page render whenever Expert Mode is disabled, including after jQuery Mobile enhances the button markup.
- Preserve `loxberry` ownership for private generated configuration artifacts when install/upgrade hooks run Apply as root, and repair root-owned artifacts created by earlier lifecycle runs.
- Make vzLogger Save/Apply transactional: serialize configuration and service actions, generate and validate in a protected staging directory, roll back incomplete promotions, and preserve the last valid runtime files on failure.
- Propagate installer and systemd failures through the control CLI, so lifecycle hooks and callers can no longer report a successful apply after a failed service operation.
- Replace world-writable runtime, log, and serial-device permissions with the existing `loxberry` and `_vzlogger` identities; no additional system group is created.
- Persist generated custom-JSON channel UUIDs in versioned per-reader sidecars, preserving existing UUIDs during migration and keeping unchanged channels stable when reordered; reject invalid Legacy general settings without partial writes.
- Add reusable regression tests for locking/rollback, custom UUID registries, Legacy allow-lists, and MQTT bridge topic parsing, and run them in CI.
- Standardize developer packages through a local build script that mirrors the GitHub release archive rules, always labels local ZIPs with purpose/commit/dirty state, verifies archive contents and plugin version, and reserves suffixless release assets exclusively for the GitHub release workflow.
- Add a persistent, reload-free Expert Mode for editing the complete `vzlogger.conf`: switch modes immediately via AJAX while keeping expanded UI sections open, retain the expert draft across mode changes and standard applies, require an explicit save/apply before a dormant draft becomes active again, offer a confirmed reset from the current runtime file, keep standard vzLogger settings read-only while active, retain invalid drafts without replacing the last valid runtime file, validate unknown upstream extensions as warnings, preserve UUID-based SmartMeter bridge outputs, and continue allowing service logging and bridge controls to update their dedicated settings.
- Replace separate discovered-channel selection and additional-OBIS input with one flat vzLogger channel editor whose rows have persistent UUIDs, may intentionally repeat an OBIS identifier, retain inactive/API-specific values, and generate only fields native to the selected API.
- Add a versioned multilingual OBIS catalog with exact entries and structured A–F fallback rules for electricity, gas, water, thermal energy, heat cost allocation, and service codes; show semantic names, explanations, expected units, aggregation recommendations, storage-index context, and manufacturer-specific fallbacks in the editor.
- Preserve explicit SML/D0 `*F` storage indices from 0 through 254 without treating them as historical queries, represent empty, `null`, and the standard unused value 255 uniformly as “Unspecified (255)”, disable them for OMS, make aggregation conditional on meter `aggtime`, and dynamically enable Volkszaehler, InfluxDB, and MySmartGrid target fields including the API-specific MySmartGrid registration name.
- Store channel state in `vzlogger_channel_definitions.json`, migrate legacy selections/custom identifiers atomically, keep plugin display/output metadata out of `vzlogger.conf`, and restrict `vzlogger_channels.json` to active plugin outputs with one unique cache/UDP key per channel.
- Prefill the editable cache/UDP output key from the OBIS identifier, publish only that configured key without compatibility aliases, and order HTTP-cache and UDP values identically: `Last_Update`, `Last_UpdateLoxEpoche`, configured outputs by ascending `chnN`, and unmapped additional values alphabetically.
- Refresh jQuery Mobile select widgets after dynamic enable/disable changes so the bridge update-cycle dropdown no longer remains visually disabled after switching from Legacy to vzLogger and applying without a page reload.
- Drop a removed meter's OBIS channel model from the current browser session and hydrate re-detected meter panels from fresh server state so deleted channels cannot reappear before a new discovery run.
- Keep configuration sections, collapsibles, tables, channel cards, and jQuery Mobile input wrappers within the physical mobile viewport by replacing residual table layout at narrow breakpoints, reducing nested padding on phone-sized screens, grouping each setting name more closely with its control, separating subdued grey help text with a subtle guide line before the following setting, and aligning enhanced text/select controls with native fields and switches.
- Make the Legacy configuration mobile-safe as well by stacking its outer and nested layout tables, constraining enhanced and native form controls, wrapping long labels and URLs, presenting action buttons at the available phone width, keeping both implementation tabs equally high regardless of the active tab or mobile browser, applying the same label/control/subdued-help rhythm as the vzLogger view, and normalizing the horizontal alignment of enhanced inputs.
- Resolve MQTT channels primarily by UUID/`chnN`, use an identifier fallback only when unambiguous, and base energy scaling and calculated-power recognition on structured OBIS identifiers rather than output names.
- Show the custom semantic channel name or OBIS-catalog name on the rendered live-data page and display values with catalog units, including explicit Wh-to-kWh conversion for electrical SML counters.
- Keep advanced channel settings expanded while editing, use the full reader-panel width for channel cards, highlight only the open settings content with a subtle pastel-yellow editing surface, compact the API and aggregation selectors, preserve the storage index as a native integer spinner, and add visible field-level help for common and API-specific channel options.
- Show each channel's applied vzLogger/MQTT DATA index in the editor and its persistent UUID in the advanced-settings heading; refresh channel numbers directly after Save/Apply and mark unapplied or inactive definitions without inventing an index.
- Allow manually created OBIS channels to be staged for removal from their advanced settings, with channel/OBIS/UUID confirmation and persistence only on Save/Apply; keep discovered channels available for deactivation instead.
- Expand Validate config and Save/Apply checks to cover submitted numeric ranges, protocol-specific SML/D0/OMS fields, aggregation dependencies, MQTT topics and TLS combinations, API-specific channel requirements, device and certificate paths, active-meter/bridge requirements, and UUID/identifier/`chnN` consistency across generated configuration, definitions, and bridge mapping.
- Prefill new cache/UDP output keys from independent OBIS-catalog metadata using `<Clear_Name>_OBIS_<short-code>` (including `*F` when present), retain existing configured keys, allow parser-friendly spaces and selected punctuation, and report the complete required format in UI and backend validation errors.

## 2.0.0.33 - 2026-07-17

- Replace the persistent yellow service-action output with a brief green success confirmation, keep warnings and failures open in the action dialog, verify that service actions reach their requested final state, and add a shared control-log link below the service panels.
- Improve the Validate and Save/Apply overlays with action-specific wait text, an elapsed-time counter, and a shared 60-second server-side timeout whose failure remains visible in the overlay.
- Run generated-config validation, debug-log creation, and Save/Apply through AJAX without a page reload. Validation uses a temporary draft and never changes the saved or generated configuration, while Save/Apply remains the only form action that writes it. Keep validation and apply failures open for acknowledgement, auto-close a successful apply after three seconds, and monitor debug-log creation entirely in its new tab with a 45-second server-side limit. Render the generated configuration in a readable masked view, restore each collapsible panel's browser-local open state after a manual reload, and reject invalid or unreasonably large generated baud rates.
- Map an SML template's operating/read baud rate to vzLogger instead of its initial communication baud rate, correct Generic SML to the verified 9600 baud/8N1 operating defaults, determine apply success from the requested final service state, reset the vzLogger failure state before disabling its generated unit, close a failed OBIS-discovery overlay before showing the error alert, and clear saved meter/template/OBIS pending markers immediately after AJAX Save/Apply.

## 2.0.0.32 - 2026-07-17

- Show the effective Legacy meter-template values in the disabled manual-settings fields while preserving the separately saved manual configuration for later reselection.
- Reduce normal, field-label, and help-text sizes in the SmartMeter configuration UI, compact buttons, vertically centered switches, select boxes, and text inputs, tighten panel and table spacing, and remove the redundant Operation heading.
- Replace the low-contrast implementation-tab status dots with larger, centered white badges using a green check mark for active and a dark-gray minus for inactive.
- Apply the same compact typography, controls, switches, inputs, headings, and table spacing to the Legacy configuration page, and align its MQTT-topic input with the UDP-port field.
- Use one neutral meter-template catalog for both Legacy and vzLogger, generate both selectors from it, and map its initial/read baud rates to each implementation's field names without a reversed Legacy fallback.
- Restore the selected protocol after a page reload from the generated vzLogger configuration for saved meters and from the pending OBIS-discovery draft only for new, unsaved meters.
- Preserve an existing valid `vzlogger.conf` while Legacy or neither implementation is active and reactivate it unchanged when switching back to vzLogger; migrate Legacy meter settings only when no valid generated vzLogger configuration exists.
- Store Legacy meter selection and manual serial settings in separate `LEGACY_*` keys, migrate existing values once, and make the Legacy UI and polling runtime use that isolated state so saving vzLogger no longer clears a working Legacy reader configuration.

## 2.0.0.30 - 2026-07-17

- Add a protocol-filtered **Initialize from template** selector for SML and D0 meters that applies known baud-rate, serial-mode, and D0 timeout values without changing unrelated meter settings, and warns when a template requires unsupported meter-specific sequences.

## 2.0.0.29 - 2026-07-17

- Enlarge the implementation tabs and their status icons, place each icon before its label, and vertically center icon and text together.
- Allow both Legacy and vzLogger implementations to be inactive while still preventing simultaneous activation, add active/inactive icons to both implementation tabs, and mark unsaved changes beside the vzLogger, bridge, and Legacy activation switches.
- Add distinct, state-aware tooltips for service Start, Stop, and Restart, I/R-head scanning, OBIS discovery, and the generated-configuration viewer, and repeat the action help in the right-side help column where the layout permits it.

## 2.0.0.28 - 2026-07-16

- Fix manual vzLogger Start, Stop, and Restart failing to read `smartmeter.cfg` after loading the generated JSON configuration with an unscoped Perl input-record separator.
- Visually separate the framed vzLogger and SmartMeter-bridge configuration areas with a consistent heading hierarchy, and immediately toggle the bridge UDP port when the unsaved Send UDP switch changes.
- Apply enabled/disabled states from one central UI state calculation to controls, labels, section headings, help text, and complete configuration frames for vzLogger, local HTTP, MQTT, bridge, HTTP-cache status, UDP, and standard SML/D0/OMS meters; preserve every disabled value and keep only meter description plus activation editable for an inactive meter.
- Run vzLogger and SmartMeter-bridge Start/Stop/Restart through AJAX without reloading or saving unrelated form values, persist each service's log controls, let Start/Restart additionally apply only the selected service activation when the existing configuration is valid, require applied and generated MQTT for bridge starts, update only `log` and `verbosity` in the current vzLogger configuration, refresh both service states plus live links every three seconds while the page is visible, pause polling during an action, and show an action-specific progress overlay with a 15-second delay notice that closes automatically on success and remains dismissible on failure while the action response directly refreshes the final status.
- Add a read-only button beside the generated-configuration path that opens `vzlogger.conf` in a new browser tab while masking password values.
- Add a per-reader Remove action that stages deletion in the browser, commits it only with Save and apply, removes the meter section, channel mappings, and owned meter artifacts, keeps connected removed readers hidden during normal reloads, and lets an explicit I/R rescan recreate their defaults.
- Treat applying a configuration without meters as a valid disabled state that stops vzLogger and the bridge and removes the SmartMeter service override.
- Run SML, D0, and OMS OBIS discovery directly with current unsaved meter settings, select and mark only genuinely new channels until Save and apply, preserve known deselections, and retain discoveries with a visible warning if restoring the previous vzLogger state fails.
- Update OBIS discovery results in place instead of reloading the page, preserving unsaved protocol choices, meter fields, and checkbox deselections while adding newly detected channels.
- Mark newly discovered meter panels as New / unsaved and retain only their OBIS-tested SML, D0, or OMS protocol in a meter-specific pending file so a later page reload can show the cached channels; clear the marker on Save and apply or meter removal.
- Run I/R reader discovery through AJAX with a non-dismissible active overlay, a 15-second request guard, separate lists for genuinely new and connected browser-staged removals, in-place insertion or restoration of their panels without losing unsaved values, no page reload, and a visible three-second auto-close countdown only when neither kind of reader was found.
- Run OBIS channel discovery as a browser-independent background job, persist its result from the watchdog itself, poll status once per second, resume the progress overlay after a page reload, and provide a controlled cancel action that restores vzLogger.
- Run temporary vzLogger OBIS discovery in the foreground under an independent timeout, inspect its log once per second, and finish early once every detected OBIS channel has appeared at least twice; browser reloads cannot leave the serial reading head blocked, and vzLogger Start, Stop, or Restart removes matching plugin test processes.
- Omit empty optional SML, D0, and OMS meter parameters from generated JSON, leave SML baud rate and parity unset by default, and preserve explicit `false`, `0`, baud-rate, and parity values.
- Remove the TCP `host` field from the standard SML and D0 reader forms and generated meter objects; network-backed meters remain available through the custom JSON mode.
- Add the common vzLogger meter controls `enabled`, `allowskip`, and `aggtime` to each standard SML, D0, and OMS reader panel.
- Replace the flat vzLogger meter-preset table with one collapsed panel per detected I/R reading head and protocol-specific SML, D0, and OMS fields; retain legacy preset values during migration, limit the normal OBIS UI to these protocols, accept complete and short OBIS identifiers, and reopen the affected reader after discovery.
- Add a custom JSONC meter mode that preserves each reader's original source including comments, validates one complete meter object, omits invalid objects without blocking other meters, highlights JSON and missing-device warnings in collapsed headings, and limits generated changes to stable missing channel UUIDs and missing `api: "null"` values.
- Separate runtime control into always-visible vzLogger and SmartMeter-bridge service panels, keep each debug-log control beside its service log action, place vzLogger log level in its service row, and move bridge update, HTTP-cache, and UDP options into a compact collapsed bridge-settings section with consistent vzLogger/MQTT dependency handling and a correctly re-enabled UDP port field.
- Add a collapsed MQTT section grouped into connection/publishing, user/password authentication, and certificate authentication; show effective LoxBerry broker, port, and user values without duplicating unchanged values as plugin overrides, omit empty optional MQTT keys from `vzlogger.conf`, and never return stored passwords in GUI HTML or unmasked diagnostics.
- Generate `vzlogger.conf` in the documented section and parameter order instead of alphabetically sorting JSON keys, beginning with root `retry`, `verbosity`, and `log`.
- Add the vzLogger root `retry` setting to a collapsed advanced service section and preserve the configured value whenever `vzlogger.conf` is regenerated.
- Align configuration and help columns across all vzLogger sections, enlarge the help column, and use the service-panel help-text size consistently.
- Add a collapsed **vzLogger HTTP service (local)** section with configurable `enabled`, `port`, `index`, `timeout`, and `buffer` values in the generated configuration.
- Start the system `vzlogger` service directly with the generated plugin configuration through a SmartMeter-managed systemd drop-in instead of copying the file to `/etc/vzlogger.conf`; remove the override again when switching to Legacy mode or uninstalling the plugin.
- Set the generated local vzLogger HTTP ring buffer default to the documented value `-1`, retaining one tuple per channel while keeping the live JSON response compact.
- Structure the rendered vzLogger live-data page by I/R reading head and configured channel, show channel number, OBIS identifier and mapped name, add readable local times next to raw timestamps, and reload channel metadata only when its generated mapping changes.
- Add dynamic vzLogger OBIS channel discovery: the GUI can read available channels through a temporary vzLogger test configuration with only the selected I/R head, empty `channels`, disabled MQTT, verbose logging, and per-head log parsing, cache the result per I/R head, keep unchecked discovered channels visible on later page loads, omit legacy-calculated power channels and previously configured but undiscovered channels after a successful read, and generate `vzlogger.conf` from selected discovered channels plus the additional OBIS fallback field.
- Keep OBIS discovery diagnostics in persistent control and per-reader log files instead of relying on the former synchronous result box, and avoid noisy SML parser array-to-string notices during legacy reads.
- Sort discovered vzLogger OBIS channels numerically in the UI and generated configuration.
- Avoid Perl warnings while sorting alphanumeric OBIS identifiers such as `1-0:C.5.0` during vzLogger configuration generation.
- Omit the unused Volkszähler endpoint URL from generated vzLogger channels because Smartmeter uses `api: "null"` and processes readings through the local MQTT bridge.
- Write vzLogger MQTT bridge HTTP cache files only on the configured update cycle instead of after every received MQTT reading, reducing SD-card writes and system load.

## 2.0.0.27 - 2026-07-11

- Keep the vzLogger service debug switch, log level, and local HTTP port editable in vzLogger mode even when the MQTT bridge is disabled.

## 2.0.0.26 - 2026-07-11

- Add known vzLogger OBIS channel selections for manufacturer ID (`1-0:96.50.1`) and server ID (`1-0:96.1.0`) so they map to the legacy-compatible cache names.
- Write legacy-compatible `Last_Update` and `Last_UpdateLoxEpoche` fields from vzLogger MQTT timestamps and scale vzLogger energy counter readings from Wh to kWh in the bridge cache.
- Parse additional vzLogger OBIS channels saved with escaped `\n` separators so all configured custom channels are generated into `vzlogger.conf`.
- Preserve unchecked vzLogger OBIS channel selections instead of restoring all default channels after saving.
- Set the default vzLogger service log level to `0` while keeping the debug-log switch unchanged.
- Document the MQTT bridge as optional and off by default on fresh installs.
- Allow the `vzlogger` service to start and run in vzLogger mode even when the MQTT bridge is disabled; applying the configuration now stops only the bridge when the bridge switch is off.

## 2.0.0.25 - 2026-07-11

- Regenerate and validate the saved vzLogger configuration before manual service Start/Restart actions, so service controls no longer reuse a stale generated configuration.
- Fail vzLogger validation when meter reading is enabled but no detected I/R head has a meter preset selected, instead of attempting to start `vzlogger` with an empty `meters` list.

## 2.0.0.24 - 2026-07-11

- Fix fresh installs so the SmartMeter I/R head udev rule is installed and triggered from the root hook immediately, making `/dev/serial/smartmeter/*` readers available before the first reboot.
- Clarify the apply output when vzLogger mode is selected but meter reading is disabled.
- Purge the plugin-managed `vzlogger` package and remove runtime cache plus stale service links during uninstall.

## 2.0.0.23 - 2026-07-11

- Publish the GitHub-built plugin ZIP through a draft-release flow so immutable GitHub Releases already contain `Smartmeter-V<version>.zip` when they become public.
- Automate GitHub Release plugin ZIP asset creation and point prerelease update metadata at the uploaded release asset instead of GitHub's automatic source archive.
- Fix fresh installs where `preroot.sh` created the plugin config directory as root before LoxBerry copied `smartmeter.cfg`, causing the config install step to fail with `Permission denied`.

## 2.0.0.22 - 2026-07-11

- Automate GitHub Release plugin ZIP asset creation and point prerelease update metadata at the uploaded release asset instead of GitHub's automatic source archive.
- Fix fresh installs where `preroot.sh` created the plugin config directory as root before LoxBerry copied `smartmeter.cfg`, causing the config install step to fail with `Permission denied`.

## 2.0.0.21 - 2026-07-11

- Enable the `vzlogger` systemd service during vzLogger Save/Apply, Start, and Restart so it starts again automatically after a LoxBerry reboot while vzLogger meter reading is active.

## 2.0.0.20 - 2026-07-11

- Fix the vzLogger MQTT bridge channel parser so retained `chnN/uuid` and `chnN/id` messages keep their channel name while validating the payload, allowing subsequent `chnN/raw` values to populate the plugin cache.
- Restart the vzLogger MQTT bridge during Save/Apply so changes to the bridge debug switch are applied immediately instead of waiting for a manual service restart.

## 2.0.0.19 - 2026-07-10

- Moved the optional vzLogger service debug log into the plugin log directory at `/opt/loxberry/log/plugins/smartmeter-v2/vzlogger.log` and prepare it before restarting vzLogger.
- Moved the vzLogger update cycle out of the HTTP cache section and changed it from a free numeric field to a fixed seconds/minutes dropdown.

## 2.0.0.18 - 2026-07-10

- Fixed vzLogger MQTT bridge parsing for `chnN/raw` payloads without embedded UUIDs by persisting the generated `chnN` channel mapping and using it before sending cache/UDP values.
- Fixed vzLogger MQTT bridge channel discovery for retained `chnN/id` topics that include an OBIS suffix such as `*255`.
- Added a vzLogger HTTP cache section showing cache status, last update, and a direct link to the existing plugin cache endpoint.
- Renamed the vzLogger HTTP port label to clarify that it configures the vzLogger live-data service, not the plugin HTTP cache.
- Fixed upgrades preserving an active vzLogger configuration: the root hook now reapplies the generated configuration and restarts `vzlogger` plus the MQTT bridge after LoxBerry finishes dependency handling, so an old bridge process cannot keep running after an update.
- Masked MQTT passwords in generated vzLogger debug logs, including `systemctl` and `journalctl` output that shows `mosquitto_sub -P ...`.
- Fixed the initial plugin page so it opens the active implementation tab instead of always showing Legacy.
- Added a vzLogger service log-level setting for the generated `verbosity` value when the vzLogger debug log is enabled.
- Moved vzLogger control, apply, and generated diagnostic logs to the LoxBerry plugin log directory.
- Removed the separate vzLogger UDP interval field; the update cycle now controls vzLogger publishing and the bridge UDP send cycle.

## 2.0.0.17 - 2026-07-10

- Fixed upgrade-time vzLogger bridge service refresh so systemd changes run from the root hook instead of `postupgrade.sh`.
- Fixed the implementation tabs so Legacy and vzLogger use compact, always available labels.
- Removed the duplicate `Active` section heading and restored the plugin title/version in the page header.
- Reordered the vzLogger service controls so log/debug actions stay with Start/Stop and live-data links sit below them.
- Moved the vzLogger HTTP port next to the vzLogger live-data links because it configures the vzLogger service.
- Moved the MQTT base topic into the vzLogger service section before the bridge settings.
- Clarified the custom OBIS channel help text with accepted separators and examples.
- Moved action explanations to right-side help text and added tooltips for validate, debug-log, and save/apply.
- Fixed persisted OBIS checkbox selections being shown as unchecked after saving.
- Moved the bridge log path from the Bridge service label into the right-side help text.
- Split standard and custom OBIS channel inputs into separate rows with separate help text.

## 2.0.0.16 - 2026-07-10

- Fix the bridge systemd environment so LoxBerry Perl modules load outside a login shell.
- Parse verified vzLogger `chnN/uuid` plus `chnN/raw` MQTT messages and populate the legacy-compatible cache.
- Simplify the vzLogger workflow to save/apply, clarify manual validation, and reorganize service controls.
- Add a generic auto-refreshing live-data page alongside the raw JSON endpoint.
- Add selectable and custom OBIS channels per vzLogger reader.
- Calculate legacy-compatible consumption and delivery power values in the MQTT bridge from counter deltas.
- Open generated vzLogger diagnostic logs directly in the LoxBerry log viewer.
- Separate bridge and vzLogger debug controls; bound plugin logs and use the package-rotated vzLogger log only in debug mode.
- Improve implementation-tab sizing and borders and remove duplicate technical status output.

## 2.0.0.15 - 2026-07-10

### Added

- Added an explicit I/R head rescan action to the vzLogger view.
- Added an always-visible vzLogger live-JSON link and always-visible service log buttons that are disabled until their targets are available.
- Added expectation-aware service status colors for active and inactive operating modes.

### Changed

- Unified the Legacy and vzLogger navigation spacing and moved the active implementation switch to the first section in both views.
- Grouped vzLogger meter-reading settings and bridge controls, disabling dependent settings unless meter reading is enabled.
- Preserved configured reading, MQTT, UDP, HTTP, and debug values while their controls are disabled.
- Clear stale systemd failure states when services are intentionally stopped.

### Fixed

- Fixed vzLogger startup under its dedicated `_vzlogger` account by writing its log to the plugin runtime directory with suitable permissions.
- Read LoxBerry's `Brokeruser` and `Brokerpass` MQTT fields so vzLogger and the bridge can authenticate with the local broker.

### Upgrade Notes

- No manual migration is required. Install the prerelease over the existing SmartMeter v2 installation.

## 2.0.0.14 - 2026-07-10

### Added

- Added GitHub Actions syntax checks for Perl and PHP files.
- Added an explicit implementation mode switch between `legacy` and `vzlogger`.

### Changed

- vzLogger is now installed or updated during plugin installation through LoxBerry `dpkg/apt`; the plugin configures the Volkszaehler apt repository in `preroot.sh`.
- The explicit `Install vzLogger package` button was removed because package installation is now part of the LoxBerry installation flow.
- The explicit `Install bridge service` button was replaced with status, Restart, Start/Stop, and log controls for the vzLogger and MQTT bridge services.
- Applying active vzLogger mode now installs and starts the MQTT bridge systemd service automatically when needed; disabling vzLogger stops both services.
- Installation and upgrade now stop and disable the vzLogger service again while Legacy mode is active, so the package can be present without running in parallel.
- Selecting vzLogger mode now removes the legacy polling cron jobs before applying the vzLogger runtime.
- Selecting or saving the legacy configuration now stops vzLogger and the MQTT bridge and restores the legacy polling cron when meter reading is enabled.

### Fixed

- Fixed vzLogger maintenance actions so package installation, validation, bridge service installation, and debug-log creation run independently of the currently active implementation mode.
- Removed a Perl precedence warning from the MQTT bridge status command and made stopping vzLogger quiet when the service is not installed.
- Fixed the legacy warning layout so it no longer uses an absolute-positioned navbar that can cover the LoxBerry header.
- Fixed the vzLogger control status action failing to compile while listing runtime cache files.
- Fixed the active implementation switch rendering by using contextual on/off labels instead of long implementation names.
- Removed the duplicate in-page tab bar from the vzLogger view.
- Kept configured IR heads visible even when the current `/dev/serial/smartmeter` symlink is missing.

### Upgrade Notes

- Existing active legacy installations default to `legacy`; inactive or new configurations default to `vzlogger`.

## 2.0.0.11 - 2026-07-07

### Added

- Added vzLogger debug logging and a diagnostic log action for service status, generated config, channel mapping, bridge logs, cache files, and MQTT parser evidence.

### Changed

- Moved the new vzLogger configuration page text into German and English language files.
- Updated German and English user guides with the vzLogger workflow while keeping the legacy implementation documented.

### Fixed

- Added the missing `language.ini` keys for the vzLogger configuration page.
- Redirected the unused log form path to the existing log file view.
- Avoided restarting vzLogger after a failed privileged config copy.
- Added persistent vzLogger control/UI action logging and included available LoxBerry install/plugin log tails in the debug log.

### Upgrade Notes

- This is a prerelease for LoxBerry target-system validation of the vzLogger migration MVP.

## 2.0.0.10 - 2026-07-07

### Changed

- Reworked meter polling runtime file handling to use a shared runtime directory variable.
- Replaced several shell-command calls with direct Perl file, process, and symlink operations.
- Added a non-blocking fetch lock to avoid overlapping meter polling runs.
- Added atomic meter data file replacement to reduce partial-read risk.
- Added basic validation for legacy web frontend configuration values.

### Fixed

- Improved error reporting when `sm_logger.pl` fails during polling.
- Kept the fetch lock when clearing runtime cache files.
- Removed the external `dos2unix` dependency from serial dump handling.

## 2.0.0.9 - 2026-07-07

### Fixed

- Moved the documentation website URL to the `PLUGIN.WEBSITE` metadata field used by the LoxBerry v4 plugin management UI.

## 2.0.0.8 - 2026-07-06

### Added

- Added the plugin documentation landing page.
- Added German and English user guides.
- Documented MQTT topic structure, default MQTT base topic, UDP output, and HTTP access.

## 2.0.0.7 - 2026-07-06

### Changed

- Changed MQTT publishing to use the LoxBerry MQTT Gateway UDP input instead of connecting directly to an MQTT broker.

### Fixed

- Removed the direct `Net::MQTT::Simple` runtime dependency from MQTT publishing.

## 2.0.0.6 - 2026-07-06

### Added

- Added MQTT publishing for meter values.
- Added MQTT configuration defaults and web frontend settings.
- Added German and English language entries for MQTT settings.

### Changed

- Extended upgrade handling for the new MQTT configuration values.

## 2.0.0.5 - 2026-07-06

### Fixed

- Restored automatic meter polling cron jobs during plugin upgrades.
- Improved upgrade log restoration to avoid overwriting existing log directories incorrectly.
- Quoted upgrade paths more safely in `postupgrade.sh`.

## 2.0.0.4 - 2026-07-06

### Added

- Added Iskra MT631 SML protocol support.

### Changed

- Refactored cron job management into helper functions.
- Adjusted plugin packaging metadata for LoxBerry compatibility.

### Fixed

- Fixed LoxBerry plugin packaging findings from the release preparation.

## 2.0.0.3 - 2026-07-06

### Added

- Added OBIS ID parsing for SML values not present in the known OBIS mapping.

### Fixed

- Handled SML data without a complete footer more gracefully.
- Used the LoxBerry home directory placeholders for daemon log paths.
- Fixed reboot cron runner setup.

## 2.0.0.2 - 2026-07-06

### Changed

- Prepared the `2.0.0.2` prerelease metadata.

### Fixed

- Improved SML parser handling for unknown OBIS codes and multi-message data.

## 2.0.0.1 - 2026-07-06

### Added

- Started the SmartMeter v2 release line.

### Changed

- Renamed the plugin to Smartmeter v2.
- Marked runtime scripts as executable.
- Included earlier parser and runtime compatibility updates from the pre-release history.
