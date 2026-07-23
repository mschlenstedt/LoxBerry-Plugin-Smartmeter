# Plugin Lifecycle Test Expectations

This document defines expected behavior for Smartmeter-NG plugin lifecycle operations. It is intentionally independent from a specific implementation plan and applies to fresh installation, installation over an existing version, and uninstall behavior.

## Uninstall

Precondition:

- Smartmeter-NG is installed.

Expected:

- Uninstall completes successfully.
- All plugin-owned folders and files are removed.
- Plugin-owned services are stopped and removed.
- The `vzlogger` package installed for Smartmeter-NG is removed.
- The vzLogger apt source list configured by Smartmeter-NG is removed.

## Fresh Install

Precondition:

- No previous Smartmeter-NG plugin installation exists.

Expected:

- Installation completes successfully.
- The active implementation is `vzlogger`.
- Connected USB I/R heads are available below `/dev/serial/smartmeter/` before the first reboot.
- The MQTT bridge is disabled.
- All optional logs and debug logs are disabled.

## Install Over Existing Version

Precondition:

- A previous Smartmeter-NG plugin installation exists.

Expected:

- Installation completes successfully.
- The active implementation follows the previous configuration:
  - previous `vzlogger` remains `vzlogger`;
  - previous `none` remains `none`.

## Implementation Switching

Precondition:

- A generated and valid plugin-owned `vzlogger.conf` exists.

Expected:

- Deactivating either implementation without activating the other stops the corresponding runtime but does not regenerate `vzlogger.conf`.
- Saving while vzLogger is already active remains an explicit request to regenerate and apply its configuration.
- Concurrent configuration or service actions are rejected without partial writes.
- Failed generation, validation, promotion, override installation, or service restart returns a non-zero control result and preserves the last valid generated runtime files.
- Runtime, log, generated configuration, and serial-device permissions use only the existing `loxberry` and `_vzlogger` identities and do not require world-writable modes.
