#!/bin/sh

# Runs as root before LoxBerry processes dpkg/apt dependencies.
#
# vzlogger itself is not part of dpkg/apt: it is installed by
# bin/vzlogger_pkg.sh from postroot.sh, so the plugin controls the apt call and
# can keep the packaged service from starting. This script only records whether
# vzlogger was already present, because the uninstall must not purge a package
# that the user installed independently.

ARGV3=$3
ARGV5=$5

MARKER_DIR="$ARGV5/config/plugins/$ARGV3"
MARKER_FILE="$MARKER_DIR/vzlogger.installed-by-plugin"

if [ "$(id -u)" != "0" ]; then
	echo "<ERROR> preroot.sh must run as root."
	exit 2
fi

mkdir -p "$MARKER_DIR"

if dpkg-query -W -f='${Status}' vzlogger 2>/dev/null | grep -q "install ok installed"; then
	echo "<INFO> vzLogger is already installed. Keeping existing package ownership."
else
	touch "$MARKER_FILE"
	echo "<INFO> Marked vzLogger for plugin-managed installation."
fi

if id loxberry >/dev/null 2>&1; then
	chown -R loxberry:loxberry "$MARKER_DIR"
	chmod u+rwX,go+rX "$MARKER_DIR"
fi

exit 0
