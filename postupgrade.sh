#!/bin/sh

ARGV0=$0 # Zero argument is shell command
ARGV1=$1 # First argument is temp folder during install
ARGV2=$2 # Second argument is Plugin-Name for scipts etc.
ARGV3=$3 # Third argument is Plugin installation folder
ARGV4=$4 # Forth argument is Plugin version
ARGV5=$5 # Fifth argument is Base folder of LoxBerry

remove_cronjobs()
{
	for cronfolder in cron.01min cron.03min cron.05min cron.10min cron.15min cron.30min cron.hourly cron.reboot
	do
		rm -f "$ARGV5/system/cron/$cronfolder/$ARGV2"
	done
}

create_cronjob()
{
	cronfolder=$1
	scriptname=$2

	ln -s "$ARGV5/bin/plugins/$ARGV3/$scriptname" "$ARGV5/system/cron/$cronfolder/$ARGV2"
}

restore_cronjob()
{
	configfile="$ARGV5/config/plugins/$ARGV3/smartmeter.cfg"
	read_enabled=$(sed -n 's/^READ=//p' "$configfile")
	cron_interval=$(sed -n 's/^CRON=//p' "$configfile")
	implementation=$(sed -n 's/^IMPLEMENTATION=//p' "$configfile")

	remove_cronjobs

	if [ "$implementation" = "vzlogger" ]; then
		echo "<INFO> vzLogger mode is active. No legacy cronjob restored."
		return
	fi

	if [ "$read_enabled" != "1" ]; then
		echo "<INFO> Automatic meter polling is disabled. No cronjob restored."
		return
	fi

	case "$cron_interval" in
		M)
			create_cronjob "cron.reboot" "reboot_cron_runner.sh"
			echo "<INFO> Restored automatic meter polling cronjob: reboot"
			;;
		1)
			create_cronjob "cron.01min" "fetch.pl"
			echo "<INFO> Restored automatic meter polling cronjob: 1 minute"
			;;
		3)
			create_cronjob "cron.03min" "fetch.pl"
			echo "<INFO> Restored automatic meter polling cronjob: 3 minutes"
			;;
		5)
			create_cronjob "cron.05min" "fetch.pl"
			echo "<INFO> Restored automatic meter polling cronjob: 5 minutes"
			;;
		10)
			create_cronjob "cron.10min" "fetch.pl"
			echo "<INFO> Restored automatic meter polling cronjob: 10 minutes"
			;;
		15)
			create_cronjob "cron.15min" "fetch.pl"
			echo "<INFO> Restored automatic meter polling cronjob: 15 minutes"
			;;
		30)
			create_cronjob "cron.30min" "fetch.pl"
			echo "<INFO> Restored automatic meter polling cronjob: 30 minutes"
			;;
		60)
			create_cronjob "cron.hourly" "fetch.pl"
			echo "<INFO> Restored automatic meter polling cronjob: hourly"
			;;
		*)
			echo "<WARNING> Unknown cron interval '$cron_interval'. No cronjob restored."
			;;
	esac
}

migrate_config()
{
	configfile="$ARGV5/config/plugins/$ARGV3/smartmeter.cfg"

	if ! grep -q '^SENDMQTT=' "$configfile"; then
		sed -i '/^UDPPORT=/a SENDMQTT=0' "$configfile"
		echo "<INFO> Added default MQTT send setting"
	fi

	if ! grep -q '^MQTTTOPIC=' "$configfile"; then
		sed -i '/^SENDMQTT=/a MQTTTOPIC=smartmeter' "$configfile"
		echo "<INFO> Added default MQTT topic"
	fi

	if ! grep -q '^IMPLEMENTATION=' "$configfile"; then
		read_enabled=$(sed -n 's/^READ=//p' "$configfile")
		if [ "$read_enabled" = "1" ]; then
			sed -i '/^READ=/a IMPLEMENTATION=legacy' "$configfile"
			echo "<INFO> Added default implementation mode: legacy"
		else
			sed -i '/^READ=/a IMPLEMENTATION=vzlogger' "$configfile"
			echo "<INFO> Added default implementation mode: vzlogger"
		fi
	fi

	if ! grep -q '^\[VZLOGGER\]' "$configfile"; then
		cat >> "$configfile" <<'EOF'

[VZLOGGER]
LOCALPORT=18080
UDPINTERVAL=5
DEBUG=0
VZLOGGERDEBUG=0
LOGLEVEL=5
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
			sed -i '/^\[VZLOGGER\]/a LOGLEVEL=5' "$configfile"
			echo "<INFO> Added default vzLogger service log level"
		fi
	fi
}

echo "<INFO> Copy back existing config files"
cp -v -r "/tmp/$ARGV1"_upgrade/config/"$ARGV3"/* "$ARGV5/config/plugins/$ARGV3/"

echo "<INFO> Migrate config files"
migrate_config

echo "<INFO> Ensure executable permissions for vzLogger helper scripts"
chmod +x "$ARGV5/bin/plugins/$ARGV3/vzlogger_config.pl" 2>/dev/null || true
chmod +x "$ARGV5/bin/plugins/$ARGV3/vzlogger_validate.pl" 2>/dev/null || true
chmod +x "$ARGV5/bin/plugins/$ARGV3/vzlogger_control.pl" 2>/dev/null || true
chmod +x "$ARGV5/bin/plugins/$ARGV3/vzlogger_mqtt_bridge.pl" 2>/dev/null || true
chmod +x "$ARGV5/bin/plugins/$ARGV3/install_vzlogger_bridge_service.sh" 2>/dev/null || true
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

echo "<INFO> Restore automatic meter polling cronjob"
restore_cronjob

echo "<INFO> Remove temporary folders"
rm -r "/tmp/$ARGV1"_upgrade

# Exit with Status 0
exit 0
