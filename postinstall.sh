#!/bin/sh

# Bashscript which is executed by bash *AFTER* complete installation is done
# (but *BEFORE* postupdate). Use with caution and remember, that all systems
# may be different! Better to do this in your own Pluginscript if possible.
#
# Exit code must be 0 if executed successfull.
#
# Will be executed as user "loxberry".
#
# We add 5 arguments when executing the script:
# command <TEMPFOLDER> <NAME> <FOLDER> <VERSION> <BASEFOLDER>

ARGV2=$2 # Second argument is Plugin-Name for scipts etc.
ARGV3=$3 # Third argument is Plugin installation folder
ARGV5=$5 # Fifth argument is Base folder of LoxBerry

/bin/sed -i "s#REPLACEBYSUBFOLDER#$ARGV3#" $ARGV5/config/plugins/$ARGV3/smartmeter.json
/bin/sed -i "s#REPLACEBYNAME#$ARGV2#" $ARGV5/config/plugins/$ARGV3/smartmeter.json
/bin/chmod +x $ARGV5/bin/plugins/$ARGV3/vzlogger_config.pl
/bin/chmod +x $ARGV5/bin/plugins/$ARGV3/migrate_config.pl
/bin/chmod +x $ARGV5/bin/plugins/$ARGV3/config_value.pl
/bin/chmod +x $ARGV5/bin/plugins/$ARGV3/vzlogger_validate.pl
/bin/chmod +x $ARGV5/bin/plugins/$ARGV3/vzlogger_control.pl
/bin/chmod +x $ARGV5/bin/plugins/$ARGV3/vzlogger_mqtt_bridge.pl
/bin/chmod +x $ARGV5/bin/plugins/$ARGV3/install_vzlogger_bridge_service.sh
/bin/chmod +x $ARGV5/bin/plugins/$ARGV3/install_vzlogger_service_override.sh
/bin/chmod +x $ARGV5/webfrontend/htmlauth/plugins/$ARGV3/vzlogger_live.cgi
/bin/chmod +x $ARGV5/webfrontend/htmlauth/plugins/$ARGV3/vzlogger_config.cgi

echo "<INFO> Rename htaccess to .htaccess"
mv $ARGV5/webfrontend/htmlauth/plugins/$ARGV3/htaccess $ARGV5/webfrontend/htmlauth/plugins/$ARGV3/.htaccess

echo "<INFO> vzLogger package is installed through LoxBerry dpkg/apt dependencies."

if command -v mosquitto_sub >/dev/null 2>&1; then
	echo "<INFO> mosquitto_sub found for MQTT bridge."
else
	echo "<WARNING> mosquitto_sub is not available. Install mosquitto-clients for HTTP/UDP cache updates from vzLogger MQTT."
fi

echo "<INFO> ***********************************************************************"
echo "<INFO> * Please reboot your LoxBerry to initialize the Smartmeter-NG Plugin  *"
echo "<INFO> ***********************************************************************"

# Exit with Status 0
exit 0
