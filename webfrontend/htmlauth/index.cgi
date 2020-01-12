#!/usr/bin/perl

# Copyright 2019 Michael Schlenstedt, michael@loxberry.de
#                Christian Fenzl, christian@loxberry.de
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


##########################################################################
# Modules
##########################################################################

# use Config::Simple '-strict';
# use CGI::Carp qw(fatalsToBrowser);
use CGI;
use LoxBerry::System;
#use LoxBerry::Web;
use LoxBerry::JSON; # Available with LoxBerry 2.0
#require "$lbpbindir/libs/LoxBerry/JSON.pm";
use LoxBerry::Log;
use Time::HiRes qw ( sleep );
use warnings;
use strict;
use Data::Dumper;

##########################################################################
# Variables
##########################################################################

my $log;

# Read Form
my $cgi = CGI->new;
my $q = $cgi->Vars;

my $version = LoxBerry::System::pluginversion();
my $template;

# Language Phrases
my %L;

# Globals 
my %pids;
my $CFGFILEDEVICES = $lbpconfigdir . "/devices.json";
my $CFGFILEMQTT = $lbpconfigdir . "/mqtt.json";
my $CFGFILEOWFS = $lbpconfigdir . "/owfs.json";

##########################################################################
# AJAX
##########################################################################

if( $q->{ajax} ) {
	
	## Handle all ajax requests 
	require JSON;
	# require Time::HiRes;
	my %response;
	ajax_header();

	# Save MQTT Settings
	if( $q->{ajax} eq "savemqtt" ) {
		$response{error} = &savemqtt();
		print JSON->new->canonical(1)->encode(\%response);
	}
	
	# Save OWFS Settings
	if( $q->{ajax} eq "saveowfs" ) {
		$response{error} = &saveowfs();
		print JSON->new->canonical(1)->encode(\%response);
	}
	
	# Save Device Settings
	if( $q->{ajax} eq "savedevice" ) {
		$response{error} = &savedevice();
		print JSON->new->canonical(1)->encode(\%response);
	}


	# Get pids
	if( $q->{ajax} eq "getpids" ) {
		pids();
		$response{pids} = \%pids;
		print JSON->new->canonical(1)->encode(\%response);
	}
	
	# Get config
	if( $q->{ajax} eq "getconfig" ) {
		my $content;
		if ( !$q->{config} ) {
			$response{error} = "1";
			$response{message} = "No config given";
		}
		elsif ( !-e $lbpconfigdir . "/" . $q->{config} . ".json" ) {
			$response{error} = "1";
			$response{message} = "Config file does not exist";
		}
		else {
			# Config
			my $cfgfile = $lbpconfigdir . "/" . $q->{config} . ".json";
			$content = LoxBerry::System::read_file("$cfgfile");
			print $content;
		}
		print JSON->new->canonical(1)->encode(\%response) if !$content;
	}
	
	# Scan Devices
	if( $q->{ajax} eq "searchdevices" ) {
		$response{error} = &searchdevices();
		print JSON->new->canonical(1)->encode(\%response);
	}
	
	# Delete Devices
	if( $q->{ajax} eq "deletedevice" ) {
		if ( !$q->{device} ) {
			$response{error} = "1";
			$response{message} = "No device given";
		}
		$response{error} = &deletedevice($q->{device});
		print JSON->new->canonical(1)->encode(\%response);
	}
	
	# Get single device config
	if( $q->{ajax} eq "getdeviceconfig" ) {
		if ( !$q->{device} ) {
			$response{error} = "1";
			$response{message} = "No device given";
		}
		else {
			# Get config
			%response = &getdeviceconfig ( $q->{device} );
		}
		print JSON->new->canonical(1)->encode(\%response);
	}
	
	exit;

##########################################################################
# Normal request (not AJAX)
##########################################################################

} else {
	
	require LoxBerry::Web;
	
	# Init Template
	$template = HTML::Template->new(
	    filename => "$lbptemplatedir/settings.html",
	    global_vars => 1,
	    loop_context_vars => 1,
	    die_on_bad_params => 0,
	);
	%L = LoxBerry::System::readlanguage($template, "language.ini");
	
	# Default is owfs form
	$q->{form} = "owfs" if !$q->{form};

	if ($q->{form} eq "owfs") { &form_owfs() }
	elsif ($q->{form} eq "devices") { &form_devices() }
	elsif ($q->{form} eq "mqtt") { &form_mqtt() }
	elsif ($q->{form} eq "log") { &form_log() }

	# Print the form
	&form_print();
}

