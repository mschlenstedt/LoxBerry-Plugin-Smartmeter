# SmartMeter v2 Documentation

SmartMeter v2 is a LoxBerry plugin for reading smart meters with optical I/R reading heads. The legacy configuration can periodically read meter values and make them available by HTTP, UDP, and MQTT.

Choose your language:

- [English user guide](User-Guide.en.md)
- [Deutsche Benutzerdokumentation](User-Guide.de.md)

## Quick Links

- MQTT topic structure: `<base topic>/<meter>/<value name>`
- Default MQTT base topic: `smartmeter`
- UDP sends the same value set to all configured Miniservers.
- HTTP access remains available through the plugin web frontend.
