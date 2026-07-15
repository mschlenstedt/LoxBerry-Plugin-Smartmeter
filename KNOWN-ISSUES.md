# Known Issues

This document tracks confirmed limitations and follow-up items that are not tied to one specific release process step or implementation plan.

## Uninstall Leaves Runtime Cache Until Reboot

Observed on:

- LoxBerry test device `loxberry-test`
- Check time: 2026-07-11 12:13 +02:00
- Tested after uninstalling SmartMeter v2 `2.0.0.20`

Expected:

- All plugin-owned runtime files are removed during uninstall.

Observed:

- The plugin-owned runtime directory remained after uninstall:

```text
/var/run/shm/smartmeter-v2/
  A106Q3RX.data
  A106Q3RX.lastdel
  A106Q3RX.lastcons
```

Impact:

- These files are stale runtime cache files.
- They should disappear after a reboot because `/var/run/shm` is temporary runtime storage.
- A reboot should not be required for uninstall cleanup, so uninstall should remove this directory explicitly.

Follow-up:

- Update the uninstall hook to remove `/var/run/shm/<plugin-folder>` when it belongs to SmartMeter v2.

## Uninstall Removes vzLogger Package But Leaves dpkg Config State

Observed on:

- LoxBerry test device `loxberry-test`
- Check time: 2026-07-11 12:13 +02:00
- Tested after uninstalling SmartMeter v2 `2.0.0.20`

Expected:

- The vzLogger package installed for SmartMeter v2 is fully removed when it was marked as plugin-managed.

Observed:

- `vzlogger` was removed as an executable package, but dpkg still reported:

```text
vzlogger deinstall ok config-files 0.8.9
```

- Remaining package configuration files included:

```text
/etc/init.d/vzlogger
/etc/logrotate.d/vzlogger
```

Impact:

- The `vzlogger` binary is no longer available and the service is inactive.
- The system still has dpkg conffile state for `vzlogger`.
- A reboot does not remove this state.

Follow-up:

- If SmartMeter v2 installed `vzlogger`, uninstall should use package purge semantics instead of remove-only semantics.
- Keep the existing ownership guard so a user-installed `vzlogger` package is not purged by the plugin.

## vzLogger Target-System Validation Is Not Complete

Source:

- `docs/vzlogger-implementation-plan.md`

Expected:

- The vzLogger implementation is validated on target LoxBerry systems for repository setup, architecture support, permissions, service behavior, data flow, and meter presets.

Known gaps:

- `preroot.sh` repository setup still needs root-level validation on the supported target LoxBerry versions.
- Supported Debian/Raspberry Pi OS codenames and architecture behavior still need confirmation.
- Legacy meter presets still need verification against actual vzLogger options.
- Generated configuration validation against a real installed `vzlogger` binary still depends on identifying a reliable dry-run or check option.
- Perl syntax checks still need to run directly on LoxBerry.
- Permission behavior for web UI actions running as the LoxBerry user still needs target-system verification.
- Disabling meter reading has only partial verification for stopping vzLogger and the bridge.
- Custom OBIS identifiers and calculated power values still need verification with a real meter.
- The explicit Legacy/vzLogger mode switch still needs target-system verification.

Impact:

- Some behavior is implemented and locally linted, but not yet fully proven on every intended target environment.
- Release candidates that touch install hooks, permissions, services, meter presets, or data flow should be tested on a real LoxBerry before publication.

Follow-up:

- Keep the detailed work items in `docs/vzlogger-implementation-plan.md`.
- Record confirmed target-system findings here only when they represent a user-visible limitation, operational risk, or release-relevant validation gap.

## vzLogger Configuration UX Is Still Incomplete

Source:

- `docs/vzlogger-implementation-plan.md`

Expected:

- Users can configure supported meters with minimal manual mapping and can inspect the latest cached values directly in the plugin UI.

Known gaps:

- Serial and D0 settings are only partially mapped from legacy fields.
- Dynamic OBIS channel discovery now exists for direct legacy meter reads; target-system validation with real meters is still pending.
- Guided migration from an existing legacy configuration to vzLogger configuration is not implemented yet.
- The UI does not yet provide a full table of last cached values.
- Documentation for guided migration is pending until the migration flow exists.

Impact:

- Existing legacy setups may still require manual review when moving to vzLogger.
- Users may need to inspect cache files, logs, or debug output instead of relying entirely on the UI.

Follow-up:

- Use `docs/vzlogger-implementation-plan.md` as the implementation backlog.
- Update this document when any gap becomes a confirmed runtime issue or is resolved.

## vzLogger Config Ownership And Cleanup Policy Is Not Final

Source:

- `docs/vzlogger-implementation-plan.md`

Expected:

- Generated vzLogger configuration, channel mapping, and runtime cache files have a clear ownership and cleanup policy.

Known gaps:

- The plugin starts vzLogger directly with the generated configuration below the plugin config directory through a SmartMeter-managed systemd drop-in.
- Cleanup policy for generated `vzlogger.conf`, `vzlogger_channels.json`, and runtime cache files is not fully defined.

Impact:

- SmartMeter-generated files can be cleaned up safely only where ownership is clear.
- This overlaps with the uninstall runtime-cache and dpkg-config-state findings above.

Follow-up:

- Define ownership markers and cleanup rules before changing uninstall behavior further.
- Keep user-installed or externally managed vzLogger configuration protected from plugin cleanup.
