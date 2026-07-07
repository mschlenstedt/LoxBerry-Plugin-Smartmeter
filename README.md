# SmartMeter v2 for LoxBerry

SmartMeter v2 is a LoxBerry plugin for reading smart meters with optical I/R reading heads. It provides meter values through the plugin web frontend and can forward them by HTTP, UDP, and MQTT depending on the selected configuration.

The standard implementation uses the external `vzlogger` package. The plugin generates `vzlogger.conf`, enables vzLogger MQTT publishing, and maintains a local cache from the MQTT stream. HTTP and UDP output are served from this cache.

The legacy reader remains available for existing installations and meter setups that are not covered by vzLogger yet.

## Documentation

- [English user guide](docs/User-Guide.en.md)
- [Deutsche Benutzerdokumentation](docs/User-Guide.de.md)
- [Documentation index](docs/Readme.md)
- [Release process](docs/release-process.md)

## Main Features

- Detects optical I/R reading heads below `/dev/serial/smartmeter/`.
- Generates and validates vzLogger configuration files.
- Supports vzLogger MQTT publishing with a local SmartMeter cache.
- Provides HTTP and UDP output from cached meter values.
- Includes a bridge service for MQTT-to-cache processing.
- Provides diagnostic logging for service state, generated config, channel mapping, bridge logs, cache files, and MQTT parser samples.

## Quick Links

- MQTT topic structure: `<base topic>/<meter>/<value name>`
- Default MQTT base topic: `smartmeter`
- UDP sends the same value set to all configured Miniservers.
- HTTP access remains available through the plugin web frontend.
- vzLogger live readings can optionally be opened through the local vzLogger HTTP daemon.

## Release Notes

See [CHANGELOG.md](CHANGELOG.md) for notable changes and release notes.
