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

The **Smartmeter Configuration (vzLogger)** and **Smartmeter Configuration (Legacy)** tabs only switch between configuration views. The active reader is selected through the **Implementation** field and is applied only when the form is saved.

Select **vzLogger** as the **Implementation** mode at the top of the page. When saved, the plugin removes the legacy polling cron jobs so both readers do not run in parallel.

### Package Installation

During installation or upgrade, the plugin configures the Volkszaehler/Cloudsmith apt repository. LoxBerry then installs `vzlogger` and `mosquitto-clients` through the plugin's normal `dpkg/apt` package list. If `vzlogger` is already installed, the existing package ownership is preserved and apt updates it to the available current version.

After installation, the plugin stops and disables the `vzlogger` service again while Legacy is active. vzLogger starts when **Save and apply** is used in vzLogger mode; the MQTT bridge can remain disabled independently.

### Meter Setup

A newly detected reader is marked **New / unsaved** in its panel until the next **Save and apply**. If that meter runs OBIS discovery before being applied, the plugin stores only the selected standard protocol—SML, D0, or OMS—in a meter-specific pending file. After a page reload, the UI can therefore select that protocol again and display the discovered OBIS channels. Other unsaved meter fields, particularly OMS keys, are not persisted as a draft. **Save and apply** and final meter removal both delete this pending file.

Enable **Bridge service enabled** when the MQTT bridge should forward vzLogger MQTT values to the plugin HTTP cache and optional UDP output. The `vzlogger` service itself remains startable in vzLogger mode independently of the bridge. The **Update cycle** controls how often vzLogger publishes meter values by MQTT; the bridge uses the same cycle for HTTP cache writes and UDP sends. The MQTT base topic is a shared setting and remains configurable independently of the service buttons.

Connect an I/R reading head and select **Rescan for I/R heads**. The AJAX scan displays an overlay that cannot be closed while it is active. Device detection itself is a short directory lookup; if the request nevertheless does not respond within 15 seconds, it ends as an error. When complete, the overlay reports whether no devices, no new devices, genuinely new readers, or connected readers staged for removal only in the browser were found. Genuinely new and staged readers may occur in the same scan and are listed separately as `Name: device path`. Staged readers are shown again with their unsaved inputs intact, while new reader panels are inserted directly into the existing page. The page is not reloaded. Only a result containing neither new nor staged readers closes automatically after a visible three-second countdown. Results containing new or staged devices, no detected devices, and errors remain visible until **Close** is selected. A separate, initially collapsed section appears below the button for every detected reading head. Its heading shows the name, device path, and selected protocol. SML, D0, OMS, and **Custom (JSON)** are available. The form displays only meter parameters supported by the selected protocol. Existing SML and D0 meter presets are migrated to the new schema on the first save while retaining their known baud rates and serial values. A reading head without a selected protocol is not generated as a meter.

SML, D0, and OMS continue to show OBIS discovery, discovered channels, and the additional-identifier field. Discovery uses the meter's current, not-yet-applied form settings, so recreating a meter does not require **Save and apply** before starting discovery. Genuinely new results are selected automatically and marked **New** until the next **Save and apply**. Known channels that were deliberately deselected remain deselected, and repeated discovery does not mark known results as new again. Discovery starts as a browser-independent background job. A progress overlay with a spinner polls status once per second, resumes after a page reload, and provides **Cancel search**. Closing, reloading, or navigating away does not terminate the job; the background process stores discovered channels itself. A controlled cancellation restores the regular vzLogger service. Discovery briefly stops that service and runs an independently time-bounded vzLogger test in the foreground. It checks the log once per second and finishes early as soon as every detected OBIS channel has appeared at least twice; 15 seconds remains the safety limit. Start, Stop, and Restart additionally remove matching plugin test processes. The regular service is started again afterwards. If only this restoration fails, the UI shows a warning while preserving the discovered channels and their pending markers. After successful discovery, the UI updates the channel list in place without reloading the page. Unsaved protocol selections, form values, and checkbox deselections therefore remain intact. Both complete identifiers such as `1-0:1.8.0` and short D0/OMS forms such as `1.8.0` are accepted. If the installed vzLogger does not support OMS, the UI marks the reading head and disables its OBIS discovery; validation and apply also report the missing runtime support.

SML, D0, and OMS also expose the general meter parameters `enabled`, `allowskip`, and `aggtime`. `aggtime` is not SML-specific and is valid for every meter protocol; `-1` disables aggregation. Empty optional fields are omitted from `vzlogger.conf`. In particular, the SML baud-rate and parity fields are empty by default so vzLogger uses its internal defaults. Explicitly selected baud-rate or parity values are retained. The standard forms always use the detected reading head's local device path. An SML or D0 meter using a TCP `host` must therefore be configured through **Custom (JSON)**.

