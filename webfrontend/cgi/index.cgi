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
#use HTML::Entities;
use String::Escape qw( unquotemeta );
use Cwd 'abs_path';
use HTML::Template;
#use warnings;
#use strict;
#no strict "refs"; # we need it for template system and for contructs like ${"skalar".$i} in loops

##########################################################################
# Variables
##########################################################################
my  $cgi = new CGI;
my  $cfg;
my  $plugin_cfg;
my  $lang;
my  $installfolder;
my  $languagefile;
my  $version;
my  $home = File::HomeDir->my_home;
my  $psubfolder;
my  $pname;
my  $languagefileplugin;
my  %TPhrases;
my  @heads;
my  %head;
my  @rows;
my  %hash;
my  $maintemplate;
my  $template_title;
my  $phrase;
my  $helplink;
my  @help;
my  $helptext;
my  $saveformdata;
my  $clearcache;
my  %plugin_config;
my  $name;
my  $device;
my  $serial;

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
print "Content-type: text/html\n\n";

# Read general config
$cfg	 	= new Config::Simple("$home/config/system/general.cfg") or die $cfg->error();
$installfolder	= $cfg->param("BASE.INSTALLFOLDER");
$lang		= $cfg->param("BASE.LANG");

# Read plugin config
$plugin_cfg 	= new Config::Simple("$installfolder/config/plugins/$psubfolder/smartmeter.cfg") or die $plugin_cfg->error();
$pname          = $plugin_cfg->param("MAIN.SCRIPTNAME");

# Create temp folder if not already exist
if (!-d "/var/run/shm/$psubfolder") {
	system("mkdir -p /var/run/shm/$psubfolder > /dev/null 2>&1");
}
# Check for temporary log folder
if (!-e "$installfolder/log/plugins/$psubfolder/shm") {
	system("ln -s /var/run/shm/$psubfolder $installfolder/log/plugins/$psubfolder/shm > /dev/null 2>&1");
}

# Detect which IR Heads are connected
my @heads = split(/\n/,`ls /dev/serial/smartmeter/*`);

# Save a config set if it not already exists
foreach (@heads) {
	$serial = $_;
	$serial =~ s%/dev/serial/smartmeter/%%g;
	if ( !$plugin_cfg->param("$serial.DEVICE") ) {
		$plugin_cfg->param("$serial.NAME", "$serial");
		$plugin_cfg->param("$serial.SERIAL", "$serial");
		$plugin_cfg->param("$serial.DEVICE", "$_");
		$plugin_cfg->param("$serial.METER", "0");
		$plugin_cfg->param("$serial.PROTOCOL", "");
		$plugin_cfg->param("$serial.STARTBAUDRATE", "");
		$plugin_cfg->param("$serial.BAUDRATE", "");
		$plugin_cfg->param("$serial.TIMEOUT", "");
		$plugin_cfg->param("$serial.DELAY", "");
		$plugin_cfg->param("$serial.HANDSHAKE", "");
		$plugin_cfg->param("$serial.DATABITS", "");
		$plugin_cfg->param("$serial.STOPBITS", "");
		$plugin_cfg->param("$serial.PARITY", "");
	}
}
$plugin_cfg->save;

# Set parameters coming in - get over post
if ( $cgi->url_param('lang') ) {
	$lang = quotemeta( $cgi->url_param('lang') );
}
elsif ( $cgi->param('lang') ) {
	$lang = quotemeta( $cgi->param('lang') );
}
if ( $cgi->url_param('saveformdata') ) {
	$saveformdata = quotemeta( $cgi->url_param('saveformdata') );
}
elsif ( $cgi->param('saveformdata') ) {
	$saveformdata = quotemeta( $cgi->param('saveformdata') );
}
if ( $cgi->url_param('clearcache') ) {
	$clearcache = quotemeta( $cgi->url_param('clearcache') );
}
elsif ( $cgi->param('clearcache') ) {
	$clearcache = quotemeta( $cgi->param('clearcache') );
}

##########################################################################
# Initialize html templates
##########################################################################

# Header # At the moment not in HTML::Template format
#$headertemplate = HTML::Template->new(filename => "$installfolder/templates/system/$lang/header.html");

# Main
$maintemplate = HTML::Template->new(
	filename => "$installfolder/templates/plugins/$psubfolder/multi/main.html",
	global_vars => 1,
	loop_context_vars => 1,
	die_on_bad_params => 0,
	associate => $cgi,
);

