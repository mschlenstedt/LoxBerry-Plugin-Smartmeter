#!/bin/bash

# Installs and updates the vzlogger package from the Volkszaehler Cloudsmith
# repository, and reports versions for the web interface.
#
# Usage:
#   vzlogger_pkg.sh current     installed version (empty if not installed)
#   vzlogger_pkg.sh available   newest version offered by the repository
#   vzlogger_pkg.sh repo        (re)write keyring and apt source, as root
#   vzlogger_pkg.sh install     install vzlogger, as root
#   vzlogger_pkg.sh upgrade     update vzlogger, as root
#
# Only the vzlogger package is installed. Its dependencies are shared
# libraries; the repository itself contains nothing but vzlogger, libsml and
# libmbus, so no other Volkszaehler component is pulled in.
#
# The package ships a systemd unit and an init script and its postinst enables
# and starts them. This plugin runs vzlogger from its own watchdog instead, so
# the service is prevented from starting during installation and is disabled
# and masked afterwards. That has to be repeated after every package upgrade
# because the postinst unmasks the unit again.

set -u

ACTION="${1:-}"
KEYRING="/usr/share/keyrings/volkszaehler-volkszaehler-org-project-archive-keyring.gpg"
SOURCE_LIST="/etc/apt/sources.list.d/volkszaehler-volkszaehler-org-project.list"
REPO_BASE="https://dl.cloudsmith.io/public/volkszaehler/volkszaehler-org-project"
KEY_URL="$REPO_BASE/gpg.21DBDAC56DF44DA1.key"
POLICY_FILE="/usr/sbin/policy-rc.d"
POLICY_BACKUP="/usr/sbin/policy-rc.d.smartmeter-ng"

installed_version()
{
	dpkg-query -W -f='${Version}' vzlogger 2>/dev/null | grep -v '^$' || true
}

available_version()
{
	apt-cache policy vzlogger 2>/dev/null | awk '/Candidate:/ {print $2}' | grep -v '(none)' || true
}

require_root()
{
	if [ "$(id -u)" != "0" ]; then
		echo "<ERROR> This action has to run as root."
		exit 1
	fi
}

# Writes the keyring and the apt source. Run on every install and upgrade so a
# rotated repository key cannot lock the plugin out of updates.
configure_repository()
{
	require_root

	if ! command -v curl >/dev/null 2>&1 || ! command -v gpg >/dev/null 2>&1; then
		echo "<INFO> Installing apt helper packages"
		apt-get update
		apt-get install -y --no-install-recommends ca-certificates curl gnupg
	fi

	if [ -r /etc/os-release ]; then
		. /etc/os-release
	else
		ID="debian"
		VERSION_CODENAME=""
	fi
	CODENAME="${VERSION_CODENAME:-}"
	if [ -z "$CODENAME" ] && command -v lsb_release >/dev/null 2>&1; then
		CODENAME="$(lsb_release -sc)"
	fi
	if [ -z "$CODENAME" ]; then
		echo "<ERROR> Could not determine the Debian/Raspberry Pi OS codename."
		exit 3
	fi
	REPO_OS="debian"
	[ "${ID:-debian}" = "raspbian" ] && REPO_OS="raspbian"

	tmpkey="$(mktemp)"
	trap 'rm -f "$tmpkey"' EXIT
	echo "<INFO> Refreshing the Volkszaehler repository key"
	if ! curl -fsSL "$KEY_URL" -o "$tmpkey"; then
		echo "<ERROR> Could not download the repository key from $KEY_URL"
		exit 3
	fi
	if ! gpg --dearmor <"$tmpkey" >"$KEYRING.new"; then
		echo "<ERROR> Could not convert the repository key"
		rm -f "$KEYRING.new"
		exit 3
	fi
	mv "$KEYRING.new" "$KEYRING"
	chmod 0644 "$KEYRING"

	# No deb-src entry: the plugin never builds from source, and the extra
	# index would only slow down (or break) apt update.
	echo "<INFO> Configuring the Volkszaehler apt source for $REPO_OS $CODENAME"
	printf 'deb [signed-by=%s] %s/deb/%s %s main\n' "$KEYRING" "$REPO_BASE" "$REPO_OS" "$CODENAME" >"$SOURCE_LIST"
	chmod 0644 "$SOURCE_LIST"
}

# Prevents the package scripts from starting the service during installation.
block_service_start()
{
	[ -e "$POLICY_FILE" ] && mv "$POLICY_FILE" "$POLICY_BACKUP"
	printf '#!/bin/sh\nexit 101\n' >"$POLICY_FILE"
	chmod 0755 "$POLICY_FILE"
}

unblock_service_start()
{
	rm -f "$POLICY_FILE"
	[ -e "$POLICY_BACKUP" ] && mv "$POLICY_BACKUP" "$POLICY_FILE"
	return 0
}

# The plugin starts vzlogger from its watchdog, so the packaged service must
# not run. The postinst re-enables and unmasks it, so this runs after every
# install and upgrade.
disable_packaged_service()
{
	if command -v systemctl >/dev/null 2>&1; then
		systemctl stop vzlogger.service >/dev/null 2>&1 || true
		systemctl disable vzlogger.service >/dev/null 2>&1 || true
		systemctl mask vzlogger.service >/dev/null 2>&1 || true
		systemctl reset-failed vzlogger.service >/dev/null 2>&1 || true
	fi
	if command -v update-rc.d >/dev/null 2>&1 && [ -e /etc/init.d/vzlogger ]; then
		update-rc.d vzlogger disable >/dev/null 2>&1 || true
	fi
	echo "<INFO> The packaged vzlogger service is disabled; the plugin watchdog starts vzlogger."
}

install_package()
{
	require_root
	configure_repository

	echo "<INFO> Updating package lists"
	apt-get update

	oldversion="$(installed_version)"
	block_service_start
	echo "<INFO> Installing vzlogger"
	if ! DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends vzlogger; then
		unblock_service_start
		echo "<ERROR> Could not install vzlogger"
		exit 4
	fi
	unblock_service_start
	disable_packaged_service

	if [ ! -x /usr/bin/vzlogger ]; then
		echo "<ERROR> vzlogger was installed but /usr/bin/vzlogger is missing"
		exit 4
	fi
	newversion="$(installed_version)"
	if [ -n "$oldversion" ] && [ "$oldversion" = "$newversion" ]; then
		echo "<OK> vzlogger $newversion is already up to date"
	else
		echo "<OK> vzlogger $newversion installed"
	fi
}

case "$ACTION" in
	current)
		installed_version
		;;
	available)
		available_version
		;;
	repo)
		configure_repository
		echo "<OK> Repository configured"
		;;
	install|upgrade)
		install_package
		;;
	*)
		echo "Usage: $0 current|available|repo|install|upgrade"
		exit 2
		;;
esac
exit 0
