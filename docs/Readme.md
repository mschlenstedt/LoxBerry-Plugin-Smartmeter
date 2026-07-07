# SmartMeter v2 Documentation

SmartMeter v2 is a LoxBerry plugin for reading smart meters with optical I/R reading heads. The legacy configuration can periodically read meter values and make them available by HTTP, UDP, and MQTT.

The standard implementation uses the external `vzlogger` package. The plugin generates `vzlogger.conf`, enables vzLogger MQTT publishing, and maintains a local cache from the MQTT stream. HTTP and UDP output are served from this cache.

If `vzlogger` is not available from the configured apt sources, use the vzLogger configuration page to add the official Volkszaehler/Cloudsmith apt repository and install `vzlogger` via apt.

The generated configuration can be validated from the vzLogger configuration page before applying it. Validation checks JSON syntax, required MQTT/local sections, meter definitions, channel UUIDs, and the MQTT-to-cache mapping.

The MQTT-to-HTTP/UDP bridge can be installed as a systemd service from the vzLogger configuration page. If the service is not installed, the plugin control script falls back to a directly forked bridge process.

For troubleshooting, enable the vzLogger debug log and use the configuration page to create a diagnostic log. It captures service state, generated configuration, channel mapping, bridge logs, cache files, and a bounded MQTT sample for parser verification.

Choose your language:

- [English user guide](User-Guide.en.md)
- [Deutsche Benutzerdokumentation](User-Guide.de.md)

## Quick Links

- MQTT topic structure: `<base topic>/<meter>/<value name>`
- Default MQTT base topic: `smartmeter`
- UDP sends the same value set to all configured Miniservers.
- HTTP access remains available through the plugin web frontend.
- vzLogger live readings can optionally be opened through the local vzLogger HTTP daemon.
