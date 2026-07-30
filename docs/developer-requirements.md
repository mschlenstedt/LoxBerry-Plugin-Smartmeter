# Developer Requirements

This document records the product and engineering contracts that must remain true when Smartmeter-NG is changed. It consolidates decisions from the user guides, lifecycle tests, review findings, and project discussions. Detailed procedures remain in the linked specialist documents.

## Using Project History

- This file describes the current accepted target behavior, not every behavior that existed during the migration.
- Treat `CHANGELOG.md`, older commits, target evidence, and completed implementation-plan steps as historical context. Do not turn an old MVP limitation, temporary workaround, retired file path, or version-specific observation into a current requirement.
- Before adding or changing a requirement, compare the latest accepted behavior in the current user guides, executable tests, `KNOWN-ISSUES.md`, recent commits, and the `Unreleased` changelog. Resolve contradictions explicitly and update or remove superseded documentation.
- Historical evidence may justify a current rule, but the rule must be stated independently of the old version, date, test device, or implementation accident.

## 1. Product Architecture

- vzLogger is the only meter implementation. It may be inactive; the former Legacy Perl reader was removed and is only maintained in the `Version1` branch.
- vzLogger is installed from the Volkszaehler apt repository by `bin/vzlogger_pkg.sh`, not through the LoxBerry `dpkg/apt` list. Only the `vzlogger` package is installed; the plugin must not bundle it or pull in other Volkszaehler components.
- vzLogger reads the meters and publishes MQTT itself. The plugin owns the configuration and the process lifecycle but never reads serial devices directly.
- vzLogger runs in the foreground (`vzlogger -f`) as the `loxberry` user, supervised by `bin/watchdog.pl`, not by systemd. The packaged systemd unit is disabled and masked.
- Activation changes take effect only after an explicit save/apply.
- The existing LoxBerry plugin identity fields (`AUTHOR`, `PLUGIN.NAME`, and `PLUGIN.FOLDER`) are stable update identifiers and must not change.

## 2. Compatibility And Mode Switching

- The plugin is unreleased, so there are no existing installations. No migration path or backward compatibility for old configuration formats, keys, or file layouts is required; ship the current format directly.
- A valid generated `vzlogger.conf` must survive a fully inactive state, upgrades, and later vzLogger reactivation.
- Ordinary read-only page loads must not rewrite configuration files or services.
- Meter or channel removal is staged in the browser and becomes persistent only on Save/Apply. Applying a meter removal also removes its runtime artifacts.


## 3. Save, Apply, And Service Safety

- Every mutating CGI, CLI, service, and lifecycle action uses the same non-blocking exclusive configuration lock. Status and other read-only actions stay lock-free.
- Generated runtime artifacts are created in a protected staging directory on the same filesystem, validated as one coherent set, and then promoted atomically with backups. Any promotion failure must roll back the complete set and preserve the last valid runtime configuration.
- Submitted user settings may remain saved after a failed Apply so they can be corrected; invalid generated runtime files must never replace the active valid set.
- Validate Config is non-mutating: it uses a temporary draft and must not change saved settings, generated files, custom meter sources, cron, or services.
- Apply succeeds only when generation, validation, promotion, and every requested final service state succeed. Failures propagate to CGI/CLI callers as non-zero results.
- Start and Restart validate the existing generated configuration and change only the requested service activation and its dedicated log settings. They must not save unrelated form fields. Stop remains available for a running service even when configuration is invalid.
- Service controls and lifecycle hooks must report the observed final service state, not only a successful command invocation.

## 5. Meter And Channel Model