exit;


##########################################################################
# Form: OWFS
##########################################################################

sub form_owfs
{
	$template->param("FORM_OWFS", 1);
	return();
}


##########################################################################
# Form: DEVICES
##########################################################################

sub form_devices
{
	$template->param("FORM_DEVICES", 1);
	return();
}

##########################################################################
# Form: MQTT
##########################################################################

sub form_mqtt
{
	$template->param("FORM_MQTT", 1);
	my $mqttplugindata = LoxBerry::System::plugindata("mqttgateway");
	$template->param("MQTTGATEWAY_INSTALLED", 1) if($mqttplugindata);
	$template->param("MQTTGATEWAY_PLUGINDBFOLDER", $mqttplugindata->{PLUGINDB_FOLDER}) if($mqttplugindata);
	return();
}


##########################################################################
# Form: Log
##########################################################################

sub form_log
{
	$template->param("FORM_LOG", 1);
	$template->param("LOGLIST", LoxBerry::Web::loglist_html());
	return();
}

##########################################################################
# Print Form
##########################################################################

sub form_print
{
	
	# Navbar
	our %navbar;

	$navbar{10}{Name} = "$L{'COMMON.LABEL_OWFS'}";
	$navbar{10}{URL} = 'index.cgi?form=owfs';
	$navbar{10}{active} = 1 if $q->{form} eq "owfs";
	
	$navbar{20}{Name} = "$L{'COMMON.LABEL_DEVICES'}";
	$navbar{20}{URL} = 'index.cgi?form=devices';
	$navbar{20}{active} = 1 if $q->{form} eq "devices";
	
	$navbar{30}{Name} = "$L{'COMMON.LABEL_MQTT'}";
	$navbar{30}{URL} = 'index.cgi?form=mqtt';
	$navbar{30}{active} = 1 if $q->{form} eq "mqtt";
	
	$navbar{98}{Name} = "$L{'COMMON.LABEL_LOG'}";
	$navbar{98}{URL} = 'index.cgi?form=log';
	$navbar{98}{active} = 1 if $q->{form} eq "log";

	$navbar{99}{Name} = "$L{'COMMON.LABEL_CREDITS'}";
	$navbar{99}{URL} = 'index.cgi?form=credits';
	$navbar{99}{active} = 1 if $q->{form} eq "credits";
	
	# Template
	LoxBerry::Web::lbheader($L{'COMMON.LABEL_PLUGINTITLE'} . " V$version", "https://www.loxwiki.eu/x/3gmcAw", "");
	print $template->output();
	LoxBerry::Web::lbfooter();
	
	exit;

}


######################################################################
# AJAX functions
######################################################################

sub ajax_header
{
	print $cgi->header(
			-type => 'application/json',
			-charset => 'utf-8',
			-status => '200 OK',
	);	
}	

sub pids
{
	$pids{'owserver'} = trim(`pgrep -f owserver`) ;
	$pids{'owhttpd'} = trim(`pgrep -f owhttpd`) ;
	$pids{'owfs2mqtt'} = trim(`pgrep -d , -f owfs2mqtt`) ;
	return();
}

sub deletedevice
{
 	my $device = $_[0];
 	my $errors;
 	if (!$device) {
 		$errors++;
 	} else {
 		# Devices config
 		my $jsonobjdevices = LoxBerry::JSON->new();
 		my $cfgdevices = $jsonobjdevices->open(filename => $CFGFILEDEVICES);
 		delete $cfgdevices->{$device};
 		$jsonobjdevices->write();
 	}
 	return ($errors);
}

