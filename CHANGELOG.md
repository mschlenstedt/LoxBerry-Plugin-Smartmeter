# Changelog

All notable user-visible changes should be documented in this file. Use the latest entry as the source for GitHub Release notes.

## Unreleased

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