- The neutral meter-template catalog holds meter models and serial defaults once. SML uses the operating/reading baud rate.
- The standard editor supports SML, D0, and OMS. Protocol-specific fields must not leak into generated objects for another protocol. Unsupported behavior must be reported rather than silently approximated.
- Active vzLogger mode requires at least one active meter. A meter without channels may remain valid for discovery with a warning; a configuration without meters is valid only as a disabled state and must stop vzLogger.
- OBIS discovery uses the reader's current browser settings, runs independently of the page request, survives navigation/reload, supports cancellation, and restores the regular vzLogger service afterwards. Discovered identifiers remain available for user selection; a restoration warning must not discard successful discovery results.
- Custom JSONC represents exactly one complete vzLogger meter object, is limited to 64 KiB, and is preserved textually including comments and formatting. Generation may supply missing channel UUID/API values internally but must not rewrite the source JSONC.
- `vzlogger_channel_definitions.json` is the authoritative UI model for active and inactive channel definitions. `vzlogger_channels.json` contains only active plugin outputs used by the live view.
- Custom-channel identity is maintained by the versioned `vzlogger_user_channel_uuids_<serial>.json` registry. Explicit UUIDs always win. Otherwise a canonical SHA-256 channel fingerprint maps to an ordered UUID list so identical duplicates and channel reordering remain stable. Content changes may create a new UUID; only an explicit UUID guarantees identity across such changes.
- Manual duplicate OBIS channels are valid when they have distinct UUIDs. Discovered channels are normally deactivated instead of deleted so later discovery can find them again.
- SML/D0 storage index `*F` accepts `0..254`. Empty, `null`, and `255` mean unspecified and are not emitted as a redundant `*255`; OMS does not support this field.
- Channel aggregation is a temporal setting and is available only when the meter has `aggtime > 0`. Retained settings for an inactive API are neither validated nor generated.
- Output keys are unique per reader, case-insensitively, and become the channel's MQTT topic segment. Existing keys must not be renamed automatically or supplemented with compatibility aliases. Keys are 1–64 characters and accept letters, digits, spaces, and `_ | ( ) [ ] / ' % $ ! . * -`; `#` and `+` are rejected as MQTT wildcards, and `/` is a topic separator.

## 6. MQTT Output

- vzLogger publishes MQTT itself. The plugin writes the channel's output key as its `mqtt_topic`, so a value is published at `<base-topic>/<reader>/<output key>/raw`; without a plugin output key the channel falls back to its OBIS name.
- vzLogger additionally publishes `/uuid` and `/id` (the OBIS identifier) once per channel as retained messages, and `/agg` when aggregation is enabled. The base topic carries no extra path segment because channels supply their own.
- The payload is the plain meter value, or `{"timestamp":<ms>,"value":<number>}` when timestamps are enabled. Values are the raw meter readings; the plugin does not scale them, so SML energy counters are published in Wh.
- Delivery to the Miniserver is handled by the LoxBerry MQTT Gateway. The plugin does not send UDP and does not serve an HTTP cache.
- MQTT passwords, private-key passwords, tokens, and similar secrets must never appear in rendered HTML, unmasked diagnostics, process listings, or logs.

## 7. Expert Mode

- Expert Mode edits a separate persistent `vzlogger_expert.conf` draft. Enabling or disabling the mode must not silently overwrite either the draft or active `vzlogger.conf`.
- While Expert Mode is active, standard vzLogger configuration fields are read-only. Service activation and log settings remain independently editable.
- Invalid expert input remains available for correction while the last valid runtime configuration stays active. Unknown upstream extension fields produce warnings and are preserved.
- Reinitializing the expert draft from the current `vzlogger.conf` is explicit, confirmed, and visible only while Expert Mode is active.
- Expert mappings are retained by known UUID. Unknown UUIDs are reported.

## 8. Security And File Ownership

- Do not create additional Linux users or groups. vzLogger runs as the existing `loxberry` user, so the packaged `_vzlogger` user is not used by the plugin.
- Runtime directories use `loxberry:loxberry 0750`; runtime files use at most `0640`.
- Mapping, definitions, UUID sidecars, custom JSON/JSONC, and the generated `vzlogger.conf` are owned by `loxberry:loxberry`, at most `0640`.
- Serial devices use the udev rule `ttyUSB[0-9]* GROUP=loxberry MODE=0660`. Plugin scripts use a restrictive `umask` (`0027`).
- Never reintroduce `0777`/`0666` fallbacks. Install and upgrade hooks repair required ownership and modes idempotently.

