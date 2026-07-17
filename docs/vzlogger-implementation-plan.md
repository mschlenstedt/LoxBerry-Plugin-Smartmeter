# vzLogger Implementation Plan

This plan tracks the migration from the legacy SmartMeter reader to a vzLogger-based standard implementation. The target architecture is:

- `vzlogger` is installed as an external apt package, not bundled in this plugin.
- vzLogger reads the meters and publishes values natively via MQTT.
- The plugin configures vzLogger, maintains a local MQTT-derived cache, and serves HTTP/UDP from that cache.
- The legacy implementation remains available as a supported fallback and parallel configuration path. It must not be removed as part of this vzLogger migration.

## Current Review Summary (2026-07-17)

The implementation has moved well beyond the original MVP plan. The core architecture, configuration generation and validation, MQTT bridge, service integration, dynamic OBIS discovery, implementation switching, migration behavior, and the expanded SML/D0/OMS/custom-meter UI are implemented. A complete upgrade, disable/reactivate, uninstall, fresh-install, real SML, cache, HTTP, calculated-power, and UDP test was completed with 2.0.0.32 on LoxBerry 4.0.0.13 (Debian 13/trixie, arm64). The follow-up SML-template and AJAX-lifecycle defects found during that test have also been corrected and retested. The remaining work is compatibility coverage rather than missing core functionality.

The HTTP-cache panel intentionally remains a compact status view. It shows cache availability and the last update, while the cache endpoint itself exposes the values; an additional inline value table is not required.

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
- `[x]` Verify `preroot.sh` repository setup as root on the confirmed target platform: LoxBerry 4.0.0.13, Debian 13/trixie, arm64. Broader platform coverage is intentionally not claimed and remains a compatibility limitation in `KNOWN-ISSUES.md`.
- `[x]` Define the currently confirmed OS/architecture support boundary as Debian 13/trixie on arm64. Other Debian/Raspberry Pi OS codenames and architectures require their own installation evidence before being added to the supported matrix.

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
- `[x]` Map the standard SML and D0 serial settings to vzLogger fields and provide protocol-specific SML, D0, and OMS configuration. Unsupported meter-specific legacy sequences are identified in the shared template catalog instead of being silently mapped.
- `[x]` Map an SML template's operating/read baud rate to vzLogger's `baudrate` field, while D0 continues to map initial and read baud rates separately. The corrected Generic SML catalog default is 9600 baud/8N1. A repeated target test with the connected ISK meter discovered `1-0:1.8.0`, `1-0:2.8.0`, and `1-0:16.7.0`. A separate 9600/7E1 comparison saw identifiers in one short raw run, but the regular discovery found no channels and sustained reading stopped after one value; 8N1 is therefore the verified Generic SML parity default for this hardware. Broader hardware-dependent template coverage remains tracked in `KNOWN-ISSUES.md`.
- `[x]` Make OBIS channels configurable in the UI, including custom meter-specific OBIS identifiers.
- `[x]` Add dynamic OBIS channel discovery through a temporary, time-bounded high-verbosity vzLogger run; cache results per reader, preserve selections, support cancellation/background status, and restore the regular service afterwards.
- `[x]` Add a reversible migration path from existing Legacy configuration. Existing valid generated vzLogger configuration is preserved and reused; Legacy/form values are migrated only when no valid generated configuration exists, and isolated `LEGACY_*` settings remain available when switching back.
- `[x]` Add OMS and custom JSONC meter configurations in addition to the original SML/D0 scope.
- `[x]` Use one shared meter-template catalog for Legacy and vzLogger initialization.

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
- `[x]` Evaluate native validation through the installed `vzlogger` binary and retain structural plugin validation. Current vzLogger releases provide no separate check/validate/dry-run option; foreground execution starts the configured meters and is therefore not a safe, non-invasive validation step.
- `[x]` Add repository CI and the Windows `tools/check-perl-syntax.ps1` helper using LoxBerry stubs. The vzLogger generator, validator, control, bridge, and main CGI pass the helper as of this review; target-LoxBerry runtime behavior remains covered by the target checklist.

Decision notes:

