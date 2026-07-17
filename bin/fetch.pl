#!/usr/bin/perl

# Copyright 2017 Michael Schlenstedt, michael@loxberry.de
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

use Config::Simple;
use File::HomeDir;
use Cwd 'abs_path';
use IO::Socket; # For sending UDP packages
use Getopt::Long;
use LoxBerry::System;
use File::Path qw(make_path);
use Fcntl qw(:flock);
#use warnings;
#use strict;
no strict "refs"; # we need it for template system and for contructs like ${"skalar".$i} in loops
no strict "subs"; # we need it for template system and for contructs like ${"skalar".$i} in loops

##########################################################################
# Variables
##########################################################################
my  $cfg;
my  $plugin_cfg;
my  %plugin_cfg_hash;
my  $installfolder;
my  $version;
my  $home = $lbhomedir;
my  $psubfolder = $lbpplugindir;
my  $runtime_dir = "/var/run/shm/$psubfolder";
my  $pname;
my  @heads;
my  $name;
my  $serial;
my  $device;
my  $meter;
my  $protocol;
my  $startbaudrate;
my  $baudrate;
my  $timeout;
my  $handshake;
my  $databits;
my  $stopbits;
my  $parity;
my  $delay;
our $miniservers;
our $clouddns;
our $udpport;
our $sendudp;
our $sendmqtt;
our $mqtttopic;
our $implementation;
my  $udpstring;
my  @lines;
my  $i;
my  $verbose;
my  $force;

##########################################################################
# Read Settings
##########################################################################

# Version of this script
$version = "0.2";

# Figure out in which subfolder we are installed
#$psubfolder = abs_path($0);
#$psubfolder =~ s/(.*)\/(.*)\/bin\/(.*)$/$2/g;

# If Cron is minimum, here is the rerun mark
RERUN:

# Read general config
$cfg	 	= new Config::Simple("$home/config/system/general.cfg") or die $cfg->error();
$installfolder	= $cfg->param("BASE.INSTALLFOLDER");
$miniservers	= $cfg->param("BASE.MINISERVERS");
$clouddns	= $cfg->param("BASE.CLOUDDNS");

# Read plugin config
$plugin_cfg 	= new Config::Simple("$installfolder/config/plugins/$psubfolder/smartmeter.cfg") or die $plugin_cfg->error();
$pname          = $plugin_cfg->param("MAIN.SCRIPTNAME");
$udpport        = $plugin_cfg->param("MAIN.UDPPORT");
$sendudp        = $plugin_cfg->param("MAIN.SENDUDP");
$sendmqtt       = $plugin_cfg->param("MAIN.SENDMQTT");
$mqtttopic      = $plugin_cfg->param("MAIN.MQTTTOPIC") || "smartmeter";
$implementation = $plugin_cfg->param("MAIN.IMPLEMENTATION") || "legacy";
$cron		= $plugin_cfg->param("MAIN.CRON");

# Commandline options
GetOptions (    "verbose"          => \$verbose,
                "force"            => \$force,
);

if ($verbose) {
	$verbose = "--verbose";
}

# Create temp folder if not already exist
if (!-d $runtime_dir) {
	make_path($runtime_dir);
}
# Check for temporary log folder
if (!-e "$installfolder/log/plugins/$psubfolder/shm") {
	symlink($runtime_dir, "$installfolder/log/plugins/$psubfolder/shm");
}

open(my $lock_fh, ">", "$runtime_dir/fetch.lock") or die "Could not open fetch lock: $!";
if (!flock($lock_fh, LOCK_EX | LOCK_NB)) {
	&LOG("Another meter polling run is already active. Giving up.", "WARN");
	exit;
}

# Delete old Logfile
if (-e "$runtime_dir/fetch.log") {
	unlink("$runtime_dir/fetch.log");
}

# Check if we should read automatically
if ( $implementation ne "legacy" && !$force ) {
	&LOG ("Legacy meter polling is disabled because Legacy mode is not active.", "INFO");
	exit;
}

