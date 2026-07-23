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

use CGI::Carp qw(fatalsToBrowser);
use CGI qw/:standard/;
use Config::Simple;
use File::HomeDir;
use Cwd 'abs_path';
use File::Path qw(make_path);
use FindBin;
use LoxBerry::System;
use lib $lbpbindir;
use lib "$FindBin::Bin/../../bin";
use SmartMeterVZLoggerConfig qw(implementation_mode);
use SmartMeterLegacyRuntime qw(vzlogger_service_running);
use warnings;
use strict;

##########################################################################
# Variables
##########################################################################
my  $cgi = new CGI;
my  $cfg;
my  $plugin_cfg;
my  $installfolder;
my  $home = File::HomeDir->my_home;
my  $psubfolder;
my  $logfile;
my  $pid;

##########################################################################
# Read Settings
##########################################################################

# Figure out in which subfolder we are installed
$psubfolder = abs_path($0);
$psubfolder =~ s/(.*)\/(.*)\/(.*)$/$2/g;

# Read general config
$cfg	 	= new Config::Simple("$home/config/system/general.cfg") or die $cfg->error();
$installfolder	= $cfg->param("BASE.INSTALLFOLDER");
$plugin_cfg = Config::Simple->new("$installfolder/config/plugins/$psubfolder/smartmeter.cfg") or die "Could not read SmartMeter configuration";

##########################################################################
# Main program
##########################################################################

# Create temp folder if not already exist
my $runtime_dir = "/var/run/shm/$psubfolder";
if (!-d $runtime_dir) {
	make_path($runtime_dir);
}
# Check for temporary log folder
if (!-e "$installfolder/log/plugins/$psubfolder/shm") {
	symlink($runtime_dir, "$installfolder/log/plugins/$psubfolder/shm");
}
# Create Logfile
$logfile = "$runtime_dir/fetch_manually.log";
unlink($logfile) if (-e $logfile);
open(my $log_fh, ">", $logfile) or die "Could not create $logfile: $!";
close($log_fh);

if (implementation_mode($plugin_cfg) ne "legacy" || vzlogger_service_running()) {
	open(my $disabled_fh, ">", $logfile) or die "Could not write $logfile: $!";
	print $disabled_fh implementation_mode($plugin_cfg) ne "legacy"
		? "Legacy meter polling is disabled because Legacy mode is not active.\n"
		: "Legacy meter polling is disabled while the vzLogger service is running.\n";
	close($disabled_fh);
	print redirect(-url=>"/admin/system/tools/logfile.cgi?logfile=plugins/$psubfolder/shm/fetch_manually.log&header=html&format=template");
	exit;
}

# Redirect to Logviewer
print redirect(-url=>"/admin/system/tools/logfile.cgi?logfile=plugins/$psubfolder/shm/fetch_manually.log&header=html&format=template");

# Without the following workaround
# the script cannot be executed as
# background process via CGI
$pid = fork();
die "Fork failed: $!" if !defined $pid;


if ($pid == 0) {
  # do this in the child
  open STDIN, "</dev/null";
  open STDOUT, ">$logfile";
  #open STDERR, ">$logfile";
  open STDERR, ">/dev/null";

  # Trigger fetch
  system($^X, "$installfolder/bin/plugins/$psubfolder/fetch.pl", "--verbose", "--manual");
}

exit;