**Custom (JSON)** is only a GUI mode. The editor contains exactly one complete vzLogger meter object whose actual `protocol`, for example `exec` or `s0`, must be present in that object. Root sections such as `meters`, `mqtt`, or `local` are not accepted. Input, including comments and formatting, is stored unchanged as `vzlogger_meter_<reader>.jsonc` (maximum 64 KiB). Comments are removed and valid JSON is generated for `vzlogger.conf`. No meter defaults are inserted. Only an existing `channels` array may receive a missing stable UUID and a missing `api` value of `"null"`; the JSONC source remains untouched.

If a custom object is syntactically or structurally invalid, its input remains stored, the reading head shows a red warning symbol, and the concrete error appears when expanded. That meter is omitted from the newly generated `vzlogger.conf` and `vzlogger_channels.json`, while other valid meters remain. A missing absolute local `device` path also produces a visible warning but does not prevent the meter object from being used.

At the end of every reader panel, **Remove meter configuration** can stage that configuration for removal. The panel disappears immediately only from the current browser view; reloading or reopening the page without **Save and apply** discards the staged removal completely. Only **Save and apply** removes the section from `smartmeter.cfg`, its entries from `vzlogger_channels.json`, and its meter-specific JSONC, OBIS, pending, test, log, and runtime cache files. Removing the last meter makes the meterless configuration a valid disabled state: vzLogger and the bridge are stopped, and the SmartMeter service override is removed. A removed reader that remains connected stays hidden during normal page loads. **Scan for I/R readers** clears that marker for currently detected devices and recreates their default settings; the meter and channel selection must then be configured and applied again.

The plugin generates:

- `vzlogger.conf` in the plugin config directory.
- `vzlogger_channels.json` with the stable channel UUID to SmartMeter cache-name mapping.

Use **Save and apply** for the normal workflow; it writes, validates, and applies the configuration. **Validate config** is retained to validate a saved or manually edited configuration without applying it.

The bridge service for HTTP cache and UDP is optional and is switched off by default on fresh installs.

For each SML, D0, or OMS reader, known OBIS channels can be selected and additional meter-specific OBIS channels can be added line by line. An optional `*255` suffix is removed when saving, because the generated vzLogger config uses identifiers without that suffix. The known channels also include manufacturer ID (`1-0:96.50.1`) and server ID (`1-0:96.1.0`) when the meter provides those values. In custom JSON mode, channels belong to the supplied meter object, so no separate OBIS UI is displayed.

### Apply Flow

Use **Save and apply** to generate and validate the config. The plugin installs a systemd drop-in for the `vzlogger` service that starts vzLogger directly with `/opt/loxberry/config/plugins/smartmeter-v2/vzlogger.conf`. It then enables the service for LoxBerry reboot startup and restarts it. If **Bridge service enabled** is on, the plugin also installs and starts the MQTT bridge as a systemd service; otherwise it only stops the bridge.

The generated `vzlogger.conf` orders sections and parameters according to the vzLogger documentation. Root parameters start with `retry`, `verbosity`, and `log`, followed by `local`, `mqtt`, and `meters`, each with a stable parameter order.

If Legacy mode is active, applying the configuration stops vzLogger and the bridge and removes the plugin drop-in. An unrelated `/etc/vzlogger.conf` is left unchanged.

### Service Control

At the top of the vzLogger page, the **Operation** section contains two separate service panels. The first controls the actual `vzlogger` service and provides status, Start/Stop/Restart, log, debug logging, log level, and live-data links. **Show generated config** is placed below, directly before the generated-config path, and opens `/opt/loxberry/config/plugins/smartmeter-v2/vzlogger.conf` read-only in a new browser tab; `pass` and `keypass` are masked. The second controls the **SmartMeter bridge**, a plugin add-on service for HTTP cache and UDP; its debug-log switch is placed directly beside the log action. Turning on the unsaved vzLogger activation switch immediately allows the bridge to be enabled as long as MQTT is on. All bridge settings, including HTTP-cache status, are enabled only while the bridge is active; the UDP port additionally requires **Send UDP**. Stop remains available for a service that is still running.

