#!/bin/sh

# Runs as root after LoxBerry has installed dependencies and executed the
# normal postinstall/postupgrade scripts. Keep vzLogger stopped unless the
# plugin configuration explicitly enables the vzLogger implementation.

ARGV3=$3
ARGV5=$5

CONFIG_FILE="$ARGV5/config/plugins/$ARGV3/smartmeter.cfg"
BRIDGE_SERVICE="smartmeter-v2-vzlogger-bridge.service"
BRIDGE_INSTALLER="$ARGV5/bin/plugins/$ARGV3/install_vzlogger_bridge_service.sh"
VZLOGGER_CONTROL="$ARGV5/bin/plugins/$ARGV3/vzlogger_control.pl"
VZLOGGER_OVERRIDE_INSTALLER="$ARGV5/bin/plugins/$ARGV3/install_vzlogger_service_override.sh"
PREUPGRADE_ACTIVE_FILE="$ARGV5/config/plugins/$ARGV3/vzlogger.preupgrade-service-active"
SMARTMETER_LOG_DIR="$ARGV5/log/plugins/$ARGV3"
SMARTMETER_LOG_FILE="$SMARTMETER_LOG_DIR/smartmeter.log"
SMARTMETER_UDEV_RULE="/etc/udev/rules.d/99-smartmeter.rules"
RUNTIME_DIR="/var/run/shm/$ARGV3"
PLUGIN_CONFIG_DIR="$ARGV5/config/plugins/$ARGV3"

if [ "$(id -u)" != "0" ]; then
	echo "<ERROR> postroot.sh must run as root."
	exit 2
fi

implementation=""
if [ -f "$CONFIG_FILE" ]; then
	implementation=$(sed -n 's/^IMPLEMENTATION=//p' "$CONFIG_FILE" | tail -n 1)
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

refresh_bridge_service()
{
	if [ ! -x "$BRIDGE_INSTALLER" ]; then
		echo "<WARNING> vzLogger bridge service installer is missing or not executable."
		return
	fi

	echo "<INFO> Refresh vzLogger bridge systemd service"
	if /bin/sh "$BRIDGE_INSTALLER" "$ARGV5" "$ARGV3" install; then
		echo "<INFO> Refreshed vzLogger bridge systemd service"
	else
		echo "<WARNING> Could not refresh vzLogger bridge systemd service"
	fi
}

has_configured_vzlogger_meter()
{
	if [ ! -f "$CONFIG_FILE" ]; then
		return 1
	fi

	grep -q '^METER=[^0][^[:space:]]*' "$CONFIG_FILE"
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
	was_active_before_upgrade=0
	if [ -f "$PREUPGRADE_ACTIVE_FILE" ]; then
		was_active_before_upgrade=1
	fi
	rm -f "$PREUPGRADE_ACTIVE_FILE"
	if [ -x "$VZLOGGER_CONTROL" ]; then
		if [ "$was_active_before_upgrade" = "1" ]; then
			echo "<INFO> vzLogger was active before upgrade. Applying configuration and restarting configured services."
		else
			echo "<INFO> vzLogger mode is active. Applying configuration and restarting configured services."
		fi
		if "$VZLOGGER_CONTROL" apply; then
			echo "<INFO> Applied active vzLogger configuration after install or upgrade."
		else
			echo "<WARNING> Could not apply active vzLogger configuration after install or upgrade."
		fi
	else
		echo "<WARNING> vzLogger control helper is missing or not executable."
	fi
	exit 0
fi

rm -f "$PREUPGRADE_ACTIVE_FILE"

if [ -f "$VZLOGGER_OVERRIDE_INSTALLER" ]; then
	/bin/sh "$VZLOGGER_OVERRIDE_INSTALLER" "$ARGV5" "$ARGV3" remove || \
		echo "<WARNING> Could not remove SmartMeter vzLogger service override"
fi

if command -v systemctl >/dev/null 2>&1; then
	if systemctl list-unit-files "$BRIDGE_SERVICE" >/dev/null 2>&1; then
		refresh_bridge_service
	fi

	if systemctl list-unit-files vzlogger.service >/dev/null 2>&1; then
		if [ "$implementation" = "vzlogger" ]; then
			echo "<INFO> vzLogger mode is active but no meter is configured. Stopping and disabling vzLogger service."
		else
			echo "<INFO> Legacy mode is active. Stopping and disabling vzLogger service."
		fi
		systemctl stop vzlogger.service >/dev/null 2>&1 || true
		systemctl disable vzlogger.service >/dev/null 2>&1 || true
		systemctl reset-failed vzlogger.service >/dev/null 2>&1 || true
	else
		echo "<INFO> vzLogger service is not installed."
	fi
	if systemctl list-unit-files "$BRIDGE_SERVICE" >/dev/null 2>&1; then
		if [ "$implementation" = "vzlogger" ]; then
			echo "<INFO> Stopping MQTT bridge because no vzLogger meter is configured."
		else
			echo "<INFO> Stopping MQTT bridge because vzLogger mode is disabled."
		fi
		systemctl stop "$BRIDGE_SERVICE" >/dev/null 2>&1 || true
		systemctl reset-failed "$BRIDGE_SERVICE" >/dev/null 2>&1 || true
	fi
else
	echo "<INFO> systemctl is not available. Skipping vzLogger service handling."
fi

exit 0
