# SmartMeter v2 User Guide

## Overview

SmartMeter v2 reads smart meter data on LoxBerry. The standard implementation uses the external `vzlogger` package. vzLogger reads the meter and publishes values by MQTT; the plugin keeps a local cache from that MQTT stream and serves HTTP and UDP output from the cache.

The legacy implementation remains available. Use it if an existing setup depends on the old reader or if vzLogger does not support a required meter setup yet.

## Requirements

- LoxBerry with the SmartMeter v2 plugin installed.
- At least one supported optical I/R reading head below `/dev/serial/smartmeter/`.
- For the standard implementation: installed `vzlogger` package and `mosquitto-clients`. Both packages are installed by LoxBerry during plugin installation.
- For MQTT transport: the LoxBerry MQTT broker settings must be available in LoxBerry.

## Standard Configuration With vzLogger

Open the SmartMeter v2 plugin in the LoxBerry web interface and use the **Smartmeter Configuration (vzLogger)** page.

The **Smartmeter Configuration (vzLogger)** and **Smartmeter Configuration (Legacy)** tabs only switch between configuration views. A white badge with a green check mark identifies the active implementation, while a white badge with a dark-gray minus identifies an inactive one. Legacy and vzLogger cannot be active at the same time, but both may be inactive. Enabling one implementation disables the other when saved; disabling one does not automatically enable the other. The state takes effect only when saved. After a change, the vzLogger, SmartMeter bridge, and Legacy activation switches therefore display **Change not saved yet**.

Select **vzLogger** as the **Implementation** mode at the top of the page. When saved, the plugin removes the legacy polling cron jobs so both readers do not run in parallel.

An existing valid `vzlogger.conf` is preserved while switching between implementations. Enabling or disabling Legacy, including the state in which both implementations are inactive, does not overwrite this file. When vzLogger is enabled again, the plugin validates and reuses the existing configuration unchanged. The current Legacy/form values are migrated into a new `vzlogger.conf` only when no valid generated vzLogger configuration exists. A normal **Save and apply** while vzLogger is already active still deliberately regenerates the file from the displayed vzLogger settings.

The Legacy meter configuration is preserved independently as well. Meter selection, manual protocol, baud rates, timeout, delay, handshake, data bits, stop bits, parity, and CRC are stored internally in dedicated `LEGACY_*` keys. On the first page load after updating, the plugin copies existing Legacy values into that area once. Saving a vzLogger configuration no longer changes those Legacy values. When switching back to Legacy, both its UI and polling runtime use the unchanged isolated Legacy settings.

### Package Installation

During installation or upgrade, the plugin configures the Volkszaehler/Cloudsmith apt repository. LoxBerry then installs `vzlogger` and `mosquitto-clients` through the plugin's normal `dpkg/apt` package list. If `vzlogger` is already installed, the existing package ownership is preserved and apt updates it to the available current version.

After installation, the plugin stops and disables the `vzlogger` service again while Legacy is active. vzLogger starts when **Save and apply** is used in vzLogger mode; the MQTT bridge can remain disabled independently.

### Meter Setup

A newly detected reader is marked **New / unsaved** in its panel until the next **Save and apply**. If that meter runs OBIS discovery before being applied, the plugin stores only the selected standard protocol—SML, D0, or OMS—in a meter-specific pending file. After a page reload, the UI can therefore select that protocol again and display the discovered OBIS channels. Other unsaved meter fields, particularly OMS keys, are not persisted as a draft. **Save and apply** and final meter removal both delete this pending file.

Enable **Bridge service enabled** when the MQTT bridge should forward vzLogger MQTT values to the plugin HTTP cache and optional UDP output. The `vzlogger` service itself remains startable in vzLogger mode independently of the bridge. The **Update cycle** controls how often vzLogger publishes meter values by MQTT; the bridge uses the same cycle for HTTP cache writes and UDP sends. The MQTT base topic is a shared setting and remains configurable independently of the service buttons.

