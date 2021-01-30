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
use warnings;
use strict;
no strict "refs"; # we need it for template system and for contructs like ${"skalar".$i} in loops

##########################################################################
# Variables
##########################################################################
my  $cgi = new CGI;
my  $cfg;
my  $plugin_cfg;
my  $lang;
my  $installfolder;
my  $version;
my  $home = File::HomeDir->my_home;
my  $psubfolder;
my  $pname;
my  $serial;
my  $logfile;
my  $pid;

##########################################################################
# Read Settings
##########################################################################

# Version of this script
$version = "0.1";

# Figure out in which subfolder we are installed
$psubfolder = abs_path($0);
$psubfolder =~ s/(.*)\/(.*)\/(.*)$/$2/g;

# Read general config
$cfg	 	= new Config::Simple("$home/config/system/general.cfg") or die $cfg->error();
$installfolder	= $cfg->param("BASE.INSTALLFOLDER");
$lang		= $cfg->param("BASE.LANG");

##########################################################################
# Main program
##########################################################################

# Create temp folder if not already exist
if (!-d "/var/run/shm/$psubfolder") {
	system("mkdir -p /var/run/shm/$psubfolder > /dev/null 2>&1");
}
# Check for temporary log folder
if (!-e "$installfolder/log/plugins/$psubfolder/shm") {
	system("ln -s /var/run/shm/$psubfolder  $installfolder/log/plugins/$psubfolder/shm > /dev/null 2>&1");
}
# Create Logfile
$logfile = "/var/run/shm/$psubfolder/fetch_manually.log";
system("rm /var/run/shm/$psubfolder/$logfile");
system("touch /var/run/shm/$psubfolder/$logfile");

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
  system("$installfolder/webfrontend/cgi/plugins/$psubfolder/bin/fetch.pl --verbose --force");
}

exit;
