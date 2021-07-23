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

/bin/sed -i "s#REPLACEBYSUBFOLDER#$ARGV3#" $ARGV5/config/plugins/$ARGV3/smartmeter.cfg
/bin/sed -i "s#REPLACEBYNAME#$ARGV2#" $ARGV5/config/plugins/$ARGV3/smartmeter.cfg
/bin/sed -i "s#REPLACEBYSUBFOLDER#$ARGV3#" $ARGV5/system/daemons/plugins/$ARGV2
/bin/sed -i "s#REPLACEBYBASEFOLDER#$ARGV5#" $ARGV5/system/daemons/plugins/$ARGV2

echo "<INFO> Rename htaccess to .htaccess"
mv $ARGV5/webfrontend/htmlauth/plugins/$ARGV3/htaccess $ARGV5/webfrontend/htmlauth/plugins/$ARGV3/.htaccess

echo "<INFO> *******************************************************************"
echo "<INFO> * Please reboot your LoxBerry to initialize the Smartmeter Plugin *"
echo "<INFO> *******************************************************************"

# Exit with Status 0
exit 0