Connect an I/R reading head and select **Rescan for I/R heads**. The AJAX scan displays an overlay that cannot be closed while it is active. Device detection itself is a short directory lookup; if the request nevertheless does not respond within 15 seconds, it ends as an error. When complete, the overlay reports whether no devices, no new devices, genuinely new readers, or connected readers staged for removal only in the browser were found. Genuinely new and staged readers may occur in the same scan and are listed separately as `Name: device path`. Staged readers are shown again with their unsaved inputs intact, while new reader panels are inserted directly into the existing page. The page is not reloaded. Only a result containing neither new nor staged readers closes automatically after a visible three-second countdown. Results containing new or staged devices, no detected devices, and errors remain visible until **Close** is selected. A separate, initially collapsed section appears below the button for every detected reading head. Its heading shows the name, device path, and selected protocol. SML, D0, OMS, and **Custom (JSON)** are available. The form displays only meter parameters supported by the selected protocol. Existing SML and D0 meter presets are migrated to the new schema on the first save while retaining their known baud rates and serial values. A reading head without a selected protocol is not generated as a meter.

SML, D0, and OMS show OBIS discovery and one unified channel editor for discovered and manually added channels. Discovery uses the meter's current, not-yet-applied form settings, so recreating a meter does not require **Save and apply** before starting discovery. New identifiers are added as active `api: null` rows; discovery does not add another row when the complete identifier already exists. Manual creation may deliberately add the same identifier more than once as separate vzLogger channels with distinct UUIDs. Discovery starts as a browser-independent background job. A progress overlay with a spinner polls status once per second, resumes after a page reload, and provides **Cancel search**. Closing, reloading, or navigating away does not terminate the job; the background process stores discovered identifiers itself. A controlled cancellation restores the regular vzLogger service. Discovery briefly stops that service and runs an independently time-bounded vzLogger test in the foreground. It checks the log once per second and finishes early as soon as every detected OBIS channel has appeared at least twice; 15 seconds remains the safety limit. Start, Stop, and Restart additionally remove matching plugin test processes. The regular service is started again afterwards. If only this restoration fails, the UI shows a warning while preserving detected identifiers. After successful discovery, the UI updates the editor in place without reloading the page. Both complete identifiers such as `1-0:1.8.0` and short D0 forms such as `1.8.0` are accepted. If the installed vzLogger does not support OMS, the UI marks the reading head and disables its OBIS discovery; validation and apply also report the missing runtime support.

SML, D0, and OMS also expose the general meter parameters `enabled`, `allowskip`, and `aggtime`. `aggtime` is not SML-specific and is valid for every meter protocol; `-1` disables aggregation. Empty optional fields are omitted from `vzlogger.conf`. In particular, the SML baud-rate and parity fields are empty by default so vzLogger uses its internal defaults. Explicitly selected baud-rate or parity values are retained. The standard forms always use the detected reading head's local device path. An SML or D0 meter using a TCP `host` must therefore be configured through **Custom (JSON)**.

After selecting SML or D0, **Initialize from template** becomes available. The selector shows only meter models matching the selected protocol. An SML template sets only the baud rate and serial mode. A D0 template sets the initial communication baud rate, read baud rate, serial mode, and read timeout. Name, activation, device, intervals, sequences, OBIS channels, and all other meter settings remain unchanged. The applied values initially change only the browser form and must be persisted with **Save and apply**. For meter models whose earlier implementation used additional special sequences, the UI notes that only the available basic values are applied.

Legacy and vzLogger use the same central meter-template catalog. Baud rates are stored neutrally as the initial communication baud rate and operating/read baud rate. Legacy maps these values to `STARTBAUDRATE` and `BAUDRATE`. For vzLogger, SML maps the operating/read baud rate to `baudrate`; D0 maps the initial communication baud rate to `baudrate` and the read baud rate to `baudrate_read`. Meter models, serial settings, and Legacy-specific sequences therefore need to be maintained in only one place.

**Custom (JSON)** is only a GUI mode. The editor contains exactly one complete vzLogger meter object whose actual `protocol`, for example `exec` or `s0`, must be present in that object. Root sections such as `meters`, `mqtt`, or `local` are not accepted. Input, including comments and formatting, is stored unchanged as `vzlogger_meter_<reader>.jsonc` (maximum 64 KiB). Comments are removed and valid JSON is generated for `vzlogger.conf`. No meter defaults are inserted. Only an existing `channels` array may receive a missing stable UUID and a missing `api` value of `"null"`; the JSONC source remains untouched.

