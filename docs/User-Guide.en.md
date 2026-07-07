# SmartMeter v2 User Guide

## Overview

SmartMeter v2 reads smart meter data on LoxBerry. The standard implementation uses the external `vzlogger` package. vzLogger reads the meter and publishes values by MQTT; the plugin keeps a local cache from that MQTT stream and serves HTTP and UDP output from the cache.

The legacy implementation remains available. Use it if an existing setup depends on the old reader or if vzLogger does not support a required meter setup yet.

## Requirements

- LoxBerry with the SmartMeter v2 plugin installed.
- At least one supported optical I/R reading head below `/dev/serial/smartmeter/`.
- For the standard implementation: installed `vzlogger` package and `mosquitto-clients`.
- For MQTT transport: the LoxBerry MQTT broker settings must be available in LoxBerry.

## Standard Configuration With vzLogger

Open the SmartMeter v2 plugin in the LoxBerry web interface and use the **Smartmeter Configuration (vzLogger)** page.

### Package Installation

If `vzlogger` is missing, use **Install vzLogger package**. The helper configures the Volkszaehler/Cloudsmith apt repository and installs `vzlogger` through apt. This action requires root privileges on the target system.

`mosquitto-clients` remains a regular plugin dependency because the MQTT bridge uses `mosquitto_sub`.

### Meter Setup

Enable **Read meters** to let vzLogger and the MQTT bridge provide live values.

Select the detected I/R head and choose a meter preset. The current generator maps presets to the vzLogger protocols `sml` or `d0`. For D0 meters, manual serial settings can be set if the preset defaults are not sufficient.

The plugin generates:

- `vzlogger.conf` in the plugin config directory.
- `vzlogger_channels.json` with the stable channel UUID to SmartMeter cache-name mapping.

Use **Save and generate config** to write the files and validate their structure. Use **Validate config** to run validation again without applying the configuration.

### Apply Flow

Use **Save and apply** to generate and validate the config, copy it to `/etc/vzlogger.conf`, restart `vzlogger`, and start the MQTT bridge.

If meter reading is disabled, applying the configuration stops vzLogger and the bridge.

### Bridge Service

Use **Install bridge service** to install the MQTT bridge as a systemd service. Without the service, the control script can still start a forked bridge process as fallback.

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

The bridge converts recognized vzLogger messages into legacy-compatible `.data` cache files below:

```text
/var/run/shm/<plugin folder>/
```

The existing HTTP endpoint continues to serve values from these cache files. If UDP is enabled, the bridge sends the cached values cyclically to all configured Miniservers.

## Debug Log

Enable **Debug log** before reproducing a problem. This makes the MQTT bridge log raw MQTT topics, payloads, UUID mapping decisions, parsed cache names, and ignored messages.

Use **Create debug log** to create a diagnostic log in the runtime directory. It includes:

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

Check whether the target Debian/Raspberry Pi OS codename and architecture are supported by the Volkszaehler/Cloudsmith repository. Run the package installer as root and attach the debug log if the failure is not obvious.

### No cached values are written

Check the following:

- `vzlogger` is running.
- The MQTT bridge is running as service or fallback process.
- `mosquitto_sub` is installed.
- `vzlogger_channels.json` exists and validates.
- The debug log contains real MQTT messages under `<base topic>/vzlogger/#`.

### HTTP or UDP has no values

Check whether `.data` files exist below `/var/run/shm/<plugin folder>/`. HTTP and UDP use this cache and do not query vzLogger directly.

### Legacy reading has no meter data

Check the following:

- The I/R reading head is connected.
- The device exists below `/dev/serial/smartmeter/`.
- The legacy meter configuration is complete.
- Manual reading from the legacy web interface works.

### Log Files

The plugin writes runtime logs below the LoxBerry plugin log directory and runtime logs below `/var/run/shm/<plugin folder>/`. In the legacy frontend, use the log view to inspect legacy meter read and publish activity.