if ( !$plugin_cfg->param("MAIN.READ") && !$force ) {
	&LOG ("Reading serial devices is currently deactivated. Giving up.", "FAIL");
	exit;
}

# Detect which IR Heads are connected / configured
Config::Simple->import_from("$installfolder/config/plugins/$psubfolder/smartmeter.cfg", \%plugin_config_hash);
while (my ($configname, $configvalue) = each %plugin_config_hash){
	if ( $configname =~ /SERIAL/ ) {
		$name 		=	$plugin_cfg->param("$configvalue.NAME");
		$serial		=	$plugin_cfg->param("$configvalue.SERIAL");
		$device		=	$plugin_cfg->param("$configvalue.DEVICE");
		$meter		=	$plugin_cfg->param("$configvalue.METER");
		$protocol	=	$plugin_cfg->param("$configvalue.PROTOCOL");
		$startbaudrate	=	$plugin_cfg->param("$configvalue.STARTBAUDRATE");
		$baudrate	=	$plugin_cfg->param("$configvalue.BAUDRATE");
		$timeout	=	$plugin_cfg->param("$configvalue.TIMEOUT");
		$handshake	=	$plugin_cfg->param("$configvalue.HANDSHAKE");
		$databits	=	$plugin_cfg->param("$configvalue.DATABITS");
		$stopbits	=	$plugin_cfg->param("$configvalue.STOPBITS");
		$parity		=	$plugin_cfg->param("$configvalue.PARITY");
		$delay 		=	$plugin_cfg->param("$configvalue.DELAY");
		$crc 		=	$plugin_cfg->param("$configvalue.CRC");
		&LOG ("$serial: Found configuration for $name", "INFO");

		# Check if head is connected and config is complete
		if ( !-e $plugin_cfg->param("$configvalue.DEVICE") ) {
			&LOG ("$serial: Device does not exist. Skipping.", "INFO");
			next;
		}
		if ( $plugin_cfg->param("$configvalue.METER") eq "0" ) {
			&LOG ("$serial: Configuration for $name is not complete. Skipping.", "INFO");
			next;
		}

		# If set to manual, use manual settings
		if ( $meter eq "manual" ) {
			&LOG ("$serial: Manual settings.", "INFO");
			&LOG ("$serial: Protocol: $protocol", "INFO");
			&LOG ("$serial: Timeout: $timeout", "INFO");
			&LOG ("$serial: Delay: $delay", "INFO");
			&LOG ("$serial: CRC: $crc", "INFO");
			&LOG ("$serial: Device: $device", "INFO");
			&LOG ("$serial: Baudrate:$baudrate/$startbaudrate Databits:$databits Stopbits:$stopbits Parity:$parity Handshake:$handshake", "INFO");
			my @logger_args = ("--device", $device, "--protocol", $protocol);
			&add_option(\@logger_args, "--startbaudrate", $startbaudrate);
			&add_option(\@logger_args, "--baudrate", $baudrate);
			&add_option(\@logger_args, "--timeout", $timeout);
			&add_option(\@logger_args, "--delay", $delay);
			&add_option(\@logger_args, "--handshake", $handshake);
			&add_option(\@logger_args, "--databits", $databits);
			&add_option(\@logger_args, "--stopbits", $stopbits);
			&add_option(\@logger_args, "--parity", $parity);
			&add_option(\@logger_args, "--crc", $crc);
			push(@logger_args, "--verbose") if ($verbose);
			&run_sm_logger(@logger_args);
        } else {
			# If set to  a meter, use standard settings for this meter
			&LOG ("$serial: Presetting: $meter.", "INFO");
			my @logger_args = ("--device", $device, "--protocol", $meter);
			push(@logger_args, "--verbose") if ($verbose);
			&run_sm_logger(@logger_args);
            }

		# Send data by UDP to all configured miniservers
		# If we should send by UDP, figure out which Miniservers are configured
		if ($sendudp) {

		  $udpstring = "";

		  # Read Data file
		  if ( !-e "$runtime_dir/$serial\.data" ) {
			$udpstring = "$serial: No data found";
 		  } else {
			open(F,"<$runtime_dir/$serial\.data");
				@lines = <F>;
			close(F);

			foreach ( @lines ) {
			  chomp ($_);
			  $udpstring .= "$_; ";
			}
		  }

		  &LOG("$serial: UDP String to send: $udpstring", "INFO");

		  for (my $i=1;$i<=$miniservers;$i++) {

		    ${miniservername . "$i"} = $cfg->param("MINISERVER$i.NAME");

		    if ( $cfg->param("MINISERVER$i.USECLOUDDNS") ) {
		      my $miniservermac = $cfg->param("MINISERVER$i.CLOUDURL");
		      my $dns_info = "";
		      if (open(my $dns_fh, "-|", "$home/webfrontend/cgi/system/tools/showclouddns.pl", $miniservermac)) {
		        $dns_info = do { local $/; <$dns_fh> };
		        close($dns_fh);
		      }
		      my @dns_info_pieces = split /:/, $dns_info;
		      if ($dns_info_pieces[0]) {
		        $dns_info_pieces[0] =~ s/^\s+|\s+$//g;
		        ${miniserverip . "$i"} = $dns_info_pieces[0];
		        &LOG("$serial: Send Data to " . ${miniservername . "$i"} . " at " . ${miniserverip . "$i"} . " using CloudDNS.", "INFO");
		      } else {
		        ${miniserverip . "$i"} = "127.0.0.1";
		        &LOG("$serial: Could not find IP Address for " . ${miniservername . "$i"} . " using CloudDNS.", "WARN");
		      }
		    } else {
		      if ( $cfg->param("MINISERVER$i.IPADDRESS") ) {
		        ${miniserverip . "$i"} = $cfg->param("MINISERVER$i.IPADDRESS");
		        &LOG("$serial: Send Data to " . ${miniservername . "$i"}  . " at " . ${miniserverip . "$i"} . ".", "INFO");
		      } else {
		        ${miniserverip . "$i"} = "127.0.0.1";
		        &LOG("$serial: Could not find IP Address for " . ${miniservername . "$i"} . ".", "WARN");
		      }
		    }

		  }

		  # Send Data
		  for ($i=1;$i<=$miniservers;$i++) {

		    # Send value
		    my $sock = IO::Socket::INET->new(
		      Proto    => 'udp',
		      PeerPort => $udpport,
		      PeerAddr => ${miniserverip . "$i"},
		    ) or die "<ERROR> Could not create socket: $!\n";
		    $sock->send($udpstring) or die "Send error: $!\n";
		    &LOG("$serial: Send OK to " . ${miniservername . "$i"} . ". IP:" . ${miniserverip . "$i"} . " Port:$udpport", "OK");
		  }

		}

		# Publish the same meter values by MQTT.
		if ($sendmqtt) {
			if ( !-e "$runtime_dir/$serial\.data" ) {
				&LOG("$serial: No data found for MQTT publish.", "WARN");
			} else {
				open(F,"<$runtime_dir/$serial\.data");
					@lines = <F>;
				close(F);
				&publish_mqtt_data($serial, @lines);
			}
		}

	}

}
if ($plugin_cfg->param("MAIN.CRON") eq "M" && !$force) {
	&LOG("$serial: Cronjob is MINIMUM - RERUN", "OK");	
	sleep(5);
	goto RERUN;
	}