sub getdeviceconfig
{
	my $device = $_[0];
	my %response;
	if (!$device) {
		$response{error} = 1;
		$response{message} = "No device given.";
	} else {
		my $jsonobjdevices = LoxBerry::JSON->new();
		my $cfgdevices = $jsonobjdevices->open(filename => $CFGFILEDEVICES);
		if ($cfgdevices->{$device}) {
			$response{address} = $cfgdevices->{$device}->{address};
			$response{name} = $cfgdevices->{$device}->{name};
			$response{configured} = $cfgdevices->{$device}->{configured};
			$response{refresh} = $cfgdevices->{$device}->{refresh};
			$response{uncached} = $cfgdevices->{$device}->{uncached};
			$response{values} = $cfgdevices->{$device}->{values};
			$response{checkpresent} = $cfgdevices->{$device}->{checkpresent};
			$response{error} = 0;
			$response{message} = "Device data read successfully.";
		} else {
			$response{error} = 1;
			$response{message} = "Device does not exist.";
		}
	}
	return (%response);
}

sub savedevice
{
	my $errors;
	
	# Devices Config
	my $jsonobjdevices = LoxBerry::JSON->new();
	my $cfgdevices = $jsonobjdevices->open(filename => $CFGFILEDEVICES);
	my $address = $q->{address};
	
	# OWFS Config
	my $jsonobjow = LoxBerry::JSON->new();
	my $cfgow = $jsonobjow->open(filename => $CFGFILEOWFS);
 	
	# Delete old entries - in case of a Address change delete device and (new) address
	delete $cfgdevices->{$q->{device}};
	delete $cfgdevices->{$q->{address}};
	
	# Connect to owserver
	my $owserver;
	eval {
		$owserver = OWNet->new('localhost:' . $cfgow->{"serverport"} . " -v -" .$cfgow->{"tempscale"} );
	};
	if ($@ || !$owserver) {
		$errors++;
	};

	# Check Type
	my $type;
	eval {
		$type = $owserver->read("/$address/type");
	};
	if ($@ || !$type) {
		$errors++;
		$type = "Unknown";
	};
	
	# Save
	$cfgdevices->{$address}->{name} = $q->{name};
	$cfgdevices->{$address}->{address} = $q->{address};
	my $configured =  is_enabled ($q->{configured}) ? 1 : 0;
	$cfgdevices->{$address}->{configured} = $configured;
	$cfgdevices->{$address}->{refresh} = $q->{refresh};
	my $uncached =  is_enabled ($q->{uncached}) ? 1 : 0;
	$cfgdevices->{$address}->{uncached} = $uncached;
	my $checkpresent =  is_enabled ($q->{checkpresent}) ? 1 : 0;
	$cfgdevices->{$address}->{checkpresent} = $checkpresent;
	$cfgdevices->{$address}->{values} = $q->{values};
	$cfgdevices->{$address}->{type} = $type;
	$jsonobjdevices->write();

	return ($errors);
}

sub searchdevices
{
 	my $errors;
	use OWNet;
	
 	# Devices config
 	my $jsonobjdevices = LoxBerry::JSON->new();
 	my $cfgdevices = $jsonobjdevices->open(filename => $CFGFILEDEVICES);
	
 	# Clear content
	#foreach ( keys %$cfgdev ) { delete $cfgdev->{$_}; }

	# OWFS Config
	my $jsonobjow = LoxBerry::JSON->new();
	my $cfgow = $jsonobjow->open(filename => $CFGFILEOWFS);
 	
	# Connect to owserver
	my $owserver;
	eval {
		$owserver = OWNet->new('localhost:' . $cfgow->{"serverport"} . " -v -" .$cfgow->{"tempscale"} );
	};
	if ($@ || !$owserver) {
		$errors++;
		return($errors);
	};
	
	# Scan Bus
	my $devices;
	eval {
		$devices = $owserver->dir("/");
	};
	if ($@ || !$devices) {
		$errors++;
		return($errors);
	};
	
	my @devices = split(/,/,$devices);
	for ( @devices ) {
		if ( $_ =~ /^\/(\d){2}.*$/ ) {
			my $name = $_;
			$name =~ s/^\///g;
			# Check if config already exists
			if ( $cfgdevices->{$name} ) {
				next;
			} else {
				# Add device to config
				my $type;
				eval {
					$type = $owserver->read("/$name/type");
				};
				if ($@ || !$type) {
					$errors++;
					$type = "Unknown";
				};
				$cfgdevices->{$name}->{name} = "$name";
				$cfgdevices->{$name}->{address} = "$name";
				$cfgdevices->{$name}->{type} = "$type";
				$cfgdevices->{$name}->{configured} = "0";
				$cfgdevices->{$name}->{refresh} = "60";
				$cfgdevices->{$name}->{uncached} = "0";
				$cfgdevices->{$name}->{checkpresent} = "0";
				$cfgdevices->{$name}->{values} = "";
			}
		}
	}

	$jsonobjdevices->write();

 	return ($errors);
}

