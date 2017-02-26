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
my  $installfolder;
my  $version;
my  $home = File::HomeDir->my_home;
my  $psubfolder;
my  $pname;
my  $serial;
my  @lines;

##########################################################################
# Read Settings
##########################################################################

# Version of this script
$version = "0.1";

# Figure out in which subfolder we are installed
$psubfolder = abs_path($0);
$psubfolder =~ s/(.*)\/(.*)\/(.*)$/$2/g;

# Start with HTML header
#print $cgi->header(
#	type	=>	'text/html',
#	charset	=>	'utf-8',
#); 
print "Content-type: text/plain\n\n";

# Read general config
$cfg	 	= new Config::Simple("$home/config/system/general.cfg") or die $cfg->error();
$installfolder	= $cfg->param("BASE.INSTALLFOLDER");

# Read plugin config
$plugin_cfg 	= new Config::Simple("$installfolder/config/plugins/$psubfolder/smartmeter.cfg") or die $plugin_cfg->error();
$pname          = $plugin_cfg->param("MAIN.SCRIPTNAME");

# Set parameters coming in - get over post
if ( $cgi->url_param('serial') ) {
	$serial = quotemeta( $cgi->url_param('serial') );
}
elsif ( $cgi->param('serial') ) {
	$serial = quotemeta( $cgi->param('serial') );
}

# Create temp folder if not already exist
if (!-d "/var/run/shm/$psubfolder") {
	system("mkdir -p /var/run/shm/$psubfolder > /dev/null 2>&1");
}
# Check for temporary log folder
if (!-e "$installfolder/log/plugins/$psubfolder/shm") {
	system("ln -s /var/run/shm/$psubfolder  $installfolder/log/plugins/$psubfolder/shm > /dev/null 2>&1");
}

##########################################################################
# Output
##########################################################################

# We need a serial
if ( !$serial ) {

	print "No serial given.\n";

	exit;

}

# If no data exist, give dummy file
if ( !-e "/var/run/shm/$psubfolder/$serial\.data" ) {

	print "Last_Update: 01.01.2009 00:00:00\n";
	print "Last_UpdateLoxEpoche: 1230764400\n";
	print "Consumption_Total_OBIS_1.8.0: \n";
	print "Consumption_Tarif1_OBIS_1.8.1: \n";
	print "Consumption_Tarif2_OBIS_1.8.2: \n";
	print "Consumption_Tarif3_OBIS_1.8.3: \n";
	print "Consumption_Tarif4_OBIS_1.8.4: \n";
	print "Consumption_Tarif5_OBIS_1.8.5: \n";
	print "Consumption_Tarif6_OBIS_1.8.6: \n";
	print "Consumption_Tarif7_OBIS_1.8.7: \n";
	print "Consumption_Tarif8_OBIS_1.8.8: \n";
	print "Consumption_Tarif9_OBIS_1.8.9: \n";
	print "Consumption_CalculatedPower_OBIS_1.99.0: \n";
	print "Consumption_Power_OBIS_1.7.0: \n";
	print "Delivery_Total_OBIS_2.8.0: \n";
	print "Delivery_Tarif1_OBIS_2.8.1: \n";
	print "Delivery_Tarif2_OBIS_2.8.2: \n";
	print "Delivery_Tarif3_OBIS_2.8.3: \n";
	print "Delivery_Tarif4_OBIS_2.8.4: \n";
	print "Delivery_Tarif5_OBIS_2.8.5: \n";
	print "Delivery_Tarif6_OBIS_2.8.6: \n";
	print "Delivery_Tarif7_OBIS_2.8.7: \n";
	print "Delivery_Tarif8_OBIS_2.8.8: \n";
	print "Delivery_Tarif9_OBIS_2.8.9: \n";
	print "Delivery_CalculatedPower_OBIS_2.99.0: \n";
	print "Delivery_Power_OBIS_2.7.0: \n";
	print "Total_Power_OBIS_15.7.0: \n";
	print "Total_Power_OBIS_16.7.0: \n";

	exit;

}

# Read data file
open(F,"</var/run/shm/$psubfolder/$serial\.data");
	@lines = <F>;
close(F);

foreach ( @lines ) {
  print $_;
}

exit;
