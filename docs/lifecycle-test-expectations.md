# Plugin Lifecycle Test Expectations

This document defines expected behavior for SmartMeter v2 plugin lifecycle operations. It is intentionally independent from a specific implementation plan and applies to fresh installation, installation over an existing version, and uninstall behavior.

## Uninstall

Precondition:

- SmartMeter v2 is installed.

Expected:

- Uninstall completes successfully.
- All plugin-owned folders and files are removed.
- Plugin-owned services are stopped and removed.
- The `vzlogger` package installed for SmartMeter v2 is removed.
- The vzLogger apt source list configured by SmartMeter v2 is removed.

## Fresh Install

Precondition:

- No previous SmartMeter v2 plugin installation exists.

Expected:

- Installation completes successfully.
- The active implementation is `vzlogger`.
- Connected USB I/R heads are available below `/dev/serial/smartmeter/` before the first reboot.
- The MQTT bridge is disabled.
- All optional logs and debug logs are disabled.

## Install Over Existing Version

Precondition:

- A previous SmartMeter v2 plugin installation exists.

Expected:

- Installation completes successfully.
- The active implementation follows the previous configuration:
  - previous `vzlogger` remains `vzlogger`;
  - previous `legacy` remains `legacy`;
  - previous `none` remains `none`.

## Implementation Switching

Precondition:

- A generated and valid plugin-owned `vzlogger.conf` exists.

Expected:

- Activating Legacy stops vzLogger but does not overwrite the generated configuration.
- Deactivating either implementation without activating the other stops the corresponding runtime but does not regenerate `vzlogger.conf`.
- Reactivating vzLogger validates and applies the existing generated configuration without migrating the current Legacy meter settings.
- Legacy meter settings are migrated only when no valid generated vzLogger configuration exists.
- Saving while vzLogger is already active remains an explicit request to regenerate and apply its configuration.
