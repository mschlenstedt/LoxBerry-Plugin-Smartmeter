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
$cron		= $plugin_cfg->param("MAIN.CRON");

# Commandline options
GetOptions (    "verbose"          => \$verbose,
                "force"            => \$force,
);

if ($verbose) {
	$verbose = "--verbose";
}

# Create temp folder if not already exist
if (!-d "/var/run/shm/$psubfolder") {
	system("mkdir -p /var/run/shm/$psubfolder > /dev/null 2>&1");
}
# Check for temporary log folder
if (!-e "$installfolder/log/plugins/$psubfolder/shm") {
	system("ln -s /var/run/shm/$psubfolder  $installfolder/log/plugins/$psubfolder/shm > /dev/null 2>&1");
}

# Delete old Logfile
system("rm /var/run/shm/$psubfolder/fetch.log > /dev/null 2>&1");

# Check if we should read automatically
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
			&LOG ("$serial: Device: $device", "INFO");
			&LOG ("$serial: Baudrate:$baudrate/$startbaudrate Databits:$databits Stopbits:$stopbits Parity:$parity Handshake:$handshake", "INFO");
			system("$installfolder/bin/plugins/$psubfolder/sm_logger.pl --device $device --protocol $protocol --startbaudrate $startbaudrate --baudrate $baudrate --timeout $timeout --delay $delay --handshake $handshake --databits $databits --stopbits $stopbits --parity $parity $verbose");
		} else {
			# If set to  a meter, use standard settings for this meter
			&LOG ("$serial: Presetting: $meter.", "INFO");
			system("$installfolder/bin/plugins/$psubfolder/sm_logger.pl --device $device --protocol $meter $verbose");
			#system("$installfolder/bin/plugins/$psubfolder/sm_logger.pl --device $device --parse D30A3RFT --protocol $meter $verbose");
		}

		# Send data by UDP to all configured miniservers
		# If we should send by UDP, figure out which Miniservers are configured
		if ($sendudp) {

		  $udpstring = "";

		  # Read Data file
		  if ( !-e "/var/run/shm/$psubfolder/$serial\.data" ) {
			$udpstring = "$serial: No data found";
 		  } else {
			open(F,"</var/run/shm/$psubfolder/$serial\.data");
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
		      my $dns_info = `$home/webfrontend/cgi/system/tools/showclouddns.pl $miniservermac`;
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

	}

}
if ($plugin_cfg->param("MAIN.CRON") eq "M" && !$force) {
	&LOG("$serial: Cronjob is MINIMUM - RERUN", "OK");	
	goto RERUN;
	}
exit;

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
        open(F,">>/var/run/shm/$psubfolder/fetch.log");
                print F "$year-$mon-$mday $hour:$min:$sec <$type> $message\n";
        close (F);

        return();

}
