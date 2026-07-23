#!/bin/sh

ARGV0=$0 # Zero argument is shell command
ARGV1=$1 # First argument is temp folder during install
ARGV2=$2 # Second argument is Plugin-Name for scipts etc.
ARGV3=$3 # Third argument is Plugin installation folder
ARGV4=$4 # Forth argument is Plugin version
ARGV5=$5 # Fifth argument is Base folder of LoxBerry

cleanup_obsolete_language_files()
{
	templatefolder="$ARGV5/templates/plugins/$ARGV3"

	for languagefile in \
		"$templatefolder/en/language.txt" \
		"$templatefolder/de/language.txt" \
		"$templatefolder/multi/en/language.txt" \
		"$templatefolder/multi/de/language.txt"
	do
		if [ -e "$languagefile" ]; then
			rm -f "$languagefile"
			echo "<INFO> Removed obsolete language resource: $languagefile"
		fi
	done

	rmdir "$templatefolder/en" "$templatefolder/de" \
		"$templatefolder/multi/en" "$templatefolder/multi/de" 2>/dev/null || true
}

migrate_config()
{
	configfile="$ARGV5/config/plugins/$ARGV3/smartmeter.cfg"

	if ! grep -q '^MQTTTOPIC=' "$configfile"; then
		sed -i '/^UDPPORT=/a MQTTTOPIC=smartmeter' "$configfile"
		echo "<INFO> Added default MQTT topic"
	fi

	# The Legacy implementation was removed. Settings that only drove Legacy
	# polling are dropped, and a stored Legacy mode becomes inactive so the user
	# has to activate vzLogger explicitly.
	if grep -q '^SENDMQTT=' "$configfile"; then
		sed -i '/^SENDMQTT=/d' "$configfile"
		echo "<INFO> Removed obsolete Legacy MQTT send setting"
	fi

	if grep -q '^CRON=' "$configfile"; then
		sed -i '/^CRON=/d' "$configfile"
		echo "<INFO> Removed obsolete Legacy polling interval"
	fi

	if grep -q '^LEGACY_' "$configfile"; then
		sed -i '/^LEGACY_/d' "$configfile"
		echo "<INFO> Removed obsolete Legacy meter settings"
	fi

	if ! grep -q '^IMPLEMENTATION=' "$configfile"; then
		sed -i '/^READ=/a IMPLEMENTATION=none' "$configfile"
		echo "<INFO> Added default implementation mode: none"
	elif grep -q '^IMPLEMENTATION=legacy$' "$configfile"; then
		sed -i 's/^IMPLEMENTATION=legacy$/IMPLEMENTATION=none/' "$configfile"
		echo "<WARNING> The Legacy implementation was removed. Meter reading is now inactive."
		echo "<WARNING> Open the plugin page and activate vzLogger to resume reading."
	fi

	if ! grep -q '^\[VZLOGGER\]' "$configfile"; then
		cat >> "$configfile" <<'EOF'

[VZLOGGER]
LOCALPORT=18080
UDPINTERVAL=5
DEBUG=0
VZLOGGERDEBUG=0
LOGLEVEL=0
EOF
		echo "<INFO> Added default vzLogger settings"
	else
		if ! grep -q '^LOCALPORT=' "$configfile"; then
			sed -i '/^\[VZLOGGER\]/a LOCALPORT=18080' "$configfile"
			echo "<INFO> Added default vzLogger local HTTP port"
		fi
		if ! grep -q '^UDPINTERVAL=' "$configfile"; then
			sed -i '/^\[VZLOGGER\]/a UDPINTERVAL=5' "$configfile"
			echo "<INFO> Added default bridge update interval"
		fi
		if ! grep -q '^DEBUG=' "$configfile"; then
			sed -i '/^\[VZLOGGER\]/a DEBUG=0' "$configfile"
			echo "<INFO> Added default vzLogger debug setting"
		fi
		if ! grep -q '^VZLOGGERDEBUG=' "$configfile"; then
			sed -i '/^\[VZLOGGER\]/a VZLOGGERDEBUG=0' "$configfile"
			echo "<INFO> Added default vzLogger service debug setting"
		fi
		if ! grep -q '^LOGLEVEL=' "$configfile"; then
			sed -i '/^\[VZLOGGER\]/a LOGLEVEL=0' "$configfile"
			echo "<INFO> Added default vzLogger service log level"
		fi
	fi
}

echo "<INFO> Copy back existing config files"
cp -v -r "/tmp/$ARGV1"_upgrade/config/"$ARGV3"/* "$ARGV5/config/plugins/$ARGV3/"

echo "<INFO> Migrate config files"
migrate_config

echo "<INFO> Remove obsolete language resources"
cleanup_obsolete_language_files

echo "<INFO> Ensure executable permissions for vzLogger helper scripts"
chmod +x "$ARGV5/bin/plugins/$ARGV3/vzlogger_config.pl" 2>/dev/null || true
chmod +x "$ARGV5/bin/plugins/$ARGV3/vzlogger_validate.pl" 2>/dev/null || true
chmod +x "$ARGV5/bin/plugins/$ARGV3/vzlogger_control.pl" 2>/dev/null || true
chmod +x "$ARGV5/bin/plugins/$ARGV3/vzlogger_mqtt_bridge.pl" 2>/dev/null || true
chmod +x "$ARGV5/bin/plugins/$ARGV3/install_vzlogger_bridge_service.sh" 2>/dev/null || true
chmod +x "$ARGV5/bin/plugins/$ARGV3/install_vzlogger_service_override.sh" 2>/dev/null || true
chmod +x "$ARGV5/webfrontend/htmlauth/plugins/$ARGV3/vzlogger_live.cgi" 2>/dev/null || true

echo "<INFO> Copy back existing log files"
if [ -d "/tmp/$ARGV1"_upgrade/log/"$ARGV3" ]; then
	for logfile in "/tmp/$ARGV1"_upgrade/log/"$ARGV3"/*
	do
		[ -e "$logfile" ] || continue
		target="$ARGV5/log/plugins/$ARGV3/$(basename "$logfile")"
		rm -rf "$target"
		cp -v -r "$logfile" "$ARGV5/log/plugins/$ARGV3/" || echo "<WARNING> Could not restore log file $logfile"
	done
fi

echo "<INFO> Remove obsolete Legacy polling cronjobs"
for cronfolder in cron.01min cron.03min cron.05min cron.10min cron.15min cron.30min cron.hourly cron.reboot
do
	cronjob="$ARGV5/system/cron/$cronfolder/$ARGV2"
	if [ -e "$cronjob" ] || [ -L "$cronjob" ]; then
		rm -f "$cronjob"
		echo "<INFO> Removed obsolete cronjob: $cronjob"
	fi
done

echo "<INFO> Remove temporary folders"
rm -r "/tmp/$ARGV1"_upgrade

# Exit with Status 0
exit 0