exit;

sub add_option
{
	my ($args, $name, $value) = @_;
	return if (!defined($value) || $value eq "");
	push(@$args, $name, $value);
}

sub run_sm_logger
{
	my @args = @_;
	my $logger = "$installfolder/bin/plugins/$psubfolder/sm_logger.pl";
	system($^X, $logger, @args);
	if ($? != 0) {
		&LOG("sm_logger.pl failed with exit code " . ($? >> 8) . ".", "FAIL");
	}
}

################################
### SUB: Log
################################

sub LOG
{

        my $message     = shift; # http://wiki.selfhtml.org/wiki/Perl/Subroutinen
        my $type        = uc shift; # http://wiki.selfhtml.org/wiki/Perl/Subroutinen
        if ( !$type ) { $type = "INFO" };

        print "$message\n";

        # Today's date for LOGfile
        (my $sec,my $min,my $hour,my $mday,my $mon,my $year,my $wday,my $yday,my $isdst) = localtime();
        $year = $year+1900;
        $mon = $mon+1;
        $mon = sprintf("%02d", $mon);
        $mday = sprintf("%02d", $mday);
        $hour = sprintf("%02d", $hour);
        $min = sprintf("%02d", $min);
        $sec = sprintf("%02d", $sec);

        # Logfile
        open(F,">>$runtime_dir/fetch.log");
                print F "$year-$mon-$mday $hour:$min:$sec <$type> $message\n";
        close (F);

        return();

}