sub savemqtt
{
	# Save mqtt.json
	my $errors;
	my $jsonobj = LoxBerry::JSON->new();
	my $cfg = $jsonobj->open(filename => $CFGFILEMQTT);
	$cfg->{topic} = $q->{topic};
	$cfg->{usemqttgateway} = $q->{usemqttgateway};
	$cfg->{server} = $q->{server};
	$cfg->{port} = $q->{port};
	$cfg->{username} = $q->{username};
	$cfg->{password} = $q->{password};
	$jsonobj->write();
	
	# Save mqtt_subscriptions.cfg for MQTT Gateway
	my $subscr_file = $lbpconfigdir."/mqtt_subscriptions.cfg";
	eval {
		open(my $fh, '>', $subscr_file);
		print $fh $q->{topic} . "/#\n";
		close $fh;
	};
	if ($@) {
		$errors++;
	}
	
	return ($errors);
}

sub saveowfs
{
	# Save owfs.json
	
	my $errors;
	my $jsonobj = LoxBerry::JSON->new();
	my $cfg = $jsonobj->open(filename => $CFGFILEOWFS);
	$cfg->{fake} = $q->{fake};
	$cfg->{httpdport} = $q->{httpdport};
	$cfg->{serverport} = $q->{serverport};
	$cfg->{usb} = $q->{usb};
	$cfg->{serial2usb} = $q->{serial2usb};
	$cfg->{i2c} = $q->{i2c};
	$cfg->{gpio} = $q->{gpio};
	$cfg->{tempscale} = $q->{tempscale};
	$cfg->{uncached} = $q->{uncached};
	$cfg->{refreshdev} = $q->{refreshdev};
	$cfg->{refreshval} = $q->{refreshval};
	$jsonobj->write();

	my $subscr_file = $lbpconfigdir."/owfs.conf";
	eval {
		open(my $fh, '>', $subscr_file);
		print $fh "!server: server = 127.0.0.1:" . $q->{serverport} . "\n";
		print $fh "server: port = " . $q->{serverport} . "\n";
		print $fh "http: port = " . $q->{httpdport} . "\n";
		print $fh "server: FAKE = " . $q->{fake} . "\n" if $q->{fake};
		print $fh "server: usb = all\n" if is_enabled($q->{usb});
		print $fh "server: i2c = ALL:ALL\n" if is_enabled($q->{i2c});
		print $fh "server: w1\n" if is_enabled($q->{gpio});
		if ( is_enabled($q->{serial2usb}) && -e "$lbpdatadir/ftdidevices.dat" ) {
			open(my $fh1, '<', "$lbpdatadir/ftdidevices.dat");
			while (my $row = <$fh1>) {
				chomp $row;
				print $fh "$row\n";
			}
			close $fh1;
		}
		close $fh;
	};
	if ($@) {
		$errors++;
	}

	my $loglevel = LoxBerry::System::pluginloglevel();
	my $verbose = "0";
	if ($loglevel eq "7") {
		$verbose = 1;
	}

	# Restart OWFS
	system("sudo systemctl enable owserver >/dev/null 2>&1");
	system("sudo systemctl enable owhttpd >/dev/null 2>&1");
	system("sudo $lbpbindir/watchdog.pl action=restart verbose=$verbose >/dev/null 2>&1");
	
	# Create Cronjob
	my $cron_file = $lbhomedir . "/system/cron/cron.01min/" . $lbpplugindir;
	eval {
		open(my $fh, '>', $cron_file);
		print $fh "#!/bin/bash\n";
		print $fh "sudo $lbpbindir/watchdog.pl action=check verbose=0\n";
		close $fh;
		system("chmod 755 $cron_file >/dev/null 2>&1");
	};
	if ($@) {
		$errors++;
	}

	return ($errors);

}

