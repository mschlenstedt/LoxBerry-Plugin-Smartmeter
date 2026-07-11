# vzLogger Implementation Plan

This plan tracks the migration from the legacy SmartMeter reader to a vzLogger-based standard implementation. The target architecture is:

- `vzlogger` is installed as an external apt package, not bundled in this plugin.
- vzLogger reads the meters and publishes values natively via MQTT.
- The plugin configures vzLogger, maintains a local MQTT-derived cache, and serves HTTP/UDP from that cache.
- The legacy implementation remains available as a supported fallback and parallel configuration path. It must not be removed as part of this vzLogger migration.

## Status Legend

- `[x]` Implemented in the repository
- `[~]` Partially implemented, needs target-system verification or refinement
- `[ ]` Open

## 1. Package And Repository Setup

- `[x]` Remove bundled vzLogger binary from the plugin.
- `[x]` Keep `mosquitto-clients` as regular plugin dependency.
- `[x]` Keep `vzlogger` as regular `dpkg/apt` dependency after configuring the Volkszaehler/Cloudsmith apt repository in `preroot.sh`.
- `[x]` Remove the explicit `Install vzLogger package` UI button.
- `[x]` Stop and disable the vzLogger service in `postroot.sh` unless vzLogger mode and meter reading are explicitly enabled.
- `[x]` Preserve an active vzLogger service across plugin upgrades by recording the pre-upgrade state in `preroot.sh` and applying the generated configuration from `postroot.sh`.
- `[~]` Verify `preroot.sh` repository setup on the target LoxBerry versions as root.
- `[ ]` Confirm supported Debian/Raspberry Pi OS codenames and architecture behavior.

Decision notes:

- The plugin no longer ships a stale ARM binary. This avoids architecture drift and security/maintenance issues.
- The repository setup uses explicit keyring and source-list setup instead of a blind `curl | bash`.
- The normal plugin dependency file installs `vzlogger` and `mosquitto-clients`; apt can update an already installed `vzlogger` package to the current candidate version.
- Target test 2.0.0.21 confirmed repository setup and package installation on Debian trixie, but also showed that the root hook must hand the plugin config directory back to the `loxberry` user before the normal config copy step.

Implemented files:

- `preroot.sh`
- `postroot.sh`
- `dpkg/apt`
- `postinstall.sh`
- `postupgrade.sh`
- `templates/settings.html`

## 2. vzLogger Configuration Generation

- `[x]` Add `bin/vzlogger_config.pl`.
- `[x]` Generate plugin-owned `vzlogger.conf` below the plugin config directory.
- `[x]` Generate `vzlogger_channels.json` mapping stable channel UUIDs to legacy-compatible cache names.
- `[x]` Read meter definitions from existing `smartmeter.cfg`.
- `[x]` Map legacy presets to vzLogger protocols `sml` or `d0`.
- `[x]` Generate a default set of common OBIS channels.
- `[x]` Configure native vzLogger MQTT output.
- `[x]` Configure local vzLogger HTTP daemon settings.
- `[~]` Map serial/D0 settings from legacy fields.
- `[ ]` Verify all legacy meter presets against actual vzLogger options.
- `[x]` Make OBIS channels configurable in the UI, including custom meter-specific OBIS identifiers.
- `[ ]` Add dynamic OBIS channel discovery for configuration, for example by temporarily running vzLogger with `verbosity: 15` and parsing discovered OBIS identifiers from the vzLogger log.
- `[ ]` Add a guided migration from existing legacy config to vzLogger config.

Decision notes:

- UUIDs are generated deterministically from plugin folder, serial, and OBIS identifier, so MQTT topics/mapping remain stable across regenerations.
- The generator keeps HTTP enabled for optional vzLogger live readings, but MQTT is the primary integration path.
- `MAIN.READ=0` causes generated meter entries to be disabled, so apply can stop services cleanly.
- Custom OBIS identifiers are normalized by removing an optional `*255` suffix before writing the vzLogger configuration.
- Dynamic OBIS discovery should cache discovered channels per meter/reader and allow the user to select them before regenerating `vzlogger.conf`.

Implemented files:

- `bin/vzlogger_config.pl`
- `config/smartmeter.cfg`
- `webfrontend/htmlauth/index.cgi`
- `templates/settings.html`