If a custom object is syntactically or structurally invalid, its input remains stored, the reading head shows a red warning symbol, and the concrete error appears when expanded. That meter is omitted from the newly generated `vzlogger.conf` and `vzlogger_channels.json`, while other valid meters remain. A missing absolute local `device` path also produces a visible warning but does not prevent the meter object from being used.

At the end of every reader panel, **Remove meter configuration** can stage that configuration for removal. The panel disappears immediately only from the current browser view; reloading or reopening the page without **Save and apply** discards the staged removal completely. Only **Save and apply** removes the section from `smartmeter.cfg`, its entries from `vzlogger_channels.json`, and its meter-specific JSONC, OBIS, pending, test, log, and runtime cache files. Removing the last meter makes the meterless configuration a valid disabled state: vzLogger and the bridge are stopped, and the SmartMeter service override is removed. A removed reader that remains connected stays hidden during normal page loads. **Scan for I/R readers** clears that marker for currently detected devices and recreates their default settings; the meter and channel selection must then be configured and applied again.

The plugin generates:

- `vzlogger.conf` in the plugin config directory.
- `vzlogger_channel_definitions.json` with all active and inactive channel definitions and the retained target options for each API.
- `vzlogger_channels.json` containing only active plugin outputs and their stable channel UUID to SmartMeter output-key mapping.

Use **Save and apply** for the normal workflow; it saves the current form values, generates and validates the configuration, and applies it. **Validate config** instead copies the current form values into a temporary draft and generates and validates temporary files from it. It does not change `smartmeter.cfg`, `vzlogger.conf`, `vzlogger_channels.json`, or custom meter files, and it does not control any services. Both actions use AJAX without reloading the page, and the overlay shows the elapsed time. Generation, validation, and application share a 60-second server-side time limit. If it is reached, the plugin stops the currently running subprocess and displays the error in the overlay. With **Save and apply**, settings or completed intermediate steps may already have been applied at that point, so review the displayed error and service status. Validation results remain in the overlay until explicitly closed. After a successful apply, the overlay closes after a visible three-second countdown; failures remain open for acknowledgement. Validation also rejects invalid or unreasonably large baud rates.

The bridge service for HTTP cache and UDP is optional and is switched off by default on fresh installs.

For each reader, the editor manages every channel instance with activation, OBIS identifier, origin, API, and optional SmartMeter output. Channel cards use the full width of the expanded reader panel; only the currently open settings content is highlighted with a very light pastel-yellow background and a subtle border. Short, permanently visible help text appears directly below every common and API-specific control. Changing a field preserves the expanded/collapsed state of that channel's advanced settings. The internal OBIS catalog provides an English or German short name, long explanation, expected unit, and semantic category. Unknown or manufacturer-specific codes remain fully configurable and their A–F groups are shown in a readable form. A custom semantic display name changes only presentation. Neither it nor the technical **Output key (cache/UDP)** is written to `vzlogger.conf`, because vzLogger has no general channel-name field. Active plugin output keys must be unique per reader without regard to case, use at most 64 characters, and contain only letters, digits, and underscores. When an existing channel can be migrated unambiguously, the bridge also emits its previous cache/UDP name as a compatibility alias; no unsafe alias is generated for repeated identifiers.

Each channel row shows the currently applied vzLogger/MQTT DATA index as **Channel N**. The number is read from the generated `vzlogger.conf` and therefore matches the channel number on the rendered live-data page; unapplied or inactive definitions show **Channel –**. The advanced-settings heading additionally displays the persistent UUID in grey. After a successful **Save and apply**, the page refreshes the applied numbers without reloading.

Manually created channel definitions provide **Remove OBIS channel** at the end of their advanced settings. After confirmation with channel number, OBIS identifier, and UUID, the card is hidden only from the current browser draft. Reloading before **Save and apply** discards the staged removal. Applying permanently removes the definition and regenerates `vzlogger.conf` and `vzlogger_channels.json` without that channel. Discovered channels are disabled with **Active** instead, because a later discovery run may detect them again.

SML and D0 support an optional storage/billing index `*F`. Values 0 through 254 select a value that the meter actually delivers under that complete identifier; they do not request history or read a load profile. The editor represents the standard unused value 255 with **Unspecified (255)**. Existing empty, `null`, and `*255` values are normalized to this state and are not written as an unnecessary `*255` suffix. For OMS, the field is disabled and is also ignored by the backend. **Aggregation** (`none`, `avg`, `max`, `sum`) is a temporal vzLogger processing setting, not a value type. It is available only when meter-level `aggtime > 0`. New known channels then receive the catalog recommendation, while existing values are never overwritten.

