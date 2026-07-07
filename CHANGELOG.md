# Changelog

All notable user-visible changes should be documented in this file. Use the latest entry as the source for GitHub Release notes.

## Unreleased

### Added

- Added vzLogger debug logging and a diagnostic log action for service status, generated config, channel mapping, bridge logs, cache files, and MQTT parser evidence.

### Changed

- Moved the new vzLogger configuration page text into German and English language files.
- Updated German and English user guides with the vzLogger workflow while keeping the legacy implementation documented.

### Fixed

- Nothing yet.

### Upgrade Notes

- Nothing yet.

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