## 3. Configuration Validation

- `[x]` Add `bin/vzlogger_validate.pl`.
- `[x]` Validate generated JSON syntax.
- `[x]` Validate required top-level sections: `mqtt`, `local`, `meters`.
- `[x]` Validate MQTT/local ports.
- `[x]` Validate meter protocol, device, channels, UUID format, and duplicate UUIDs.
- `[x]` Validate channel mapping file.
- `[x]` Make `generate` validate after writing config.
- `[x]` Make `apply` abort if validation fails.
- `[x]` Show validation status in `status`.
- `[x]` Add `Validate config` UI button.
- `[ ]` Validate against a real installed `vzlogger` binary if a reliable dry-run/check option is identified.
- `[ ]` Run Perl syntax checks on LoxBerry.

Decision notes:

- No reliable documented `vzlogger --check` or dry-run option has been confirmed yet, so validation is currently structural.
- This still prevents starting services with malformed JSON or incomplete required plugin-generated structures.

Implemented files:

- `bin/vzlogger_validate.pl`
- `bin/vzlogger_control.pl`
- `templates/settings.html`
- `docs/Readme.md`

## 4. MQTT-First Data Flow

- `[x]` Use native vzLogger MQTT as the standard data source.
- `[x]` Add `bin/vzlogger_mqtt_bridge.pl`.
- `[x]` Subscribe to `<base-topic>/vzlogger/#`.
- `[x]` Convert MQTT readings into legacy-compatible `.data` cache files below `/var/run/shm/<plugin>/`.
- `[x]` Preserve HTTP compatibility by continuing to serve cached `.data` files through the existing PHP endpoint.
- `[x]` Send UDP cyclically from cached values to configured Miniservers.
- `[x]` Parse the verified retained `chnN/id`, `chnN/uuid`, and `chnN/raw` MQTT topic sequence.
- `[x]` Persist generated `chnN` channel indexes in `vzlogger_channels.json` so `chnN/raw` messages without embedded UUIDs can be parsed deterministically.
- `[x]` Add debug logging for raw MQTT messages, parser decisions, mapped cache names, and ignored messages.
- `[x]` Add a diagnostic debug-log action to capture status, config, mapping, control/UI action logs, install/plugin logs, cache files, and MQTT samples for parser verification.
- `[x]` Calculate legacy-compatible consumption and delivery power values from counter deltas.
- `[x]` Capture real vzLogger MQTT topics/payloads on a target system (2.0.0.15).
- `[x]` Adjust bridge parser to the exact real payload format.
- `[X]` Add last-value and last-update display to the web UI. The HTTP cache section now shows cache presence, last update, and the cache endpoint link.

Decision notes:

- MQTT is the bridge between vzLogger and plugin outputs.
- HTTP and UDP are intentionally cache-based, not direct live calls into vzLogger.
- Retained MQTT messages are expected to repopulate cache after restart.
- The debug log is the standard evidence artifact for closing the real-payload parser verification.
- 2.0.0.19 target testing showed the parser must preserve the captured `chnN` topic segment before validating `/uuid` or cleaning `/id` payloads, because later regex matches reset Perl's `$1`.

Implemented files:

- `bin/vzlogger_mqtt_bridge.pl`
- `bin/vzlogger_config.pl`
- `bin/vzlogger_control.pl`
- `templates/settings.html`
- `webfrontend/html/index.php` remains the existing HTTP cache endpoint

## 5. Bridge Service Integration

- `[x]` Add systemd service template for the MQTT bridge.
- `[x]` Add root helper to install/remove the bridge systemd unit.
- `[x]` Make `start-bridge`/`restart-bridge` install the bridge systemd service when the unit is missing.
- `[x]` Make `start-bridge`/`stop-bridge` prefer systemd when the unit is installed.
- `[x]` Keep forked bridge process as fallback if systemd unit is absent.
- `[x]` Add `--foreground` support to the bridge script for systemd.
- `[x]` Replace the explicit `Install bridge service` UI button with service status and Restart/Start/Stop controls.
- `[x]` Remove bridge service on plugin uninstall.
- `[x]` Test service install/start/stop/restart on LoxBerry (2.0.0.14; service installation and control work, while startup without the configured I/R head fails as expected).
- `[ ]` Decide whether bridge service should be auto-installed during plugin install or remain explicit user action.

