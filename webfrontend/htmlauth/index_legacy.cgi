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
use JSON::PP;
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
our $template_title;
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
my  $meter_templates_cache;
my  @legacy_meter_fields = qw(METER PROTOCOL STARTBAUDRATE BAUDRATE TIMEOUT DELAY HANDSHAKE DATABITS STOPBITS PARITY CRC);

##########################################################################
# Read crontab
##########################################################################

my $crontab = new Config::Crontab;
$crontab->system(1); ## Wichtig, damit der User im File berücksichtigt wird
$crontab->read( -file => "$lbhomedir/system/cron/cron.d/$lbpplugindir" );


##########################################################################
# Read Settings
##########################################################################

# Version fallback. The installed plugin metadata overrides this below.
$version = "unknown";

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

my $installed_plugin_cfg = Config::Simple->new("$installfolder/data/system/install/$psubfolder/plugin.cfg");
my $plugin_title = "Smartmeter v2";
if ($installed_plugin_cfg) {
	$version = $installed_plugin_cfg->param("PLUGIN.VERSION") || $version;
	$plugin_title = $installed_plugin_cfg->param("PLUGIN.TITLE") || $plugin_title;
}
$template_title = "$plugin_title V$version";

# Create temp folder if not already exist
if (!-d $runtime_dir) {
	make_path($runtime_dir);
}
# Check for temporary log folder
if (!-e "$installfolder/log/plugins/$psubfolder/shm") {
	symlink($runtime_dir, "$installfolder/log/plugins/$psubfolder/shm");
}

# Detect connected and already configured IR heads.
my %head_paths = map { $_ => 1 } glob("/dev/serial/smartmeter/*");
my %plugin_config_hash_for_heads;
Config::Simple->import_from("$installfolder/config/plugins/$psubfolder/smartmeter.cfg", \%plugin_config_hash_for_heads);
while (my ($configname, $configvalue) = each %plugin_config_hash_for_heads) {
	$head_paths{$configvalue} = 1 if ($configname =~ /\.DEVICE\z/ && $configvalue);
}
my @heads = sort keys %head_paths;

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
	if ( !defined($plugin_cfg->param("$serial.LEGACY_METER")) ) {
		foreach my $field (@legacy_meter_fields) {
			my $value = $plugin_cfg->param("$serial.$field");
			$value = $field eq "METER" ? "0" : "" if (!defined($value));
			$plugin_cfg->param("$serial.LEGACY_$field", $value);
		}
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
		my $implementation = &implementation_mode();
		if ( ($cgi->param('implementation_changed') || "") eq "1" ) {
			$implementation = &clean_config_value($cgi->param('implementation'), qr/\A(?:none|legacy)\z/, $implementation );
		}
		$plugin_cfg->param( "MAIN.IMPLEMENTATION", $implementation );
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
			$plugin_cfg->param("$serial.LEGACY_METER", &clean_config_value($cgi->param("$serial\_meter"), qr/\A[A-Za-z0-9_.:-]+\z/, "0") );
			if ( $cgi->param("$serial\_meter") eq "manual" ) {
				$plugin_cfg->param("$serial.LEGACY_PROTOCOL", &clean_config_value($cgi->param("$serial\_protocol"), qr/\A[A-Za-z0-9_.:-]*\z/, "") );
				$plugin_cfg->param("$serial.LEGACY_STARTBAUDRATE", &clean_config_value($cgi->param("$serial\_startbaudrate"), qr/\A\d*\z/, "") );
				$plugin_cfg->param("$serial.LEGACY_BAUDRATE", &clean_config_value($cgi->param("$serial\_baudrate"), qr/\A\d*\z/, "") );
				$plugin_cfg->param("$serial.LEGACY_TIMEOUT", &clean_config_value($cgi->param("$serial\_timeout"), qr/\A\d*\z/, "") );
				$plugin_cfg->param("$serial.LEGACY_DELAY", &clean_config_value($cgi->param("$serial\_delay"), qr/\A\d*\z/, "") );
				$plugin_cfg->param("$serial.LEGACY_HANDSHAKE", &clean_config_value($cgi->param("$serial\_handshake"), qr/\A[A-Za-z0-9_.:-]*\z/, "") );
				$plugin_cfg->param("$serial.LEGACY_DATABITS", &clean_config_value($cgi->param("$serial\_databits"), qr/\A\d*\z/, "") );
				$plugin_cfg->param("$serial.LEGACY_STOPBITS", &clean_config_value($cgi->param("$serial\_stopbits"), qr/\A\d*\z/, "") );
				$plugin_cfg->param("$serial.LEGACY_PARITY", &clean_config_value($cgi->param("$serial\_parity"), qr/\A[A-Za-z0-9_.:-]*\z/, "") );
				$plugin_cfg->param("$serial.LEGACY_CRC", &clean_config_value($cgi->param("$serial\_crc"), qr/\A[A-Za-z0-9_.:-]*\z/, "") );
			}
		}
		$plugin_cfg->save;

		if ( $implementation eq "legacy" ) {
			&apply_legacy_runtime;
			&run_vzlogger_control("disable-vzlogger");
		} else {
			&remove_cronjobs;
			&run_vzlogger_control("disable-vzlogger");
		}
	}
	
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
	my $implementation = &implementation_mode();
	$maintemplate->param( IMPLEMENTATION 	=> $implementation );
	$maintemplate->param( IMPLEMENTATION_SWITCH_VALUE => ($implementation eq "legacy" ? "legacy" : "none") );
	$maintemplate->param( VZLOGGER_IMPLEMENTATION_ACTIVE => ($implementation eq "vzlogger") );
	$maintemplate->param( LEGACY_IMPLEMENTATION_ACTIVE => ($implementation eq "legacy") );
	my %parity_names = (n => "none", e => "even", o => "odd");
	my $meter_template_options = [ map {
		my $serial_mode = lc($_->{serial_mode} || "");
		$serial_mode =~ /\A([78])([neo])([12])\z/ or die "Invalid serial mode '$serial_mode' in meter template '$_->{id}'";
		my ($databits, $parity, $stopbits) = ($1, $2, $3);
		my $legacy = $_->{legacy} || {};
		{
			ID => $_->{id},
			LABEL => $_->{label},
			PROTOCOL_LABEL => uc($_->{protocol}),
			STARTBAUDRATE => $_->{initial_baudrate},
			BAUDRATE => $_->{read_baudrate},
			TIMEOUT => $_->{read_timeout},
			DELAY => $legacy->{delay},
			HANDSHAKE => $legacy->{handshake} || "none",
			DATABITS => $databits,
			PARITY => $parity_names{$parity},
			STOPBITS => $stopbits,
			CRC => $legacy->{crc} || "",
		}
	} @{load_meter_templates()} ];

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
			METER		=>	$plugin_cfg->param("$serial.LEGACY_METER"),
			PROTOCOL	=>	$plugin_cfg->param("$serial.LEGACY_PROTOCOL"),
			STARTBAUDRATE	=>	$plugin_cfg->param("$serial.LEGACY_STARTBAUDRATE"),
			BAUDRATE	=>	$plugin_cfg->param("$serial.LEGACY_BAUDRATE"),
			TIMEOUT		=>	$plugin_cfg->param("$serial.LEGACY_TIMEOUT"),
			DELAY		=>	$plugin_cfg->param("$serial.LEGACY_DELAY"),
			HANDSHAKE	=>	$plugin_cfg->param("$serial.LEGACY_HANDSHAKE"),
			DATABITS	=>	$plugin_cfg->param("$serial.LEGACY_DATABITS"),
			STOPBITS	=>	$plugin_cfg->param("$serial.LEGACY_STOPBITS"),
			PARITY		=>	$plugin_cfg->param("$serial.LEGACY_PARITY"),
			CRC		    =>	$plugin_cfg->param("$serial.LEGACY_CRC"),
			METER_TEMPLATES => $meter_template_options,
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

