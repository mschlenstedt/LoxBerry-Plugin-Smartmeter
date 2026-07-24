#!/bin/sh

# Runs as root after LoxBerry has installed dependencies and executed the
# normal postinstall/postupgrade scripts. Keep vzLogger stopped unless the
# plugin configuration explicitly enables the vzLogger implementation.

ARGV3=$3
ARGV5=$5

CONFIG_FILE="$ARGV5/config/plugins/$ARGV3/smartmeter.json"
CONFIG_READER="$ARGV5/bin/plugins/$ARGV3/config_value.pl"
PACKAGE_HELPER="$ARGV5/bin/plugins/$ARGV3/vzlogger_pkg.sh"
VZLOGGER_CONTROL="$ARGV5/bin/plugins/$ARGV3/vzlogger_control.pl"
WATCHDOG="$ARGV5/bin/plugins/$ARGV3/watchdog.pl"
SMARTMETER_LOG_DIR="$ARGV5/log/plugins/$ARGV3"
SMARTMETER_LOG_FILE="$SMARTMETER_LOG_DIR/smartmeter.log"
SMARTMETER_UDEV_RULE="/etc/udev/rules.d/99-smartmeter.rules"
RUNTIME_DIR="/var/run/shm/$ARGV3"
PLUGIN_CONFIG_DIR="$ARGV5/config/plugins/$ARGV3"

if [ "$(id -u)" != "0" ]; then
	echo "<ERROR> postroot.sh must run as root."
	exit 2
fi

# vzlogger is installed here rather than through dpkg/apt so the plugin owns
# the apt call: the packaged service is kept from starting and is disabled
# afterwards, because the plugin runs vzlogger from its own watchdog.
if [ -x "$PACKAGE_HELPER" ]; then
	chmod +x "$PACKAGE_HELPER" 2>/dev/null || true
	if ! "$PACKAGE_HELPER" install; then
		echo "<WARNING> Could not install vzlogger. Use the update button on the plugin page to retry."
	fi
else
	echo "<ERROR> vzlogger package helper is missing: $PACKAGE_HELPER"
fi

implementation=""
if [ -f "$CONFIG_FILE" ] && [ -x "$CONFIG_READER" ]; then
	implementation=$("$CONFIG_READER" "$CONFIG_FILE" MAIN.IMPLEMENTATION 2>/dev/null)
fi

install_ir_head_udev_rule()
{
	mkdir -p "$SMARTMETER_LOG_DIR"

	echo "<INFO> Installing SmartMeter I/R head udev rule."
	echo "$(date) - Creating UDEV rule for I/R heads: $SMARTMETER_UDEV_RULE" >>"$SMARTMETER_LOG_FILE"
	printf '%s\n' "# LoxBerry SML-eMon Plugin device rule file - DO NOT EDIT BY HAND!" >"$SMARTMETER_UDEV_RULE"
	printf '%s\n' "KERNEL==\"ttyUSB[0-9]*\",GROUP=\"loxberry\",MODE=\"0660\",SYMLINK+=\"serial/smartmeter/\$env{ID_SERIAL_SHORT}\"" >>"$SMARTMETER_UDEV_RULE"

	if command -v udevadm >/dev/null 2>&1; then
		echo "$(date) - Reload udev rules and trigger devices." >>"$SMARTMETER_LOG_FILE"
		if udevadm control --reload-rules >>"$SMARTMETER_LOG_FILE" 2>&1 && udevadm trigger >>"$SMARTMETER_LOG_FILE" 2>&1; then
			echo "<INFO> SmartMeter I/R head udev rule installed and triggered."
		else
			echo "<WARNING> SmartMeter I/R head udev rule was written, but udev reload/trigger failed."
		fi
	else
		echo "<WARNING> udevadm is not available. SmartMeter I/R head rule was written but not triggered."
	fi
}

has_configured_vzlogger_meter()
{
	if [ ! -f "$CONFIG_FILE" ] || [ ! -x "$CONFIG_READER" ]; then
		return 1
	fi

	"$CONFIG_READER" "$CONFIG_FILE" --has-meter
}

install_ir_head_udev_rule
mkdir -p "$RUNTIME_DIR"
chown loxberry:loxberry "$RUNTIME_DIR"
chmod 0750 "$RUNTIME_DIR"
find "$RUNTIME_DIR" -maxdepth 1 -type f -exec chown loxberry:loxberry {} \; -exec chmod 0640 {} \;
for PRIVATE_FILE in \
	"$PLUGIN_CONFIG_DIR/vzlogger_channels.json" \
	"$PLUGIN_CONFIG_DIR/vzlogger_channel_definitions.json" \
	"$PLUGIN_CONFIG_DIR"/vzlogger_user_channel_uuids_*.json \
	"$PLUGIN_CONFIG_DIR"/vzlogger_meter_*.jsonc
do
	if [ -f "$PRIVATE_FILE" ]; then
		chown loxberry:loxberry "$PRIVATE_FILE"
		chmod 0600 "$PRIVATE_FILE"
	fi
done

if [ "$implementation" = "vzlogger" ] && has_configured_vzlogger_meter; then
	if [ -x "$VZLOGGER_CONTROL" ]; then
		echo "<INFO> vzLogger mode is active. Applying the configuration and starting vzlogger."
		if su loxberry -c "$VZLOGGER_CONTROL apply"; then
			echo "<INFO> Applied the active vzLogger configuration."
		else
			echo "<WARNING> Could not apply the active vzLogger configuration."
		fi
	else
		echo "<WARNING> vzLogger control helper is missing or not executable."
	fi
	exit 0
fi

# Meter reading is inactive: make sure no vzlogger process is left running.
if [ -x "$WATCHDOG" ]; then
	su loxberry -c "$WATCHDOG --action=stop" >/dev/null 2>&1 || true
	echo "<INFO> Meter reading is inactive. vzlogger is stopped."
fi

exit 0
