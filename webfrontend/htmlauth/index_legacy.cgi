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
use Config::Crontab;
use LoxBerry::Log;
use File::HomeDir;
#use HTML::Entities;
use String::Escape qw( unquotemeta );
use Cwd 'abs_path';
use HTML::Template;
use File::Path qw(make_path);
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
my  $crontabtmp = "$lbplogdir/crontab.temp";
my  $runtime_dir;

##########################################################################
# Read crontab
##########################################################################

my $crontab = new Config::Crontab;
$crontab->system(1); ## Wichtig, damit der User im File berücksichtigt wird
$crontab->read( -file => "$lbhomedir/system/cron/cron.d/$lbpplugindir" );


##########################################################################
# Read Settings
##########################################################################

# Version of this script
$version = "2.0.0.5";

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
$runtime_dir = "/var/run/shm/$psubfolder";

# Read plugin config
$plugin_cfg 	= new Config::Simple("$installfolder/config/plugins/$psubfolder/smartmeter.cfg") or die $plugin_cfg->error();
$pname          = $plugin_cfg->param("MAIN.SCRIPTNAME");
$plugin_cfg->param("MAIN.SENDMQTT", "0") if (!defined $plugin_cfg->param("MAIN.SENDMQTT"));
$plugin_cfg->param("MAIN.MQTTTOPIC", "smartmeter") if (!$plugin_cfg->param("MAIN.MQTTTOPIC"));

# Create temp folder if not already exist
if (!-d $runtime_dir) {
	make_path($runtime_dir);
}
# Check for temporary log folder
if (!-e "$installfolder/log/plugins/$psubfolder/shm") {
	symlink($runtime_dir, "$installfolder/log/plugins/$psubfolder/shm");
}