# Get VIs/VOs and data for nukiId
sub getdevicedownloads
{
	my ($intBridgeId, $nukiId) = @_;
	
	my $jsonobjbridges = LoxBerry::JSON->new();
	#my $bridges = $jsonobjbridges->open(filename => $CFGFILEBRIDGES, readonly => 1);
	my $jsonobjdevices = LoxBerry::JSON->new();
	my $devices = $jsonobjdevices->open(filename => $CFGFILEDEVICES, readonly => 1);
	my $jsonobjmqtt = LoxBerry::JSON->new();
	my $mqttconfig = $jsonobjmqtt->open(filename => $CFGFILEMQTT, readonly => 1);
	
	my %payload;
	my $error = 0;
	my $message = "";
	my $xml;
	
	#if(! defined $bridges->{$intBridgeId} ) {
	#	return (1, "BridgeId does not exist", undef);
	#} elsif (! defined $devices->{$nukiId} ) {
	#	return (1, "NukiId does not exist", undef);
	#}
	
	require "$lbpbindir/libs/LoxBerry/LoxoneTemplateBuilder.pm";
	require HTML::Entities;

 
	# Get current date
	my ($sec,$min,$hour,$mday,$mon,$year,$wday,$yday,$isdst) = localtime();
	$year+=1900;
	
	my $currdev = $devices->{$nukiId};
	my $devtype = $currdev->{deviceType};
	
	#LOGDEB "P$$ Device type is $devtype ($deviceType{$devtype})";
	
	## Create VO template
	#####################
	my $VO = LoxBerry::LoxoneTemplateBuilder->VirtualOut(
		Title => "NUKI " . $currdev->{name},
		Comment => "Created by LoxBerry Nuki Plugin ($mday.$mon.$year)",
		#Address => "http://".$bridges->{$intBridgeId}->{ip}.":".$bridges->{$intBridgeId}->{port},
 	);
	
	# Lock Actions

	# Analog action
	$VO->VirtualOutCmd(
		Title => "Analogue Lock Action",
		#CmdOn => "/lockAction?nukiId=$nukiId&deviceType=$devtype&action=<v>&nowait=1&token=$bridges->{$intBridgeId}->{token}",
		Analog => 1
	);

	# Digital actions
	#my $devlockActions = $lockAction{$devtype};
	#foreach my $actionkey ( sort keys %$devlockActions ) {
	#	my $actionname = $devlockActions->{$actionkey};
	#	$actionname  =~ s/\b(\w)(\w*)/\U$1\L$2/g;
	#	LOGDEB "P$$ actionkey $actionkey actionname $actionname";
	#	$VO->VirtualOutCmd(
	#		Title => $actionname,
	#		CmdOn => "/lockAction?nukiId=$nukiId&deviceType=$devtype&action=$actionkey&nowait=1&token=$bridges->{$intBridgeId}->{token}"
	#	);
	#}

	
	$xml = $VO->output;
	$payload{vo} = $xml;
	$payload{voFilename} = "VO_NUKI_$currdev->{name}.xml";
	
	## Create VI template (via Virtual HTTP Input)
	##############################################
	my $topic_from_cfg = $mqttconfig->{topic};
	my $topic = $topic_from_cfg;
	$topic =~ tr/\//_/;
		
	my $VI = LoxBerry::LoxoneTemplateBuilder->VirtualInHttp(
		Title => "NUKI Status " . $currdev->{name},
		Comment => "Created by LoxBerry Nuki Plugin ($mday.$mon.$year)",
 	);
	
	$VI->VirtualInHttpCmd( Title => "${topic}_${nukiId}_batteryCritical", Comment => "$currdev->{name} Battery Critical");
	$VI->VirtualInHttpCmd( Title => "${topic}_${nukiId}_mode", Comment => "$currdev->{name} Mode");
	$VI->VirtualInHttpCmd( Title => "${topic}_${nukiId}_nukiId", Comment => "$currdev->{name} Nuki ID");
	$VI->VirtualInHttpCmd( Title => "${topic}_${nukiId}_state", Comment => "$currdev->{name} State");
	$VI->VirtualInHttpCmd( Title => "${topic}_${nukiId}_sentBy", Comment => "$currdev->{name} Sent By");
	$VI->VirtualInHttpCmd( Title => "${topic}_${nukiId}_sentAtTimeLox", Comment => "$currdev->{name} Last Updated");
	
	$xml = $VI->output;
	$payload{vi} = $xml;
	$payload{viFilename} = "VI_NUKI_$currdev->{name}.xml";
	
	## Create MQTT representation of inputs
	#######################################
	
	
	my $m = "";
	if($topic) {
		$m .= '<table class="mqtttable">'."\n";
		$m .= "<tr>\n";
		$m .= '<th class="mqtttable_headrow mqtttable_vicol ui-bar-a">Loxone VI (via MQTT)</td>'."\n";
		$m .= '<th class="mqtttable_headrow mqtttable_desccol ui-bar-a">Description</td>'."\n";
		$m .= '</tr>'."\n";
		
		$m .= '<tr>'."\n";
		$m .= '<td class="mqtttable_vicol">'."${topic}_${nukiId}_batteryCritical</td>\n";
		$m .= '<td class="mqtttable_desccol">0...Battery ok 1 ... Battery low</td>'."\n";
		$m .= "</tr>\n";
		
		$m .= "<tr>\n";
		$m .= '<td class="mqtttable_vicol">'."${topic}_${nukiId}_deviceType</td>\n";
		$m .= '<td class="mqtttable_desccol">';
		#foreach( sort keys %deviceType ) {
		#	$m .= "$_...$deviceType{$_} ";
		#}
		$m .= "</td>\n";
		$m .= "</tr>\n";
		
		$m .= "<tr>\n";
		$m .= '<td class="mqtttable_vicol">'."${topic}_${nukiId}_mode</td>\n";
		if( $devtype eq "0") {
			$m .= '<td class="mqtttable_desccol">'."Always '2' after complete setup</td>\n";
		} elsif ($devtype eq "2") {
			$m .= '<td class="mqtttable_desccol">'."2...Door mode 3...Continuous mode</td>\n";
		} else {
			$m .= "<td>(unknown device type)</td>\n";
		}
		$m .= "</tr>\n";
		
		$m .= "<tr>\n";
		$m .= '<td class="mqtttable_vicol">'."${topic}_${nukiId}_nukiId</td>\n";
		$m .= '<td class="mqtttable_desccol">ID of your Nuki device</td>'."\n";
		$m .= "</tr>\n";
		
		$m .= "<tr>\n";
		$m .= '<td class="mqtttable_vicol">'."${topic}_${nukiId}_state</td>\n";
		$m .= '<td class="mqtttable_desccol">';
		#foreach( sort {$a<=>$b} keys %{$lockState{$devtype}} ) {
		#	$m .= "$_...$lockState{$devtype}{$_} ";
		#}
		$m .= "</td>\n";
		$m .= "</tr>\n";

		$m .= "<tr>\n";
		$m .= '<td class="mqtttable_vicol">'."${topic}_${nukiId}_sentBy</td>\n";
		$m .= '<td class="mqtttable_desccol">'."1...callback 2...cron 3...manual</td>\n";
		$m .= "</tr>\n";

		$m .= "<tr>\n";
		$m .= '<td class="mqtttable_vicol">'."${topic}_${nukiId}_sentAtTimeLox</td>\n";
		$m .= '<td class="mqtttable_desccol">'."Loxone Time representation of the update time &lt;v.u&gt;</td>\n";
		$m .= "</tr>\n";
	
		$m .= "</table>\n";
	
	}
	$payload{mqttTable} = $m;
		
	$error = 0;
	$message = "Generated successfully";
	return ($error, $message, \%payload);



}

END {
}