Service state is refreshed every three seconds while the browser tab is visible. During Start/Stop/Restart, this polling pauses; an overlay names the running action, and its AJAX response updates the real service state directly when it finishes. The overlay closes automatically on success. If an action takes longer than 15 seconds, the overlay reports the delay. **Hide** closes only the overlay while the system action already started continues in the background; an error reopens the overlay and can be acknowledged with **Close**. Start/Stop/Restart run without a page reload. Start/Restart become available when the corresponding activation switch is on and a valid generated configuration exists; for the bridge, MQTT must additionally be saved and enabled in the generated `vzlogger.conf`. They apply only the respective service activation. vzLogger also persists debug logging and log level and updates those values in the existing `vzlogger.conf`; the bridge persists only its debug-log switch. Other unsaved inputs remain in the browser and take effect only with **Save and apply**. Stop remains available for a running service regardless of activation switches or configuration errors. Start/Restart validate the existing configuration but never regenerate it; if it is missing or invalid, use **Save and apply** first. **Open live data (JSON)** opens vzLogger's integrated HTTP service; `/` returns all configured channels because the index is enabled, while `/<UUID>` returns one channel.

Below service control, settings are visually separated into **vzLogger configuration** and **SmartMeter bridge configuration**, each with a short description. Meters and I/R reading heads belong to the vzLogger configuration. Update cycle, HTTP cache, and UDP output belong to the bridge configuration. Disabled areas dim controls, labels, and help text together without changing their values. For an inactive SML, D0, or OMS meter, only its description and **Meter enabled** switch remain editable. The UDP port immediately follows the unsaved **Send UDP** switch and is editable only while the bridge and UDP output are enabled.

Meters, reading heads, protocols, and OBIS channels belong exclusively to the vzLogger configuration. vzLogger reads the devices and publishes readings through MQTT. The SmartMeter bridge subscribes to these MQTT messages and additionally uses `vzlogger_channels.json` to map a UUID or `chnX` to its reading head, OBIS identifier, and output name. The bridge does not access meters or serial devices directly. Update interval, HTTP cache, and UDP therefore reside in a separate, collapsed **SmartMeter bridge settings** section.

The collapsed **Advanced vzLogger service settings** section contains the rarely needed retry delay (`retry`). It sets the delay in seconds after a failed request and is preserved whenever `vzlogger.conf` is regenerated. Debug logging and log level (`verbosity`) remain directly available in the visible vzLogger service row.

The collapsed **vzLogger HTTP service (local)** section contains all settings for vzLogger's integrated HTTP service: `enabled`, `port`, `index`, `timeout`, and `buffer`. The plugin defaults are `true`, `18080`, `true`, `30`, and `-1`. Positive buffer values specify the number of seconds, while negative values specify the number of tuples per channel. All values are preserved whenever `vzlogger.conf` is regenerated.

The collapsed **MQTT** section is divided into **Connection and publishing**, **Authentication – user/password**, and **Authentication – certificate**. Broker, port, and user show the effective value: a plugin override takes precedence, followed by the LoxBerry MQTT system setting and finally `127.0.0.1:1883` for broker/port. Unchanged system values are not duplicated as plugin overrides when saved; clearing a field restores LoxBerry inheritance. Password fields remain empty and masked and only indicate whether a custom or LoxBerry password is used. The generated `vzlogger.conf` contains the effective credentials required by vzLogger but omits empty client-ID, user, password, and certificate parameters. Stored passwords are written neither to GUI HTML nor unmasked diagnostic output. The generator, internal MQTT bridge, and diagnostic capture use the same connection settings. Because `mosquitto_sub` in the internal bridge cannot receive a private-key password on its command line, its private key must be readable without an interactive prompt.

In addition to raw JSON, a rendered page refreshes the readings every two seconds. It groups values by I/R reading head and channel and shows the channel number, configured name, OBIS identifier, UUID, and raw timestamp with readable local time. Channel metadata comes from `vzlogger_channels.json` and is reloaded by the browser only when the generated mapping changes.

If the meter does not provide an instantaneous power value, the MQTT bridge additionally calculates `Consumption_CalculatedPower_OBIS_1.99.0` from `1.8.0` and `Delivery_CalculatedPower_OBIS_2.99.0` from `2.8.0` once two different counter readings are available. The unit follows the unit of the received counter value per hour.

The bridge log is `/opt/loxberry/log/plugins/smartmeter-v2/vzlogger_mqtt_bridge.log` and rotates at 2 MB. The control log is `/opt/loxberry/log/plugins/smartmeter-v2/vzlogger_control.log` and rotates at 512 KB. Apply and diagnostic logs are also written to the plugin log directory; the last five `vzlogger_debug_*.log` files are kept. The separate vzLogger debug log `/opt/loxberry/log/plugins/smartmeter-v2/vzlogger.log` is written only when vzLogger debugging is enabled. Normal operation does not write a vzLogger file log.

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

Use **Create debug log** to create a diagnostic log in the plugin log directory. It includes:

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

Saving the legacy page sets the mode to **Legacy**, stops vzLogger and the MQTT bridge, and restores the legacy polling cron job when **Read meters** is enabled.

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
