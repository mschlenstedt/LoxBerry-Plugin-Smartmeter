#!/bin/sh

set -eu

LBHOMEDIR="${1:-}"
PLUGINFOLDER="${2:-}"
ACTION="${3:-install}"

if [ -z "$LBHOMEDIR" ] || [ -z "$PLUGINFOLDER" ]; then
	echo "<ERROR> Usage: $0 <lbhomedir> <pluginfolder> [install|remove]"
	exit 2
fi

if [ "$(id -u)" != "0" ]; then
	echo "<ERROR> This script must run as root to manage systemd overrides."
	exit 2
fi

DROPIN_DIR="/etc/systemd/system/vzlogger.service.d"
DROPIN_FILE="$DROPIN_DIR/smartmeter-v2.conf"
CONFIG_FILE="$LBHOMEDIR/config/plugins/$PLUGINFOLDER/vzlogger.conf"
LEGACY_CONFIG="/etc/vzlogger.conf"
LEGACY_MARKER="/etc/vzlogger.conf.smartmeter-v2"

remove_legacy_config_copy()
{
	if [ -f "$LEGACY_MARKER" ]; then
		rm -f "$LEGACY_CONFIG" "$LEGACY_MARKER"
		echo "<INFO> Removed previous SmartMeter-managed /etc/vzlogger.conf copy"
	fi
}

if [ "$ACTION" = "remove" ]; then
	rm -f "$DROPIN_FILE"
	rmdir "$DROPIN_DIR" >/dev/null 2>&1 || true
	remove_legacy_config_copy
	if command -v systemctl >/dev/null 2>&1; then
		systemctl daemon-reload
	fi
	echo "<OK> Removed SmartMeter vzLogger service override"
	exit 0
fi

if [ "$ACTION" != "install" ]; then
	echo "<ERROR> Unsupported action: $ACTION"
	exit 2
fi

if [ ! -f "$CONFIG_FILE" ]; then
	echo "<ERROR> Missing vzLogger configuration: $CONFIG_FILE"
	exit 3
fi

VZLOGGER_BIN=$(command -v vzlogger || true)
if [ -z "$VZLOGGER_BIN" ] || [ ! -x "$VZLOGGER_BIN" ]; then
	echo "<ERROR> vzlogger executable not found"
	exit 3
fi

mkdir -p "$DROPIN_DIR"
{
	echo "[Service]"
	echo "Type=simple"
	echo "PIDFile="
	echo "RemainAfterExit=no"
	echo "ExecStart="
	printf 'ExecStart=%s -f -c %s\n' "$VZLOGGER_BIN" "$CONFIG_FILE"
	echo "ExecStop="
	echo "ExecReload="
	echo "User=_vzlogger"
	echo "Restart=on-failure"
	echo "RestartSec=5s"
} > "$DROPIN_FILE"
chmod 0644 "$DROPIN_FILE"
remove_legacy_config_copy

if command -v systemctl >/dev/null 2>&1; then
	systemctl daemon-reload
	echo "<OK> Installed SmartMeter vzLogger service override for $CONFIG_FILE"
else
	echo "<WARNING> systemctl is not available. Override was written but not loaded."
fi