## 9. Lifecycle And Ownership Boundaries

- Fresh installation defaults to an inactive implementation. `postroot.sh` installs vzlogger through the package helper, then starts it through the watchdog only when vzLogger mode is active and a meter is configured.
- `bin/vzlogger_pkg.sh` installs only the `vzlogger` package, keeps the packaged service from starting during installation (`policy-rc.d`), and disables and masks it afterwards. This is reapplied after every package update because the package postinst re-enables and unmasks the unit. The repository key is rewritten on every run.
- vzLogger reads the plugin-owned `vzlogger.conf` via the watchdog's `-c` argument. Never overwrite an unrelated `/etc/vzlogger.conf`.
- Uninstall stops vzLogger through the watchdog, removes runtime/cache artifacts, udev rules, and the apt source/key, and purges the `vzlogger` package only when an ownership marker proves the plugin introduced it.
- Broader platform or meter support must not be claimed without matching target-system or representative-hardware evidence. Current limits remain in `KNOWN-ISSUES.md`.

## 10. UI, Localization, And Accessibility

- Desktop and mobile browsers provide the same functions and information. Follow the responsive viewport and acceptance requirements in `AGENTS.md` and `docs/test-device-workflow.md`.
- German and English UI phrases, templates, validation messages, and user documentation must remain synchronized. Exercise the longer German labels during responsive testing.
- Current plugin UI translations live only in LoxBerry's native `templates/lang/language_de.ini` and `language_en.ini` resources, separated into shared and vzLogger namespaces. Do not restore duplicate `language.txt` trees or custom language loaders.
- Localize only plugin-authored text written for users in the browser, including the explanatory part of browser validation and action messages. Do not localize established technical terms, product or project names, protocol and format identifiers, commands, paths, configuration keys, API values, service states, or comparable machine-relevant identifiers.
- Keep technical CLI output, logs, and unmodified diagnostics from the operating system or external programs in English. This keeps operation, troubleshooting, and automated evaluation language-independent; a localized UI may add a translated explanation without rewriting the technical detail.
- Disabled controls preserve their values and visually disable the associated label/help region. Unsaved state must be visible where activation, meter, template, or channel state has changed.
- AJAX workflows must preserve page context and expanded panels, show progress, distinguish success/warning/failure, and avoid saving unrelated settings.
- Never expose an unmasked generated configuration or expert editor outside the authenticated frontend.

## 11. Verification And Documentation

- Regression tests belong under `tests/`, must be deterministic and reusable, and should test shared modules without requiring a live MQTT broker or production filesystem where possible.
- Run the repository Perl/PHP/shell checks appropriate to changed files. Installed behavior must additionally be deployed and verified on the disposable LoxBerry according to `docs/test-device-workflow.md`.
- UI changes require authenticated desktop and mobile browser checks on the vzLogger page. Lifecycle changes require validation against a real install log.
- Preserve remote configuration and service state during tests. Verify checksums around failed, concurrent, or read-only actions.
- Update both user guides and `CHANGELOG.md` when behavior, configuration, dependencies, compatibility, or upgrade steps change. Record confirmed limitations in `KNOWN-ISSUES.md` rather than presenting them as supported.
- Local packages and official releases follow `docs/local-builds.md` and `docs/release-process.md`; suffixless release archives are produced only by the GitHub release workflow.

## Detailed References

- User-visible behavior: `docs/User-Guide.de.md` and `docs/User-Guide.en.md`
- Installed-device and browser verification: `docs/test-device-workflow.md`
- Lifecycle acceptance: `docs/lifecycle-test-expectations.md`
- Compatibility evidence and limitations: `KNOWN-ISSUES.md`
- Release procedure: `docs/release-process.md`
