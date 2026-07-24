# Developer Requirements

This document records the product and engineering contracts that must remain true when Smartmeter-NG is changed. It consolidates decisions from the vzLogger migration plan, user guides, lifecycle tests, review findings, and project discussions. Detailed procedures remain in the linked specialist documents.

## Using Project History

- This file describes the current accepted target behavior, not every behavior that existed during the migration.
- Treat `CHANGELOG.md`, older commits, target evidence, and completed implementation-plan steps as historical context. Do not turn an old MVP limitation, temporary workaround, retired file path, or version-specific observation into a current requirement.
- Before adding or changing a requirement, compare the latest accepted behavior in the current user guides, executable tests, `KNOWN-ISSUES.md`, recent commits, and the `Unreleased` changelog. Resolve contradictions explicitly and update or remove superseded documentation.
- Historical evidence may justify a current rule, but the rule must be stated independently of the old version, date, test device, or implementation accident.

## 1. Product Architecture

- vzLogger is the standard implementation and is installed as an external apt package; it must not be bundled with the plugin.
- vzLogger reads meters and publishes MQTT. The SmartMeter bridge consumes MQTT and provides the plugin HTTP cache and optional UDP output. The bridge must not read serial devices directly.
- vzLogger is the only meter implementation. It may be inactive; the former Legacy Perl reader was removed and is only maintained in the `Version1` branch.
- Activation changes take effect only after an explicit save/apply.
- The existing LoxBerry plugin identity fields (`AUTHOR`, `PLUGIN.NAME`, and `PLUGIN.FOLDER`) are stable update identifiers and must not change.

## 2. Compatibility And Mode Switching

- Existing `smartmeter.json`, MQTT topic structure, HTTP-cache keys, UDP value names, custom JSONC files, and generated-config locations are compatibility contracts. Change them only with an explicit migration and documented upgrade path.
- A valid generated `vzlogger.conf` must survive a fully inactive state, upgrades, and later vzLogger reactivation.
- Ordinary read-only page loads must not rewrite configuration files or services.
- Meter or channel removal is staged in the browser and becomes persistent only on Save/Apply. Applying a meter removal also removes its runtime artifacts.


## 3. Save, Apply, And Service Safety

- Every mutating CGI, CLI, service, and lifecycle action uses the same non-blocking exclusive configuration lock. Status and other read-only actions stay lock-free.
- Generated runtime artifacts are created in a protected staging directory on the same filesystem, validated as one coherent set, and then promoted atomically with backups. Any promotion failure must roll back the complete set and preserve the last valid runtime configuration.
- Submitted user settings may remain saved after a failed Apply so they can be corrected; invalid generated runtime files must never replace the active valid set.
- Validate Config is non-mutating: it uses a temporary draft and must not change saved settings, generated files, custom meter sources, cron, or services.
- Apply succeeds only when generation, validation, promotion, service override handling, and every requested final service state succeed. Failures propagate to CGI/CLI callers as non-zero results.
- Start and Restart validate the existing generated configuration and change only the requested service activation and its dedicated log settings. They must not save unrelated form fields. Stop remains available for a running service even when configuration is invalid.
- Service controls and lifecycle hooks must report the observed final service state, not only a successful command invocation.

## 5. Meter And Channel Model

- The neutral meter-template catalog holds meter models and serial defaults once. SML uses the operating/reading baud rate.
- The standard editor supports SML, D0, and OMS. Protocol-specific fields must not leak into generated objects for another protocol. Unsupported behavior must be reported rather than silently approximated.
- Active vzLogger mode requires at least one active meter. A meter without channels may remain valid for discovery with a warning; a configuration without meters is valid only as a disabled state and must stop vzLogger/bridge and remove the plugin override.
- OBIS discovery uses the reader's current browser settings, runs independently of the page request, survives navigation/reload, supports cancellation, and restores the regular vzLogger service afterwards. Discovered identifiers remain available for user selection; a restoration warning must not discard successful discovery results.
- Custom JSONC represents exactly one complete vzLogger meter object, is limited to 64 KiB, and is preserved textually including comments and formatting. Generation may supply missing channel UUID/API values internally but must not rewrite the source JSONC.
- `vzlogger_channel_definitions.json` is the authoritative UI model for active and inactive channel definitions. `vzlogger_channels.json` contains only active plugin outputs used by the bridge.
- Custom-channel identity is maintained by the versioned `vzlogger_user_channel_uuids_<serial>.json` registry. Explicit UUIDs always win. Otherwise a canonical SHA-256 channel fingerprint maps to an ordered UUID list so identical duplicates and channel reordering remain stable. Content changes may create a new UUID; only an explicit UUID guarantees identity across such changes.
- Manual duplicate OBIS channels are valid when they have distinct UUIDs. Discovered channels are normally deactivated instead of deleted so later discovery can find them again.
- SML/D0 storage index `*F` accepts `0..254`. Empty, `null`, and `255` mean unspecified and are not emitted as a redundant `*255`; OMS does not support this field.
- Channel aggregation is a temporal setting and is available only when the meter has `aggtime > 0`. Retained settings for an inactive API are neither validated nor generated.
- Output keys are unique per reader, case-insensitively, and are the only HTTP-cache/UDP names emitted for that channel. Existing keys must not be renamed automatically or supplemented with compatibility aliases. Keys are 1–64 characters and accept letters, digits, spaces, and `_ # | ( ) [ ] / ' % $ ! . * -`; `:` and `;` remain reserved delimiters.