# Footer # At the moment not in HTML::Template format
#$footertemplate = HTML::Template->new(filename => "$installfolder/templates/system/$lang/footer.html");

##########################################################################
# Translations
##########################################################################

# Init Language
# Clean up lang variable
$lang         =~ tr/a-z//cd;
$lang         = substr($lang,0,2);

# Read Plugin transations
# Read English language as default
# Missing phrases in foreign language will fall back to English
$languagefileplugin 	= "$installfolder/templates/plugins/$psubfolder/en/language.txt";
Config::Simple->import_from($languagefileplugin, \%TPhrases);

# If there's no language phrases file for choosed language, use english as default
if (!-e "$installfolder/templates/system/$lang/language.dat")
{
  $lang = "en";
}

# Read foreign language if exists and not English
$languagefileplugin = "$installfolder/templates/plugins/$psubfolder/$lang/language.txt";
if ((-e $languagefileplugin) and ($lang ne 'en')) {
	# Now overwrite phrase variables with user language
	Config::Simple->import_from($languagefileplugin, \%TPhrases);
}

# Parse Language phrases to html templates
while (my ($name, $value) = each %TPhrases){
	$maintemplate->param("T::$name" => $value);
	#$headertemplate->param("T::$name" => $value);
	#$footertemplate->param("T::$name" => $value);
}

##########################################################################
# Main program
##########################################################################

&form;

exit;

#####################################################
# 
# Subroutines
#
#####################################################

#####################################################
# Form-Sub
#####################################################