Each API enables only its own target parameters. `null` has none. Volkszaehler requires `middleware`; InfluxDB requires `host` and provides version/database or bucket, organization, measurement, tags, authentication, timeout, batch/buffer, UUID, and TLS settings; MySmartGrid requires `middleware`, `secretKey`, `device`, and `type`, and labels `name` explicitly as the MySmartGrid registration name. `duplicates` applies only to Volkszaehler and InfluxDB. Values retained for inactive APIs are neither validated nor generated in `vzlogger.conf`. In custom JSON mode, channels remain part of the supplied meter object, so no separate editor is displayed.

### Apply Flow

Use **Save and apply** to generate and validate the config. The plugin installs a systemd drop-in for the `vzlogger` service that starts vzLogger directly with `/opt/loxberry/config/plugins/smartmeter-v2/vzlogger.conf`. It then enables the service for LoxBerry reboot startup and restarts it. If **Bridge service enabled** is on, the plugin also installs and starts the MQTT bridge as a systemd service; otherwise it only stops the bridge.

The generated `vzlogger.conf` orders sections and parameters according to the vzLogger documentation. Root parameters start with `retry`, `verbosity`, and `log`, followed by `local`, `mqtt`, and `meters`, each with a stable parameter order.

If Legacy mode is active, applying the configuration stops vzLogger and the bridge and removes the plugin drop-in. An unrelated `/etc/vzlogger.conf` is left unchanged.

### Service Control

At the top of the vzLogger page, two separate service panels are shown. The first controls the actual `vzlogger` service and provides status, Start/Stop/Restart, log, debug logging, log level, and live-data links. Start, Stop, and Restart each have their own tooltip; when the Start/Stop control changes with the live service state, its tooltip changes with it. The action help for these service controls, I/R-head scanning, OBIS discovery, and **Show generated config** is also displayed in the right-side help column. **Show generated config** is placed below, directly before the generated-config path, and opens `/opt/loxberry/config/plugins/smartmeter-v2/vzlogger.conf` read-only with line numbers in a new browser tab; `pass` and `keypass` are masked. The second controls the **SmartMeter bridge**, a plugin add-on service for HTTP cache and UDP; its debug-log switch is placed directly beside the log action. Turning on the unsaved vzLogger activation switch immediately allows the bridge to be enabled as long as MQTT is on. All bridge settings, including HTTP-cache status, are enabled only while the bridge is active; the UDP port additionally requires **Send UDP**. Stop remains available for a service that is still running. The open/closed state of every collapsible panel is stored locally in the browser and restored after a manual reload.

Service state is refreshed every three seconds while the browser tab is visible. During Start/Stop/Restart, this polling pauses; an overlay names the running action, and its AJAX response updates the real service state directly when it finishes. The overlay closes automatically on success. If an action takes longer than 15 seconds, the overlay reports the delay. **Hide** closes only the overlay while the system action already started continues in the background; an error reopens the overlay and can be acknowledged with **Close**. Start/Stop/Restart run without a page reload. Start/Restart become available when the corresponding activation switch is on and a valid generated configuration exists; for the bridge, MQTT must additionally be saved and enabled in the generated `vzlogger.conf`. They apply only the respective service activation. vzLogger also persists debug logging and log level and updates those values in the existing `vzlogger.conf`; the bridge persists only its debug-log switch. Other unsaved inputs remain in the browser and take effect only with **Save and apply**. Stop remains available for a running service regardless of activation switches or configuration errors. Start/Restart validate the existing configuration but never regenerate it; if it is missing or invalid, use **Save and apply** first. **Open live data (JSON)** opens vzLogger's integrated HTTP service; `/` returns all configured channels because the index is enabled, while `/<UUID>` returns one channel.

Below service control, settings are visually separated into **vzLogger configuration** and **SmartMeter bridge configuration**, each with a short description. Meters and I/R reading heads belong to the vzLogger configuration. Update cycle, HTTP cache, and UDP output belong to the bridge configuration. Disabled areas dim controls, labels, and help text together without changing their values. For an inactive SML, D0, or OMS meter, only its description and **Meter enabled** switch remain editable. The UDP port immediately follows the unsaved **Send UDP** switch and is editable only while the bridge and UDP output are enabled.