sub load_meter_templates
{
	return $meter_templates_cache if ($meter_templates_cache);
	my $catalog_file = "$installfolder/templates/plugins/$psubfolder/meter_templates.json";
	open(my $catalog_fh, "<", $catalog_file) or die "Could not read meter template catalog $catalog_file: $!";
	local $/;
	my $json = <$catalog_fh>;
	close($catalog_fh);
	my $templates = eval { JSON::PP->new->utf8->decode($json) };
	die "Invalid meter template catalog $catalog_file: $@" if (!$templates || ref($templates) ne "ARRAY");
	my %ids;
	foreach my $entry (@{$templates}) {
		my $id = ref($entry) eq "HASH" ? ($entry->{id} || "") : "";
		die "Invalid or duplicate meter template id '$id'" if ($id !~ /\A[A-Za-z0-9_.:-]+\z/ || $ids{$id}++);
		die "Invalid protocol in meter template '$id'" if (($entry->{protocol} || "") !~ /\A(?:sml|d0)\z/);
	}
	$meter_templates_cache = $templates;
	return $meter_templates_cache;
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

sub apply_legacy_runtime
{
	if ( $plugin_cfg->param("MAIN.READ") eq "1" )
	{
		&remove_cronjobs;
		if ($plugin_cfg->param("MAIN.CRON") eq "M")
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
		if ($plugin_cfg->param("MAIN.CRON") eq "1")
		{
			&create_cronjob("cron.01min", "fetch.pl");
		}
		if ($plugin_cfg->param("MAIN.CRON") eq "3")
		{
			&create_cronjob("cron.03min", "fetch.pl");
		}
		if ($plugin_cfg->param("MAIN.CRON") eq "5")
		{
			&create_cronjob("cron.05min", "fetch.pl");
		}
		if ($plugin_cfg->param("MAIN.CRON") eq "10")
		{
			&create_cronjob("cron.10min", "fetch.pl");
		}
		if ($plugin_cfg->param("MAIN.CRON") eq "15")
		{
			&create_cronjob("cron.15min", "fetch.pl");
		}
		if ($plugin_cfg->param("MAIN.CRON") eq "30")
		{
			&create_cronjob("cron.30min", "fetch.pl");
		}
		if ($plugin_cfg->param("MAIN.CRON") eq "60")
		{
			&create_cronjob("cron.hourly", "fetch.pl");
		}
	} else {
		&remove_cronjobs;
	}
}

sub run_vzlogger_control
{
	my ($action) = @_;
	my $script = "$installfolder/bin/plugins/$psubfolder/vzlogger_control.pl";
	return if (!-e $script);
	my $output = `$^X "$script" "$action" 2>&1`;
	return $output;
}

sub implementation_mode
{
	my $mode = $plugin_cfg->param("MAIN.IMPLEMENTATION") || "";
	return $mode if ($mode =~ /\A(?:none|legacy|vzlogger)\z/);
	return (($plugin_cfg->param("MAIN.READ") || "0") eq "1") ? "legacy" : "vzlogger";
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