Decision notes:

- The plugin does not force a service install during normal installation, because systemd changes need root privileges and should be explicit.
- Once installed, the service provides production behavior: autostart and restart on failure.

Implemented files:

- `templates/systemd/smartmeter-vzlogger-bridge.service.in`
- `bin/install_vzlogger_bridge_service.sh`
- `bin/vzlogger_control.pl`
- `bin/vzlogger_mqtt_bridge.pl`
- `uninstall/uninstall`

## 6. Web Frontend

- `[x]` Replace vzLogger placeholder with a working MVP configuration form.
- `[x]` Support read enable/disable.
- `[x]` Support update cycle.
- `[x]` Support MQTT base topic.
- `[x]` Support UDP enable/port/cycle.
- `[x]` Support vzLogger local HTTP port and debug-controlled vzLogger logging.
- `[x]` Detect IR heads below `/dev/serial/smartmeter/*`.
- `[x]` Allow selecting legacy meter presets and basic manual serial values.
- `[x]` Show control/status output.
- `[x]` Link to vzLogger local HTTP live readings.
- `[x]` Move hard-coded English UI strings to language files.
- `[x]` Add a debug-log option and debug-log creation button.
- `[x]` Add raw JSON and automatically refreshed, generically rendered live-data links.
- `[x]` Reduce the normal workflow to one save/apply action; retain validation for manually edited configuration.
- `[x]` Separate bridge and vzLogger debug controls and document their log paths.
- `[~]` Add better LoxBerry-style layout polish (implementation tabs and service grouping refined after 2.0.0.15 test).
- `[~]` Add log links for vzLogger, bridge, and generated config (service log links added; generated config remains a path display).
- `[ ]` Add last cached values table.
- `[x]` Add explicit OBIS channel selection and custom OBIS entry.

Decision notes:

- The current UI is deliberately an MVP to unlock end-to-end testing.
- Legacy UI remains available via the existing legacy page and is intentionally kept as a supported mode.

Implemented files:

- `webfrontend/htmlauth/index.cgi`
- `templates/settings.html`
- `templates/de/language.txt`
- `templates/en/language.txt`
- `templates/multi/de/language.txt`
- `templates/multi/en/language.txt`

## 7. Service Control And Apply Flow

- `[x]` Add `vzlogger_control.pl` as central command wrapper.
- `[x]` `generate`: generate config and validate.
- `[x]` `validate`: regenerate the saved config, then validate generated config and mapping.
- `[x]` `apply`: generate, validate, stop if disabled, otherwise restart vzLogger and bridge.
- `[x]` `start`/`restart` service actions: regenerate and validate before starting services so form changes do not reuse stale generated config.
- `[x]` `status`: report package, apt source, config, validation, vzLogger service, bridge service/process.
- `[x]` `debug-log`: create a diagnostic log for troubleshooting and MQTT parser verification.
- `[~]` Copy generated config to `/etc/vzlogger.conf` during apply.
- `[ ]` Decide whether to support a custom vzLogger config path instead of overwriting `/etc/vzlogger.conf`.
- `[ ]` Test permission behavior when actions are triggered from the web UI as the LoxBerry user.

Target finding (2.0.0.15): the bridge unit lacked LoxBerry's Perl library environment and exited with status 2 because `LoxBerry::System` was not in `@INC`. The unit template now sets `LBHOMEDIR` and `PERL5LIB` explicitly.

Decision notes:

- Current apply behavior uses `/etc/vzlogger.conf`, because the packaged vzLogger service is expected to use that path.
- If permission fails, the control script reports that root/manual copy is required.
- Meter reading with no selected meter preset is invalid. A detected I/R head alone is not enough to start vzLogger because the generated config would contain an empty `meters` list.

Implemented files:

- `bin/vzlogger_control.pl`

## 8. Install, Upgrade, And Uninstall Hooks