Meters, reading heads, protocols, and OBIS channels belong exclusively to the vzLogger configuration. vzLogger reads the devices and publishes readings through MQTT. The SmartMeter bridge subscribes to these MQTT messages and additionally uses `vzlogger_channels.json` to map a UUID or `chnX` to its reading head, OBIS identifier, and output name. The bridge does not access meters or serial devices directly. Update interval, HTTP cache, and UDP therefore reside in a separate, collapsed **SmartMeter bridge settings** section.

The collapsed **Advanced vzLogger service settings** section contains the rarely needed retry delay (`retry`). It sets the delay in seconds after a failed request and is preserved whenever `vzlogger.conf` is regenerated. Debug logging and log level (`verbosity`) remain directly available in the visible vzLogger service row.

The collapsed **vzLogger HTTP service (local)** section contains all settings for vzLogger's integrated HTTP service: `enabled`, `port`, `index`, `timeout`, and `buffer`. The plugin defaults are `true`, `18080`, `true`, `30`, and `-1`. Positive buffer values specify the number of seconds, while negative values specify the number of tuples per channel. All values are preserved whenever `vzlogger.conf` is regenerated.

The collapsed **MQTT** section is divided into **Connection and publishing**, **Authentication – user/password**, and **Authentication – certificate**. Broker, port, and user show the effective value: a plugin override takes precedence, followed by the LoxBerry MQTT system setting and finally `127.0.0.1:1883` for broker/port. Unchanged system values are not duplicated as plugin overrides when saved; clearing a field restores LoxBerry inheritance. Password fields remain empty and masked and only indicate whether a custom or LoxBerry password is used. The generated `vzlogger.conf` contains the effective credentials required by vzLogger but omits empty client-ID, user, password, and certificate parameters. Stored passwords are written neither to GUI HTML nor unmasked diagnostic output. The generator, internal MQTT bridge, and diagnostic capture use the same connection settings. Because `mosquitto_sub` in the internal bridge cannot receive a private-key password on its command line, its private key must be readable without an interactive prompt.

In addition to raw JSON, a rendered page refreshes the readings every two seconds. It groups values by I/R reading head and channel and shows the channel number, custom semantic display name or, as a fallback, the German OBIS-catalog short name, OBIS identifier, UUID, and raw timestamp with readable local time. Values include the catalog unit; electrical SML counters are converted from vzLogger's raw Wh value to kWh, while the raw value remains available as a tooltip. Channel metadata comes from `vzlogger_channels.json` and is reloaded by the browser only when the generated mapping changes.

If the meter does not provide an instantaneous power value, the MQTT bridge additionally calculates `Consumption_CalculatedPower_OBIS_1.99.0` from `1.8.0` and `Delivery_CalculatedPower_OBIS_2.99.0` from `2.8.0` once two different counter readings are available. The unit follows the unit of the received counter value per hour.

The bridge log is `/opt/loxberry/log/plugins/smartmeter-v2/vzlogger_mqtt_bridge.log` and rotates at 2 MB. The control log is `/opt/loxberry/log/plugins/smartmeter-v2/vzlogger_control.log`, rotates at 512 KB, and can be opened through **Show control log** directly below the two service panels. Successful Start, Stop, and Restart actions show a brief green confirmation; warnings and failures remain open with their details in the action dialog. Apply and diagnostic logs are also written to the plugin log directory; the last five `vzlogger_debug_*.log` files are kept. The separate vzLogger debug log `/opt/loxberry/log/plugins/smartmeter-v2/vzlogger.log` is written only when vzLogger debugging is enabled. Normal operation does not write a vzLogger file log.

The service name is:

```text
smartmeter-v2-vzlogger-bridge
```

## MQTT, HTTP, And UDP Data Flow

vzLogger publishes below:

```text
<base topic>/vzlogger
```

The MQTT bridge subscribes to:

```text
<base topic>/vzlogger/#
```

The bridge keeps recognized vzLogger messages in memory and writes them on the update cycle as legacy-compatible `.data` cache files below:

```text
/var/run/shm/<plugin folder>/
```

The existing HTTP endpoint continues to serve values from these cache files. The vzLogger page shows cache status, the last update, and a direct link to the cache endpoint in the **HTTP cache** section. If UDP is enabled, the bridge sends the cached values to all configured Miniservers on the same update cycle.