- The [official vzLogger CLI documentation](https://wiki.volkszaehler.org/software/controller/vzlogger#kommandozeilenparameter) and the current Debian man page list no `--check`, `--validate`, or `--dry-run` option, so validation remains structural.
- This still prevents starting services with malformed JSON or incomplete required plugin-generated structures.
- The documented native CLI provides configuration selection and foreground execution, but foreground execution opens devices and starts meter processing. Native preflight validation should only be reconsidered if upstream adds a dedicated side-effect-free command.

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
- `[x]` Add HTTP-cache visibility to the web UI with cache presence, last update, and a direct cache endpoint link.

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
- `[x]` Resolve bridge installation behavior: keep the bridge disabled on fresh installs, but install/refresh its systemd unit automatically when an enabled bridge is applied or started. No separate install button is required.

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
- `[x]` Add LoxBerry-style layout polish, implementation tabs and state badges, grouped/collapsible service and configuration panels, compact controls, contextual help, and AJAX progress overlays.
- `[x]` Add log links for vzLogger and bridge plus a read-only, password-masked generated-config viewer beside the displayed path.
- `[x]` Keep the HTTP-cache panel without an inline last-cached-values table; status, timestamp, and the cache endpoint provide the intended diagnostic access.
- `[x]` Add explicit OBIS channel selection and custom OBIS entry.
- `[x]` Add structured per-reader vzLogger live-data rendering and a masked, read-only generated-configuration viewer.
- `[x]` Add AJAX service control, validation, Save/Apply, reader scan, OBIS discovery, and debug-log workflows without page reloads.

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
- `[x]` `start`/`restart` service actions: use and validate the current generated config without regeneration, apply only the requested service activation plus its log controls, require MQTT in both saved and generated configuration before starting the bridge, and leave every other unsaved form value untouched; vzLogger updates only the root log settings in `vzlogger.conf`.
- `[x]` `status`: report package, apt source, config, validation, vzLogger service, bridge service/process.
- `[x]` `debug-log`: create a diagnostic log for troubleshooting and MQTT parser verification.
- `[x]` Start vzLogger directly with the generated plugin config through a SmartMeter-managed systemd drop-in.
- `[x]` Preserve unrelated `/etc/vzlogger.conf` files and remove the plugin drop-in on Legacy switch or uninstall.
- `[x]` Exercise control, validation, apply, service, discovery, and diagnostic actions through the web UI as the LoxBerry user during target testing; explicitly provide the LoxBerry Perl environment in the bridge unit.
- `[x]` Make AJAX lifecycle feedback reflect the requested final service state. Reset vzLogger's failed state before disabling the generated unit, close a failed OBIS-discovery overlay before displaying its alert, and remove saved meter, template, and OBIS pending markers immediately after a successful AJAX apply. Target retesting confirmed successful disable feedback, both services inactive with the drop-in removed, a closed failed-discovery overlay, and all three pending marker types disappearing without a page reload.

Target finding (2.0.0.15): the bridge unit lacked LoxBerry's Perl library environment and exited with status 2 because `LoxBerry::System` was not in `@INC`. The unit template now sets `LBHOMEDIR` and `PERL5LIB` explicitly.

Decision notes:

- Current apply behavior installs a systemd drop-in that runs vzLogger in the foreground with the generated plugin config path.
- If installing the drop-in fails, the control script does not restart vzLogger with a different or stale configuration.
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
- `[x]` Restore the configured legacy cron mode during upgrade and when Legacy is applied; remove all legacy polling cron entries for vzLogger or an inactive Legacy reader.
- `[x]` Disable legacy cron automatically when vzLogger mode is enabled, and stop vzLogger/bridge when legacy mode is selected.
- `[x]` Define and implement cleanup ownership: preserve generated vzLogger configuration while switching modes; remove per-meter mappings, JSONC/discovery/test/log/runtime artifacts when a meter is removed; remove the runtime cache, plugin-owned units/drop-in, owned system config, udev rule, apt source/key, and plugin-introduced vzLogger package during uninstall.
- `[x]` Verify complete uninstall cleanup on a disposable LoxBerry 4 target: plugin directories and runtime cache, bridge unit, vzLogger drop-in, UDEV rule, apt source/keyring, ownership marker, plugin-introduced vzLogger package, and old cron/system links were removed before a successful fresh install.

Decision notes:

- Legacy behavior is preserved as a supported mode; migration to vzLogger should be explicit and reversible.
- The SmartMeter systemd drop-in is removed on Legacy switch and uninstall. Older generated `/etc/vzlogger.conf` copies are removed only when `/etc/vzlogger.conf.smartmeter-v2` marks them as SmartMeter-generated.
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
- `[x]` Document reversible Legacy/vzLogger switching, generated-config preservation, conditional migration, and isolated Legacy settings.

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
- `[x]` Confirm `.data` files are written below `/var/run/shm/<plugin>/` from real retained `chnN` MQTT messages on the target LoxBerry.
- `[x]` Confirm calculated consumption and delivery power values from counter deltas with a real meter and realistic update intervals. Real non-zero values matched `delta Wh / delta hours` at three-decimal precision; for example, a 2 Wh delivery delta over 5 seconds produced 1440.000 W. An unchanged counter produced 0 W.
- `[x]` Confirm plugin HTTP endpoint returns the current cached values and timestamp on the target LoxBerry and terminates the response with `#EOF`; verified locally and through Chrome.
- `[x]` Confirm UDP messages reach the configured Miniserver. The bridge logged repeated sends to `HOME_SWEET_HOME` at `192.168.1.5:7000`, and reception with matching current values was confirmed in the Loxone UDP Monitor.
- `[x]` Test disabling meter reading stops vzLogger and bridge. Both services became inactive, the plugin drop-in was removed, no legacy polling job was active, and the generated `vzlogger.conf` hash remained unchanged. Follow-up testing also confirmed that AJAX reports this state as successful.
- `[x]` Test uninstall removes bridge service and UDEV rule, together with the complete plugin-owned cleanup set documented in section 8.

### 2.0.0.32 Target Evidence (2026-07-17)

- Package: locally built `Smartmeter-V2.0.0.32-local.zip`, SHA-256 `29DDEF476313B41236D5C25095ABA58C8ED79626FBDF73F89758559719AB3949`; package layout and Perl, PHP, and shell syntax checks passed before installation.
- Platform: LoxBerry 4.0.0.13, Debian 13/trixie, arm64; vzLogger 0.8.9 installed from the configured Cloudsmith source.
- Lifecycle: coherent upgrade to 2.0.0.32, disable/reactivate, complete uninstall without backup, and fresh install all passed. The reader symlink `/dev/serial/smartmeter/A106Q3RX` was recreated without reboot; a fresh unconfigured installation left both services stopped.
- Runtime: the manually corrected 9600/8N1 SML configuration produced the three selected real OBIS channels through MQTT. Both services were active and enabled, and only the bridge path updated `/var/run/shm/smartmeter-v2/A106Q3RX.data`.
- Outputs: calculated power, HTTP output, repeated UDP sends, and actual Miniserver reception passed. The final test state intentionally leaves vzLogger, the bridge, and UDP enabled.
- Evidence directory: `dist/test-evidence-20260717-131624/` (ignored build/test artifact, not part of the release package).

### 2.0.0.32 Follow-Up Fix Evidence (2026-07-17)

- Package: locally built `Smartmeter-V2.0.0.32-fixes-final.zip`, SHA-256 `313A733C6FA8B91FA5B528F526769EC8D33DC7B5E8B7BE37F9C82C5E58CE4735`.
- Installation: the complete package flow and root hooks passed again at 15:22. After the isolated parity comparison changed only the Generic SML catalog/default and documentation back to 8N1, the final catalog file was synchronized directly to the installed plugin to avoid a third identical apt dependency reinstall; its deployed content and the final package content match.
- SML: Generic SML now initializes 9600 baud/8N1. Discovery with the connected ISK meter found all three real OBIS channels and sustained data/UDP updates. The isolated 9600/7E1 comparison was rejected as a default because it failed regular discovery and did not sustain the data stream.
- AJAX lifecycle: a failed discovery closed its progress overlay before the error alert; disabling vzLogger and the bridge completed without false failure feedback and left both services inactive with the drop-in absent.
- AJAX saved state: meter `Neu / ungespeichert`, template `Änderung noch nicht gespeichert`, and three OBIS `Neu` markers were present before apply and all disappeared when the AJAX apply completed, without reloading the page. Their pending files were removed as part of the save.
- Final state: vzLogger and the bridge were re-enabled and are active/enabled with the SmartMeter drop-in restored.

## Completion Status

All implementation checklist items in this plan are complete. Platform-matrix and representative-meter coverage are compatibility limitations rather than concrete implementation tasks and are tracked in `KNOWN-ISSUES.md`.
