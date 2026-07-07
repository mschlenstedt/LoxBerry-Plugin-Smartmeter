#!/bin/sh

set -eu

KEYRING="/usr/share/keyrings/volkszaehler-volkszaehler-org-project-archive-keyring.gpg"
SOURCE_LIST="/etc/apt/sources.list.d/volkszaehler-volkszaehler-org-project.list"
REPO_BASE="https://dl.cloudsmith.io/public/volkszaehler/volkszaehler-org-project"
KEY_URL="$REPO_BASE/gpg.21DBDAC56DF44DA1.key"

if [ "$(id -u)" != "0" ]; then
	echo "<ERROR> This script must run as root to configure apt sources and install packages."
	exit 2
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
	echo "<ERROR> Could not determine Debian/Raspberry Pi OS codename."
	exit 3
fi

REPO_OS="debian"
case "${ID:-debian}" in
	raspbian)
		REPO_OS="raspbian"
		;;
esac

echo "<INFO> Installing apt helper packages"
apt-get update
apt-get install -y ca-certificates curl gnupg

tmpkey="$(mktemp)"
trap 'rm -f "$tmpkey"' EXIT

echo "<INFO> Installing Volkszaehler repository key"
curl -fsSL "$KEY_URL" -o "$tmpkey"
gpg --dearmor < "$tmpkey" > "$KEYRING"
chmod 0644 "$KEYRING"

echo "<INFO> Configuring Volkszaehler apt repository for $REPO_OS $CODENAME"
cat > "$SOURCE_LIST" <<EOF
deb [signed-by=$KEYRING] $REPO_BASE/deb/$REPO_OS $CODENAME main
deb-src [signed-by=$KEYRING] $REPO_BASE/deb/$REPO_OS $CODENAME main
EOF

apt-get update

echo "<INFO> Installing vzlogger and mosquitto-clients"
apt-get install -y vzlogger mosquitto-clients

echo "<OK> vzLogger package installation finished"