sub form 
{

	# Clear Cache
	if ( $clearcache ) {
		system("rm /var/run/shm/$psubfolder/* > /dev/null 2>&1");
	}

	# If the form was saved, update config file
	if ( $saveformdata ) {
		$plugin_cfg->param( "MAIN.READ", $cgi->param('read') );
		$plugin_cfg->param( "MAIN.CRON", $cgi->param('cron') );
		$plugin_cfg->param( "MAIN.SENDUDP", $cgi->param('sendudp') );
		$plugin_cfg->param( "MAIN.UDPPORT", $cgi->param('udpport') );
		foreach (@heads) {
			$serial = $_;
			$serial =~ s%/dev/serial/smartmeter/%%g;
			$plugin_cfg->param("$serial.NAME", $cgi->param("$serial\_name") );
			$plugin_cfg->param("$serial.METER", $cgi->param("$serial\_meter") );
			if ( $cgi->param("$serial\_meter") eq "manual" ) {
				$plugin_cfg->param("$serial.PROTOCOL", $cgi->param("$serial\_protocol") );
				$plugin_cfg->param("$serial.STARTBAUDRATE", $cgi->param("$serial\_startbaudrate") );
				$plugin_cfg->param("$serial.BAUDRATE", $cgi->param("$serial\_baudrate") );
				$plugin_cfg->param("$serial.TIMEOUT", $cgi->param("$serial\_timeout") );
				$plugin_cfg->param("$serial.DELAY", $cgi->param("$serial\_delay") );
				$plugin_cfg->param("$serial.HANDSHAKE", $cgi->param("$serial\_handshake") );
				$plugin_cfg->param("$serial.DATABITS", $cgi->param("$serial\_databits") );
				$plugin_cfg->param("$serial.STOPBITS", $cgi->param("$serial\_stopbits") );
				$plugin_cfg->param("$serial.PARITY", $cgi->param("$serial\_parity") );
			} else {
				$plugin_cfg->param("$serial.PROTOCOL", "");
				$plugin_cfg->param("$serial.STARTBAUDRATE", "");
				$plugin_cfg->param("$serial.BAUDRATE", "");
				$plugin_cfg->param("$serial.TIMEOUT", "");
				$plugin_cfg->param("$serial.DELAY", "");
				$plugin_cfg->param("$serial.HANDSHAKE", "");
				$plugin_cfg->param("$serial.DATABITS", "");
				$plugin_cfg->param("$serial.STOPBITS", "");
				$plugin_cfg->param("$serial.PARITY", "");
			}
		}
		$plugin_cfg->save;

		# Create Cronjob
		if ( $cgi->param('read') eq "1" ) 
		{
			if ($cgi->param('cron') eq "1") 
			{
				system ("ln -s $installfolder/webfrontend/cgi/plugins/$psubfolder/bin/fetch.pl $installfolder/system/cron/cron.01min/$pname");
				unlink ("$installfolder/system/cron/cron.03min/$pname");
				unlink ("$installfolder/system/cron/cron.05min/$pname");
				unlink ("$installfolder/system/cron/cron.10min/$pname");
				unlink ("$installfolder/system/cron/cron.15min/$pname");
				unlink ("$installfolder/system/cron/cron.30min/$pname");
				unlink ("$installfolder/system/cron/cron.hourly/$pname");
			}
			if ($cgi->param('cron') eq "3") 
			{
				system ("ln -s $installfolder/webfrontend/cgi/plugins/$psubfolder/bin/fetch.pl $installfolder/system/cron/cron.03min/$pname");
				unlink ("$installfolder/system/cron/cron.01min/$pname");
				unlink ("$installfolder/system/cron/cron.05min/$pname");
				unlink ("$installfolder/system/cron/cron.10min/$pname");
				unlink ("$installfolder/system/cron/cron.15min/$pname");
				unlink ("$installfolder/system/cron/cron.30min/$pname");
				unlink ("$installfolder/system/cron/cron.hourly/$pname");
			}
			if ($cgi->param('cron') eq "5") 
			{
				system ("ln -s $installfolder/webfrontend/cgi/plugins/$psubfolder/bin/fetch.pl $installfolder/system/cron/cron.05min/$pname");
				unlink ("$installfolder/system/cron/cron.01min/$pname");
				unlink ("$installfolder/system/cron/cron.03min/$pname");
				unlink ("$installfolder/system/cron/cron.10min/$pname");
				unlink ("$installfolder/system/cron/cron.15min/$pname");
				unlink ("$installfolder/system/cron/cron.30min/$pname");
				unlink ("$installfolder/system/cron/cron.hourly/$pname");
			}
			if ($cgi->param('cron') eq "10") 
			{
				system ("ln -s $installfolder/webfrontend/cgi/plugins/$psubfolder/bin/fetch.pl $installfolder/system/cron/cron.10min/$pname");
				unlink ("$installfolder/system/cron/cron.1min/$pname");
				unlink ("$installfolder/system/cron/cron.3min/$pname");
				unlink ("$installfolder/system/cron/cron.5min/$pname");
				unlink ("$installfolder/system/cron/cron.15min/$pname");
				unlink ("$installfolder/system/cron/cron.30min/$pname");
				unlink ("$installfolder/system/cron/cron.hourly/$pname");
			}
			if ($cgi->param('cron') eq "15") 
			{
				system ("ln -s $installfolder/webfrontend/cgi/plugins/$psubfolder/bin/fetch.pl $installfolder/system/cron/cron.15min/$pname");
				unlink ("$installfolder/system/cron/cron.01min/$pname");
				unlink ("$installfolder/system/cron/cron.03min/$pname");
				unlink ("$installfolder/system/cron/cron.05min/$pname");
				unlink ("$installfolder/system/cron/cron.10min/$pname");
				unlink ("$installfolder/system/cron/cron.30min/$pname");
				unlink ("$installfolder/system/cron/cron.hourly/$pname");
			}
			if ($cgi->param('cron') eq "30") 
			{
				system ("ln -s $installfolder/webfrontend/cgi/plugins/$psubfolder/bin/fetch.pl $installfolder/system/cron/cron.30min/$pname");
				unlink ("$installfolder/system/cron/cron.01min/$pname");
				unlink ("$installfolder/system/cron/cron.03min/$pname");
				unlink ("$installfolder/system/cron/cron.05min/$pname");
				unlink ("$installfolder/system/cron/cron.10min/$pname");
				unlink ("$installfolder/system/cron/cron.15min/$pname");
				unlink ("$installfolder/system/cron/cron.hourly/$pname");
			}
			if ($cgi->param('cron') eq "60") 
			{
				system ("ln -s $installfolder/webfrontend/cgi/plugins/$psubfolder/bin/fetch.pl $installfolder/system/cron/cron.hourly/$pname");
				unlink ("$installfolder/system/cron/cron.01min/$pname");
				unlink ("$installfolder/system/cron/cron.03min/$pname");
				unlink ("$installfolder/system/cron/cron.05min/$pname");
				unlink ("$installfolder/system/cron/cron.10min/$pname");
				unlink ("$installfolder/system/cron/cron.15min/$pname");
				unlink ("$installfolder/system/cron/cron.30min/$pname");
			}
			  
		} else {
			unlink ("$installfolder/system/cron/cron.01min/$pname");
			unlink ("$installfolder/system/cron/cron.03min/$pname");
			unlink ("$installfolder/system/cron/cron.05min/$pname");
			unlink ("$installfolder/system/cron/cron.10min/$pname");
			unlink ("$installfolder/system/cron/cron.15min/$pname");
			unlink ("$installfolder/system/cron/cron.30min/$pname");
			unlink ("$installfolder/system/cron/cron.hourly/$pname");
		}

	}
	
	# The page title read from language file + our name
	#$template_title = $phrase->param("TXT0000") . ": " . $pname;

	# Print Template header
	&lbheader;

	# Read options and set them for template
	$maintemplate->param( PSUBFOLDER	=> $psubfolder );
	$maintemplate->param( HOST 		=> $ENV{HTTP_HOST} );
	$maintemplate->param( LOGINNAME		=> $ENV{REMOTE_USER} );
	$maintemplate->param( READ 		=> $plugin_cfg->param("MAIN.READ") );
	$maintemplate->param( CRON 		=> $plugin_cfg->param("MAIN.CRON") );
	$maintemplate->param( SENDUDP 		=> $plugin_cfg->param("MAIN.SENDUDP") );
	$maintemplate->param( UDPPORT 		=> $plugin_cfg->param("MAIN.UDPPORT") );

  	# Read the config for all found heads
	my $i = 0;
	foreach (@heads) {
		$serial = $_;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		if ( $plugin_cfg->param("$serial.DEVICE") ) {
			%{"hash".$i} = (
			NAME 		=>	$plugin_cfg->param("$serial.NAME"),
			SERIAL		=>	$plugin_cfg->param("$serial.SERIAL"),
			DEVICE		=>	$plugin_cfg->param("$serial.DEVICE"),
			METER		=>	$plugin_cfg->param("$serial.METER"),
			PROTOCOL	=>	$plugin_cfg->param("$serial.PROTOCOL"),
			STARTBAUDRATE	=>	$plugin_cfg->param("$serial.STARTBAUDRATE"),
			BAUDRATE	=>	$plugin_cfg->param("$serial.BAUDRATE"),
			TIMEOUT		=>	$plugin_cfg->param("$serial.TIMEOUT"),
			DELAY		=>	$plugin_cfg->param("$serial.DELAY"),
			HANDSHAKE	=>	$plugin_cfg->param("$serial.HANDSHAKE"),
			DATABITS	=>	$plugin_cfg->param("$serial.DATABITS"),
			STOPBITS	=>	$plugin_cfg->param("$serial.STOPBITS"),
			PARITY		=>	$plugin_cfg->param("$serial.PARITY"),
			);
			push (@rows, \%{"hash".$i});
			$i++;
		} 
	}
	$maintemplate->param( ROWS => \@rows );

	# Print Template
	print $maintemplate->output;

	# Parse page footer		
	&lbfooter;

	exit;

}

#####################################################
# Page-Header-Sub
#####################################################

sub lbheader 
{
	 # Create Help page
  $helplink = "http://www.loxwiki.eu/display/LOXBERRY/SML-eMon";
  open(F,"$installfolder/templates/plugins/$psubfolder/multi/help.html") || die "Missing template plugins/$psubfolder/$lang/help.html";
    @help = <F>;
    foreach (@help)
    {
      $_ =~ s/<!--\$psubfolder-->/$psubfolder/g;
      s/[\n\r]/ /g;
      $_ =~ s/<!--\$(.*?)-->/${$1}/g;
      $helptext = $helptext . $_;
    }
  close(F);
  open(F,"$installfolder/templates/system/$lang/header.html") || die "Missing template system/$lang/header.html";
    while (<F>) 
    {
      $_ =~ s/<!--\$(.*?)-->/${$1}/g;
      print $_;
    }
  close(F);
}

#####################################################
# Footer
#####################################################

sub lbfooter 
{
  open(F,"$installfolder/templates/system/$lang/footer.html") || die "Missing template system/$lang/footer.html";
    while (<F>) 
    {
      $_ =~ s/<!--\$(.*?)-->/${$1}/g;
      print $_;
    }
  close(F);
}
