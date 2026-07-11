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

Enable **Bridge service enabled** when the MQTT bridge should forward vzLogger MQTT values to the plugin HTTP cache and optional UDP output. The `vzlogger` service itself remains startable in vzLogger mode independently of the bridge. The **Update cycle** controls how often vzLogger publishes meter values by MQTT; the bridge uses the same cycle for HTTP cache writes and UDP sends. The MQTT base topic is a shared setting and remains configurable independently of the service buttons.

Connect an I/R head and select **Rescan for I/R heads**. Then select the detected head and choose a meter preset. A detected I/R head without a meter preset is not enough; validation fails because vzLogger would otherwise start without any configured meter. The current generator maps presets to the vzLogger protocols `sml` or `d0`. For D0 meters, manual serial settings can be set if the preset defaults are not sufficient.

The plugin generates:

- `vzlogger.conf` in the plugin config directory.
- `vzlogger_channels.json` with the stable channel UUID to SmartMeter cache-name mapping.

Use **Save and apply** for the normal workflow; it writes, validates, and applies the configuration. **Validate config** is retained to validate a saved or manually edited configuration without applying it.

The bridge service for HTTP cache and UDP is optional and is switched off by default on fresh installs.

For each reader, known OBIS channels can be selected and additional meter-specific OBIS channels can be added line by line. An optional `*255` suffix is removed when saving, because the generated vzLogger config uses identifiers without that suffix. The known channels also include manufacturer ID (`1-0:96.50.1`) and server ID (`1-0:96.1.0`) when the meter provides those values.

### Apply Flow

Use **Save and apply** to generate and validate the config, copy it to `/etc/vzlogger.conf`, enable the `vzlogger` service for LoxBerry reboot startup, and restart `vzlogger`. If **Bridge service enabled** is on, the plugin also installs and starts the MQTT bridge as a systemd service; otherwise it only stops the bridge.

If Legacy mode is active, applying the configuration stops vzLogger and the bridge.

### Service Control

The vzLogger page shows the status of `vzlogger` and the MQTT bridge with service state and PID. The `vzlogger` **Restart**, **Start**, and **Stop** buttons are available in vzLogger mode even when the bridge is disabled. The bridge buttons are available only while **Bridge service enabled** is on. Start and Restart actions regenerate and validate the saved configuration before starting services. **Open live data (JSON)** opens vzLogger's integrated HTTP service; `/` returns all configured channels because the index is enabled, while `/<UUID>` returns one channel.

In addition to raw JSON, an automatically refreshed generic web page renders the response every two seconds. The generated OBIS channel configuration determines which channels appear; `vzlogger_channels.json` contains the UUID mapping.

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
