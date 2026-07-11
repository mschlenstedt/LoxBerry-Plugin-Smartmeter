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
PREUPGRADE_ACTIVE_FILE="$ARGV5/config/plugins/$ARGV3/vzlogger.preupgrade-service-active"

if [ "$(id -u)" != "0" ]; then
	echo "<ERROR> postroot.sh must run as root."
	exit 2
fi

implementation=""
read_enabled=""
if [ -f "$CONFIG_FILE" ]; then
	implementation=$(sed -n 's/^IMPLEMENTATION=//p' "$CONFIG_FILE" | tail -n 1)
	read_enabled=$(sed -n 's/^READ=//p' "$CONFIG_FILE" | tail -n 1)
fi

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

if [ "$implementation" = "vzlogger" ] && [ "$read_enabled" = "1" ]; then
	refresh_bridge_service
	was_active_before_upgrade=0
	if [ -f "$PREUPGRADE_ACTIVE_FILE" ]; then
		was_active_before_upgrade=1
	fi
	rm -f "$PREUPGRADE_ACTIVE_FILE"
	if [ -x "$VZLOGGER_CONTROL" ]; then
		if [ "$was_active_before_upgrade" = "1" ]; then
			echo "<INFO> vzLogger was active before upgrade. Applying configuration and restarting services."
		else
			echo "<INFO> vzLogger mode is active. Applying configuration and restarting services."
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

if command -v systemctl >/dev/null 2>&1; then
	if systemctl list-unit-files "$BRIDGE_SERVICE" >/dev/null 2>&1; then
		refresh_bridge_service
	fi

	if systemctl list-unit-files vzlogger.service >/dev/null 2>&1; then
		echo "<INFO> Legacy mode or meter reading disabled. Stopping and disabling vzLogger service."
		systemctl stop vzlogger.service >/dev/null 2>&1 || true
		systemctl disable vzlogger.service >/dev/null 2>&1 || true
		systemctl reset-failed vzlogger.service >/dev/null 2>&1 || true
	else
		echo "<INFO> vzLogger service is not installed."
	fi
	if systemctl list-unit-files "$BRIDGE_SERVICE" >/dev/null 2>&1; then
		echo "<INFO> Stopping MQTT bridge because vzLogger meter reading is disabled."
		systemctl stop "$BRIDGE_SERVICE" >/dev/null 2>&1 || true
		systemctl reset-failed "$BRIDGE_SERVICE" >/dev/null 2>&1 || true
	fi
else
	echo "<INFO> systemctl is not available. Skipping vzLogger service handling."
fi

exit 0