################################
### SUB: Publish MQTT data
################################

sub publish_mqtt_data
{
	my $serial = shift;
	my @data_lines = @_;

	eval {
		require JSON::PP;
	};
	if ($@) {
		&LOG("$serial: JSON module for MQTT Gateway publish is not available: $@", "FAIL");
		return;
	}

	my $general_json = "$home/config/system/general.json";
	if (!-e $general_json) {
		&LOG("$serial: MQTT settings not found in $general_json. Is LoxBerry MQTT Gateway installed?", "WARN");
		return;
	}

	open(my $json_fh, "<", $general_json) or do {
		&LOG("$serial: Could not open MQTT settings $general_json: $!", "FAIL");
		return;
	};
	local $/;
	my $json_text = <$json_fh>;
	close($json_fh);

	my $general = eval { JSON::PP->new->utf8->decode($json_text) };
	if ($@ || !ref($general) || !ref($general->{Mqtt})) {
		&LOG("$serial: Could not read MQTT settings from $general_json.", "FAIL");
		return;
	}

	my $mqtt_settings = $general->{Mqtt};
	my $udpport = $mqtt_settings->{Udpinport};
	if (!$udpport) {
		&LOG("$serial: MQTT Gateway UDP in-port is missing in $general_json.", "FAIL");
		return;
	}

	my $base_topic = $mqtttopic || "smartmeter";
	$base_topic =~ s/^\s+|\s+$//g;
	$base_topic =~ s/^\/+|\/+$//g;
	$base_topic = "smartmeter" if (!$base_topic);

	my $json = JSON::PP->new->utf8;
	my $sock = IO::Socket::INET->new(
		Proto    => 'udp',
		PeerPort => $udpport,
		PeerAddr => '127.0.0.1',
	) or do {
		&LOG("$serial: Could not create MQTT Gateway UDP socket on port $udpport: $!", "FAIL");
		return;
	};

	my $published = 0;
	foreach my $line (@data_lines) {
		chomp($line);
		next if ($line eq "");

		my ($line_serial, $value_name, $value) = split(/:/, $line, 3);
		if (!defined $line_serial || !defined $value_name || !defined $value) {
			&LOG("$serial: Skip invalid MQTT data line: $line", "WARN");
			next;
		}

		my $topic = "$base_topic/$line_serial/$value_name";
		$topic =~ s/[#+]//g;

		my %packet = (
			topic  => $topic,
			value  => $value,
			retain => 1,
		);
		my $payload = $json->encode(\%packet);
		if (!$sock->send($payload)) {
			&LOG("$serial: MQTT Gateway UDP send failed for $topic: $!", "FAIL");
			next;
		}
		$published++;
	}

	&LOG("$serial: Published $published values by MQTT Gateway UDP on port $udpport using topic $base_topic/$serial/<value>.", "OK");
}