- `[x]` Set executable permissions for helper scripts in `postinstall.sh`.
- `[x]` Set executable permissions for helper scripts in `postupgrade.sh`.
- `[x]` Install and trigger the SmartMeter I/R head udev rule from `postroot.sh` so readers are visible before the first reboot.
- `[x]` Migrate `[VZLOGGER]` default config section during upgrade.
- `[x]` Install `vzlogger` and `mosquitto_sub` through LoxBerry `dpkg/apt` dependencies.
- `[x]` Remove bridge service during uninstall.
- `[~]` Existing legacy cron restore remains in place for legacy mode.
- `[x]` Disable legacy cron automatically when vzLogger mode is enabled, and stop vzLogger/bridge when legacy mode is selected.
- `[ ]` Add cleanup policy for generated `vzlogger.conf`, channel mapping, and runtime cache.

Decision notes:

- Legacy behavior is preserved as a supported mode; migration to vzLogger should be explicit and reversible.
- Generated system-wide `/etc/vzlogger.conf` is removed on uninstall only if `/etc/vzlogger.conf.smartmeter-v2` marks it as SmartMeter-generated.
- The external apt source and keyring are removed on uninstall. The `vzlogger` package is removed only if a marker shows that this plugin introduced it.

Implemented files:

- `postinstall.sh`
- `postupgrade.sh`
- `uninstall/uninstall`
- `config/smartmeter.cfg`

## 9. Documentation

- `[x]` Document the standard vzLogger package approach.
- `[x]` Document apt repository helper behavior.
- `[x]` Document configuration validation.
- `[x]` Document bridge systemd service approach.
- `[x]` Update German and English user guides with the new vzLogger workflow while keeping legacy mode documented.
- `[x]` Document troubleshooting for apt repo, MQTT, bridge service, and vzLogger logs.
- `[ ]` Document guided migration from legacy mode once the migration flow is implemented.

Implemented files:

- `docs/Readme.md`
- `docs/User-Guide.de.md`
- `docs/User-Guide.en.md`

## 10. Target-System Verification Checklist

- `[x]` Install plugin on LoxBerry (2.0.0.15 on LoxBerry 4.0.0.13).
- `[x]` Confirm `preroot.sh` configures the Volkszaehler apt source.
- `[x]` Confirm LoxBerry installs or updates `vzlogger` through `dpkg/apt`.
- `[x]` Confirm `vzlogger --version`.
- `[x]` Confirm bridge service is installed automatically when vzLogger mode is applied.
- `[x]` Generate config from UI.
- `[x]` Validate config from UI.
- `[x]` Apply config from UI.
- `[x]` Confirm `systemctl status vzlogger`.
- `[x]` Confirm `systemctl status smartmeter-v2-vzlogger-bridge`.
- `[x]` Subscribe to generated MQTT topic and capture real messages.
- `[x]` Confirm `.data` cache updates from the real 2.0.0.17 `chnN/id`, `chnN/uuid`, and `chnN/raw` MQTT sequence using the current bridge parser logic.
- `[x]` Fix the 2.0.0.19 regression where `chnN/uuid` was received but stored under an empty channel name, so later `chnN/raw` values were ignored.
- `[x]` Diagnose 2.0.0.24 fresh-install target logs: package install and udev trigger succeed, `/dev/serial/smartmeter/A106Q3RX` is present, but `METER=0` generates an empty `meters` list and vzLogger exits after start.
- `[ ]` Confirm `.data` files are written below `/var/run/shm/<plugin>/` on the target LoxBerry, including calculated power values when counter channels are present.
- `[ ]` Confirm plugin HTTP endpoint returns cached values on the target LoxBerry.
- `[ ]` Confirm UDP messages reach all configured Miniservers.
- `[~]` Test disabling meter reading stops vzLogger and bridge.
- `[ ]` Test uninstall removes bridge service and UDEV rule.

## Recommended Next Implementation Steps

1. Test on a real LoxBerry target and create the debug log while vzLogger publishes MQTT messages.
2. Adjust `vzlogger_mqtt_bridge.pl` parser to the verified payload format from the debug log.
3. Add UI display for last cached values and direct bridge/vzLogger log links.
4. Add dynamic OBIS channel discovery using a temporary high-verbosity vzLogger run and cached per-reader results.
5. Verify custom OBIS identifiers and calculated power values on a real meter.
6. Verify the explicit legacy/vzLogger mode switch on a real LoxBerry target.