## 6. MQTT, Cache, HTTP, And UDP

- vzLogger publishes below `<base-topic>/vzlogger`; the bridge subscribes to `<base-topic>/vzlogger/#`.
- Bridge mapping resolves UUID/`chnN` first. Identifier fallback is allowed only when it is unambiguous. Scaling and calculated-power recognition use structured OBIS identifiers, not display or output names.
- Cache and UDP output start with `Last_Update` and `Last_UpdateLoxEpoche`, followed by configured outputs in ascending `chnN` order and then unmapped values alphabetically. HTTP and UDP expose the same ordered value set.
- Electrical SML energy counters are displayed in kWh when vzLogger supplies Wh. Calculated consumption/delivery power continues to use counter deltas when the meter provides no instantaneous power channel.
- The bridge update cycle controls cache writes and UDP sends. Avoid writing cache files for every MQTT message.
- The web UI intentionally shows cache availability, last update, and a link to the cache endpoint. It does not need to duplicate the complete cached value list inline.
- MQTT passwords, private-key passwords, tokens, and similar secrets must never appear in rendered HTML, unmasked diagnostics, process listings, or logs.
- The bridge remains optional and disabled on a fresh installation. vzLogger can run independently when the bridge is disabled.

## 7. Expert Mode

- Expert Mode edits a separate persistent `vzlogger_expert.conf` draft. Enabling or disabling the mode must not silently overwrite either the draft or active `vzlogger.conf`.
- While Expert Mode is active, standard vzLogger configuration fields are read-only. Bridge controls and service logging remain independently editable.
- Invalid expert input remains available for correction while the last valid runtime configuration stays active. Unknown upstream extension fields produce warnings and are preserved.
- Reinitializing the expert draft from the current `vzlogger.conf` is explicit, confirmed, and visible only while Expert Mode is active.
- Expert mappings are retained by known UUID. Unknown UUIDs are reported and are not automatically published by the bridge.

## 8. Security And File Ownership

- Do not create additional Linux users or groups. Use the existing `loxberry` user, `_vzlogger` user, and `loxberry` group.
- Runtime directories use `loxberry:loxberry 0750`; runtime files use at most `0640`.
- Mapping, definitions, UUID sidecars, and custom JSON/JSONC use `loxberry:loxberry 0600`.
- `vzlogger.conf` uses `loxberry:<primary _vzlogger group> 0640`; the vzLogger log uses `_vzlogger:loxberry 0640`.
- Serial devices use `root:loxberry 0660`. The vzLogger override uses `SupplementaryGroups=loxberry`; plugin systemd units use a restrictive `UMask` (`0027`).
- Never reintroduce `0777`/`0666` fallbacks. Install and upgrade hooks repair required ownership and modes idempotently.

## 9. Lifecycle And Ownership Boundaries

- Fresh installation defaults to an inactive implementation, with the bridge and optional debug logs disabled. An upgrade over an existing installation preserves the user configuration.
- Upgrades remove obsolete Legacy polling cron entries and turn a stored `IMPLEMENTATION=legacy` into `none`, so the user has to activate vzLogger explicitly.
- The plugin-managed systemd drop-in points vzLogger to the plugin-owned configuration. Never overwrite an unrelated `/etc/vzlogger.conf`.
- Uninstall removes plugin-owned services, drop-ins, runtime/cache artifacts, udev rules, apt source/key, and only packages proven by an ownership marker to have been introduced by the plugin.
- Broader platform or meter support must not be claimed without matching target-system or representative-hardware evidence. Current limits remain in `KNOWN-ISSUES.md`.

## 10. UI, Localization, And Accessibility

- Desktop and mobile browsers provide the same functions and information. Follow the responsive viewport and acceptance requirements in `AGENTS.md` and `docs/test-device-workflow.md`.
- German and English UI phrases, templates, validation messages, and user documentation must remain synchronized. Exercise the longer German labels during responsive testing.
- Current plugin UI translations live only in LoxBerry's native `templates/lang/language_de.ini` and `language_en.ini` resources, separated into shared, vzLogger, and Legacy namespaces. Do not restore duplicate `language.txt` trees or custom language loaders.
- Localize only plugin-authored text written for users in the browser, including the explanatory part of browser validation and action messages. Do not localize established technical terms, product or project names, protocol and format identifiers, commands, paths, configuration keys, API values, systemd states, or comparable machine-relevant identifiers.
- Keep technical CLI output, logs, and unmodified diagnostics from the operating system, systemd, or external programs in English. This keeps operation, troubleshooting, and automated evaluation language-independent; a localized UI may add a translated explanation without rewriting the technical detail.
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

- Architecture and implementation history (not a normative specification): `docs/vzlogger-implementation-plan.md`
- User-visible behavior: `docs/User-Guide.de.md` and `docs/User-Guide.en.md`
- Installed-device and browser verification: `docs/test-device-workflow.md`
- Lifecycle acceptance: `docs/lifecycle-test-expectations.md`
- Compatibility evidence and limitations: `KNOWN-ISSUES.md`
- Release procedure: `docs/release-process.md`