# Detect which IR Heads are connected
my @heads = glob("/dev/serial/smartmeter/*");

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
        $plugin_cfg->param("$serial.CRC", "");
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
		foreach my $cache_file (glob("$runtime_dir/*")) {
			next if ($cache_file =~ /\/fetch\.lock\z/);
			unlink($cache_file);
		}
	}

	# If the form was saved, update config file
	if ( $saveformdata ) {
		$plugin_cfg->param( "MAIN.READ", $cgi->param('read') );
		$plugin_cfg->param( "MAIN.CRON", $cgi->param('cron') );
		$plugin_cfg->param( "MAIN.SENDUDP", $cgi->param('sendudp') );
		$plugin_cfg->param( "MAIN.UDPPORT", $cgi->param('udpport') );
		$plugin_cfg->param( "MAIN.SENDMQTT", $cgi->param('sendmqtt') );
		$plugin_cfg->param( "MAIN.MQTTTOPIC", $cgi->param('mqtttopic') || "smartmeter" );
		foreach (@heads) {
			$serial = $_;
			$serial =~ s%/dev/serial/smartmeter/%%g;
			$plugin_cfg->param("$serial.NAME", $cgi->param("$serial\_name") );
			$plugin_cfg->param("$serial.METER", &clean_config_value($cgi->param("$serial\_meter"), qr/\A[A-Za-z0-9_.:-]+\z/, "0") );
			if ( $cgi->param("$serial\_meter") eq "manual" ) {
				$plugin_cfg->param("$serial.PROTOCOL", &clean_config_value($cgi->param("$serial\_protocol"), qr/\A[A-Za-z0-9_.:-]*\z/, "") );
				$plugin_cfg->param("$serial.STARTBAUDRATE", &clean_config_value($cgi->param("$serial\_startbaudrate"), qr/\A\d*\z/, "") );
				$plugin_cfg->param("$serial.BAUDRATE", &clean_config_value($cgi->param("$serial\_baudrate"), qr/\A\d*\z/, "") );
				$plugin_cfg->param("$serial.TIMEOUT", &clean_config_value($cgi->param("$serial\_timeout"), qr/\A\d*\z/, "") );
				$plugin_cfg->param("$serial.DELAY", &clean_config_value($cgi->param("$serial\_delay"), qr/\A\d*\z/, "") );
				$plugin_cfg->param("$serial.HANDSHAKE", &clean_config_value($cgi->param("$serial\_handshake"), qr/\A[A-Za-z0-9_.:-]*\z/, "") );
				$plugin_cfg->param("$serial.DATABITS", &clean_config_value($cgi->param("$serial\_databits"), qr/\A\d*\z/, "") );
				$plugin_cfg->param("$serial.STOPBITS", &clean_config_value($cgi->param("$serial\_stopbits"), qr/\A\d*\z/, "") );
				$plugin_cfg->param("$serial.PARITY", &clean_config_value($cgi->param("$serial\_parity"), qr/\A[A-Za-z0-9_.:-]*\z/, "") );
				$plugin_cfg->param("$serial.CRC", &clean_config_value($cgi->param("$serial\_crc"), qr/\A[A-Za-z0-9_.:-]*\z/, "") );
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
				$plugin_cfg->param("$serial.CRC", "");
			}
		}
		$plugin_cfg->save;

		# Create Cronjob
		if ( $cgi->param('read') eq "1" ) 
		{
			&remove_cronjobs;
			if ($cgi->param('cron') eq "M") 
			{
				# Check if Script already running?
				my $logger_running = 0;
				if (open(my $ps_fh, "-|", "ps", "aux")) {
					$logger_running = scalar(grep{/sm_logger.pl/} <$ps_fh>);
					close($ps_fh);
				}
				if (!$logger_running)
				{	
					my $pid = fork();
					if (defined $pid && $pid == 0) {
						open STDIN, "</dev/null";
						open STDOUT, ">/dev/null";
						open STDERR, ">/dev/null";
						exec($^X, "$installfolder/bin/plugins/$psubfolder/fetch.pl");
						exit;
					}
				}
				&create_cronjob("cron.reboot", "reboot_cron_runner.sh");
			}
			if ($cgi->param('cron') eq "1") 
			{
				&create_cronjob("cron.01min", "fetch.pl");
			}
			if ($cgi->param('cron') eq "3") 
			{
				&create_cronjob("cron.03min", "fetch.pl");
			}
			if ($cgi->param('cron') eq "5") 
			{
				&create_cronjob("cron.05min", "fetch.pl");
			}
			if ($cgi->param('cron') eq "10") 
			{
				&create_cronjob("cron.10min", "fetch.pl");
			}
			if ($cgi->param('cron') eq "15") 
			{
				&create_cronjob("cron.15min", "fetch.pl");
			}
			if ($cgi->param('cron') eq "30") 
			{
				&create_cronjob("cron.30min", "fetch.pl");
			}
			if ($cgi->param('cron') eq "60") 
			{
				&create_cronjob("cron.hourly", "fetch.pl");
			}
			  
		} else {
			&remove_cronjobs;
		}

	}
	
	# The page title read from language file + our name
	#$template_title = $phrase->param("TXT0000") . ": " . $pname;
	
	# Navbar
	our %navbar;

	$navbar{10}{Name} = "Test";
	$navbar{10}{URL} = 'index.cgi?form=owfs';
	$navbar{10}{active} = 1 if $q->{form} eq "owfs";
	
	$navbar{20}{Name} = "Test2";
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
	$maintemplate->param( SENDMQTT 		=> $plugin_cfg->param("MAIN.SENDMQTT") );
	$maintemplate->param( MQTTTOPIC 		=> $plugin_cfg->param("MAIN.MQTTTOPIC") || "smartmeter" );

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
			CRC		    =>	$plugin_cfg->param("$serial.CRC"),
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

sub remove_cronjobs
{
	foreach my $cronfolder ("cron.01min", "cron.03min", "cron.05min", "cron.10min", "cron.15min", "cron.30min", "cron.hourly", "cron.reboot") {
		unlink ("$installfolder/system/cron/$cronfolder/$pname");
	}
}

sub create_cronjob
{
	my ($cronfolder, $scriptname) = @_;
	my $source = "$installfolder/bin/plugins/$psubfolder/$scriptname";
	my $target = "$installfolder/system/cron/$cronfolder/$pname";

	unlink ($target);
	symlink ($source, $target);
}

sub clean_config_value
{
	my ($value, $pattern, $default) = @_;
	return $default if (!defined($value));
	return $value if ($value =~ $pattern);
	return $default;
}

#####################################################
# Page-Header-Sub
#####################################################

sub lbheader 
{
	 # Create Help page
  $helplink = "https://www.loxwiki.eu/x/mA-L";
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