## Debug Log

Enable **Debug log** in the bridge row before reproducing a bridge problem. This makes the MQTT bridge log raw MQTT topics, payloads, UUID mapping decisions, parsed cache names, and ignored messages. The separate switch in the vzLogger service row controls vzLogger's own log.

**Create debug log** creates a diagnostic log in the plugin log directory without saving the current form values. A new browser tab immediately shows progress, monitors the entire operation, and switches to the LoxBerry log viewer when the file is ready; the settings page shows no additional overlay and is not reloaded. The server stops creation after 45 seconds if it does not finish normally. Closing the new tab earlier does not necessarily stop the already-started server process, which may continue until that limit. The log includes:

- package, apt source, service, bridge, and validation status
- recent vzLogger control and web action output
- `vzlogger --version` output, if available
- recent `systemctl` and `journalctl` output
- plugin config, generated `vzlogger.conf`, and `vzlogger_channels.json`
- bridge log tail
- available LoxBerry install and plugin log tails
- current `.data` cache files
- a bounded MQTT capture from `<base topic>/vzlogger/#`, if `timeout` and `mosquitto_sub` are available

This debug log contains the information needed to verify the real vzLogger MQTT topic and payload format and to finish the MQTT parser adjustment.

## Legacy Configuration

The legacy implementation is still available through **Smartmeter Configuration (Legacy)**. It supports optical I/R reading heads connected below `/dev/serial/smartmeter/` and can periodically read meters with the older SmartMeter scripts.

When a meter template is selected, the still-disabled **Manual settings** section shows the effective values used by that template. This preview does not overwrite the saved manual configuration. Selecting **Manual configuration** again therefore restores the previously saved manual values.

Enabling and saving the Legacy page sets the mode to **Legacy**, stops vzLogger and the MQTT bridge, and restores the legacy polling cron job when **Read meters** is enabled. Disabling and saving Legacy leaves vzLogger inactive as well until it is explicitly enabled and saved on its own page.

The legacy plugin path can publish values through:

- HTTP: values can be read from the plugin web frontend.
- UDP: values are sent to all configured Miniservers.
- MQTT: values are published through the LoxBerry MQTT Gateway.

For legacy MQTT publishing, configure the MQTT base topic in the plugin settings.

Default:

```text
smartmeter
```

Topic structure:

```text
<base topic>/<meter>/<value name>
```

Example:

```text
smartmeter/ABC123/Consumption_Total_OBIS_1.8.0
```

The legacy MQTT payload is the value only and messages are published with the retain flag.

## Meter Values

Typical value names are:

- `Last_Update`
- `Last_UpdateLoxEpoche`
- `Consumption_Total_OBIS_1.8.0`
- `Consumption_Power_OBIS_1.7.0`
- `Delivery_Total_OBIS_2.8.0`
- `Total_Power_OBIS_15.7.0`

The available values depend on the meter type, protocol, and configured OBIS channels.

## Troubleshooting

### vzLogger package installation fails

Check the LoxBerry installation log. The relevant steps are `PREROOT`, `Refreshing APT database`, and `Installing additional software packages`. If the Volkszaehler/Cloudsmith repository does not support the target codename or architecture, LoxBerry cannot install the `vzlogger` package.

### No cached values are written

Check the following:

- `vzlogger` is running.
- The MQTT bridge is running as service or fallback process.
- `mosquitto_sub` is installed.
- `vzlogger_channels.json` exists and validates.
- The debug log contains real MQTT messages under `<base topic>/vzlogger/#`.

### HTTP or UDP has no values

Check the **HTTP cache** section for a `.data` file and a current last update. Alternatively, check whether `.data` files exist below `/var/run/shm/<plugin folder>/`. HTTP and UDP use this cache and do not query vzLogger directly.

### Legacy reading has no meter data

Check the following:

- The I/R reading head is connected.
- The device exists below `/dev/serial/smartmeter/`.
- The legacy meter configuration is complete.
- Manual reading from the legacy web interface works.

### Log Files

The plugin writes runtime logs below the LoxBerry plugin log directory and runtime logs below `/var/run/shm/<plugin folder>/`. In the legacy frontend, use the log view to inspect legacy meter read and publish activity.
