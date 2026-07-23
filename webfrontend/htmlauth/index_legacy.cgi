#!/usr/bin/perl

use strict;
use warnings;

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
use LoxBerry::System;
use File::HomeDir;
use Cwd 'abs_path';
use HTML::Template;
use File::Path qw(make_path);
use FindBin;
use JSON::PP;
use lib $lbpbindir;
use lib "$FindBin::Bin/../../bin";
use SmartMeterVZLoggerConfig qw(validate_legacy_general implementation_mode set_implementation_mode);
use SmartMeterVZLoggerRuntime qw(acquire_config_lock);
use SmartMeterLegacyRuntime qw(initialize_legacy_heads acquire_legacy_fetch_lock remove_legacy_cronjobs synchronize_legacy_runtime clear_legacy_cache vzlogger_service_running);
umask(0027);

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
my  %TPhrases;
my  @rows;
my  $maintemplate;
my  $template_title;
my  $saveformdata;
my  $clearcache;
my  $runtime_dir;
my  $meter_templates_cache;
my  $validation_error = "";


##########################################################################
# Read Settings
##########################################################################

# Version fallback. The installed plugin metadata overrides this below.
$version = "unknown";

# Figure out in which subfolder we are installed
$psubfolder = abs_path($0);
$psubfolder =~ s/(.*)\/(.*)\/(.*)$/$2/g;

# Read general config
$cfg	 	= new Config::Simple("$home/config/system/general.cfg") or die $cfg->error();
$installfolder	= $cfg->param("BASE.INSTALLFOLDER");
$lang		= $cfg->param("BASE.LANG");
$runtime_dir = "/var/run/shm/$psubfolder";

# Read plugin config
$plugin_cfg 	= new Config::Simple("$installfolder/config/plugins/$psubfolder/smartmeter.cfg") or die $plugin_cfg->error();
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
chmod(0750, $runtime_dir);
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

{
	my ($initialization_lock, $lock_error) = acquire_config_lock($runtime_dir);
	die "$lock_error\n" if (!$initialization_lock);
	local $ENV{SMARTMETER_CONFIG_LOCK_HELD} = "1";
	$plugin_cfg->save if (initialize_legacy_heads($plugin_cfg, @heads));
}

# Set parameters coming in - get over post
my $requested_lang = $cgi->param('lang');
$lang = $requested_lang if (defined($requested_lang));
$lang =~ tr/a-z//cd;
$lang = substr($lang, 0, 2) || "en";
my $is_post = ($ENV{REQUEST_METHOD} || "GET") eq "POST";
$saveformdata = $is_post && ($cgi->param('saveformdata') || "") eq "1";
$clearcache = $is_post && ($cgi->param('action') || "") eq "clearcache";

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

# LoxBerry loads the selected plugin language and fills missing phrases from English.
%TPhrases = LoxBerry::System::readlanguage($maintemplate, "language.ini");

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
		if (implementation_mode($plugin_cfg) ne "legacy") {
			$validation_error = $TPhrases{"LEGACY.ACTION_REQUIRES_ACTIVE"} || "Legacy must be active for this action.";
		} else {
			my ($config_lock, $config_error) = acquire_config_lock($runtime_dir);
			if (!$config_lock) {
				$validation_error = $config_error;
			} else {
				my ($fetch_lock, $fetch_error) = acquire_legacy_fetch_lock($runtime_dir);
				if (!$fetch_lock) {
					$validation_error = $fetch_error;
				} else {
					my ($removed, $cache_error) = clear_legacy_cache($runtime_dir);
					$validation_error = $cache_error if ($cache_error);
				}
			}
		}
	}

	# If the form was saved, update config file
	if ( $saveformdata ) {
		my $previous_implementation = implementation_mode($plugin_cfg);
		my $implementation = $previous_implementation;
		my $invalid_implementation = 0;
		if ( ($cgi->param('implementation_changed') || "") eq "1" ) {
			my $submitted = scalar($cgi->param('implementation'));
			if (defined($submitted) && $submitted =~ /\A(?:none|legacy)\z/) { $implementation = $submitted; }
			else { $invalid_implementation = 1; }
		}
		my %meter_ids = map { $_->{id} => 1 } @{load_meter_templates()};
		my @submitted_meters;
		foreach my $head (@heads) {
			my $head_serial = $head;
			$head_serial =~ s%/dev/serial/smartmeter/%%g;
			push @submitted_meters, {
				serial => $head_serial, meter => scalar($cgi->param("$head_serial\_meter")),
				protocol => scalar($cgi->param("$head_serial\_protocol")),
				startbaudrate => scalar($cgi->param("$head_serial\_startbaudrate")),
				baudrate => scalar($cgi->param("$head_serial\_baudrate")),
				timeout => scalar($cgi->param("$head_serial\_timeout")), delay => scalar($cgi->param("$head_serial\_delay")),
				databits => scalar($cgi->param("$head_serial\_databits")), stopbits => scalar($cgi->param("$head_serial\_stopbits")),
				parity => scalar($cgi->param("$head_serial\_parity")),
			};
		}
		my @validation_errors = $invalid_implementation ? ("IMPLEMENTATION") : $implementation eq "legacy" ? validate_legacy_general({
			implementation => $implementation,
			read => scalar($cgi->param('read')),
			cron => defined($cgi->param('cron')) ? scalar($cgi->param('cron')) : $plugin_cfg->param("MAIN.CRON"),
			sendudp => scalar($cgi->param('sendudp')),
			udpport => defined($cgi->param('udpport')) ? scalar($cgi->param('udpport')) : $plugin_cfg->param("MAIN.UDPPORT"),
			sendmqtt => scalar($cgi->param('sendmqtt')),
			mqtttopic => defined($cgi->param('mqtttopic')) ? scalar($cgi->param('mqtttopic')) : ($plugin_cfg->param("MAIN.MQTTTOPIC") || "smartmeter"),
			meters => \@submitted_meters,
		}, \%meter_ids) : ();
		if (@validation_errors) {
			$validation_error = ($TPhrases{"LEGACY.VALIDATION_ERROR"} || "Invalid values; nothing was saved:") . " " . join(", ", @validation_errors);
		} elsif ($implementation ne "vzlogger") {
			my ($lock, $lock_error) = acquire_config_lock($runtime_dir);
			if (!$lock) {
				$validation_error = $lock_error;
			} else {
				local $ENV{SMARTMETER_CONFIG_LOCK_HELD} = "1";
				set_implementation_mode($plugin_cfg, $implementation);
				if ($implementation eq "legacy") {
					$plugin_cfg->param("MAIN.READ", scalar($cgi->param('read')));
					$plugin_cfg->param("MAIN.CRON", scalar($cgi->param('cron'))) if (defined($cgi->param('cron')));
					$plugin_cfg->param("MAIN.SENDUDP", scalar($cgi->param('sendudp')));
					$plugin_cfg->param("MAIN.UDPPORT", scalar($cgi->param('udpport'))) if (defined($cgi->param('udpport')));
					$plugin_cfg->param("MAIN.SENDMQTT", scalar($cgi->param('sendmqtt')));
					$plugin_cfg->param("MAIN.MQTTTOPIC", scalar($cgi->param('mqtttopic'))) if (defined($cgi->param('mqtttopic')));
					foreach my $device (@heads) {
						my $serial = $device;
						$serial =~ s%/dev/serial/smartmeter/%%g;
						my $meter = scalar($cgi->param("${serial}_meter"));
						$plugin_cfg->param("$serial.NAME", scalar($cgi->param("${serial}_name")));
						$plugin_cfg->param("$serial.LEGACY_METER", clean_config_value($meter, qr/\A[A-Za-z0-9_.:-]+\z/, "0"));
						if (defined($meter) && $meter eq "manual") {
							foreach my $field (qw(protocol startbaudrate baudrate timeout delay handshake databits stopbits parity crc)) {
								my $pattern = $field =~ /\A(?:startbaudrate|baudrate|timeout|delay|databits|stopbits)\z/ ? qr/\A\d*\z/ : qr/\A[A-Za-z0-9_.:-]*\z/;
								$plugin_cfg->param("$serial.LEGACY_" . uc($field), clean_config_value(scalar($cgi->param("${serial}_$field")), $pattern, ""));
							}
						}
					}
				}
				$plugin_cfg->save;
				my ($control_output, $control_exit) = run_vzlogger_control("disable-vzlogger");
				if ($control_exit != 0) {
					set_implementation_mode($plugin_cfg, $previous_implementation);
					$plugin_cfg->save;
					my ($rollback_output, $rollback_exit) = restore_implementation_runtime($previous_implementation);
					$validation_error = ($control_output || "Could not disable vzLogger.") . $rollback_output;
					$validation_error .= " Runtime rollback was incomplete." if ($rollback_exit != 0);
				} elsif ($implementation eq "legacy") {
					my ($runtime_output, $runtime_ok) = synchronize_legacy_runtime($installfolder, $psubfolder, $plugin_cfg, start_minimal_now => 1);
					if (!$runtime_ok) {
						set_implementation_mode($plugin_cfg, $previous_implementation);
						$plugin_cfg->save;
						remove_legacy_cronjobs($installfolder, $psubfolder);
						my ($rollback_output, $rollback_exit) = restore_implementation_runtime($previous_implementation);
						$validation_error = $runtime_output . $rollback_output;
						$validation_error .= " Runtime rollback was incomplete." if ($rollback_exit != 0);
					}
				} else {
					remove_legacy_cronjobs($installfolder, $psubfolder);
				}
			}
		}
	}

	# Print Template header
	load_page_header();

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
	$maintemplate->param( VALIDATION_ERROR => $validation_error );
	my $implementation = implementation_mode($plugin_cfg);
	$maintemplate->param( IMPLEMENTATION 	=> $implementation );
	$maintemplate->param( IMPLEMENTATION_SWITCH_VALUE => ($implementation eq "legacy" ? "legacy" : "none") );
	$maintemplate->param( VZLOGGER_IMPLEMENTATION_ACTIVE => ($implementation eq "vzlogger") );
	$maintemplate->param( LEGACY_IMPLEMENTATION_ACTIVE => ($implementation eq "legacy") );
	$maintemplate->param( VZLOGGER_SERVICE_ACTIVE => vzlogger_service_running() );
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
	foreach my $device (@heads) {
		my $serial = $device;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		if ( $plugin_cfg->param("$serial.DEVICE") ) {
			my %row = (
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
			push(@rows, \%row);
		} 
	}
	$maintemplate->param( ROWS => \@rows );

	# Print Template
	print $maintemplate->output;

	# Parse page footer		
	LoxBerry::Web::lbfooter();

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
		my $language = $TPhrases{'COMMON.LANGUAGE_CODE'} || "en";
		$entry->{label} = $entry->{"label_$language"} || $entry->{label_en} || $entry->{label};
	}
	$meter_templates_cache = $templates;
	return $meter_templates_cache;
}

sub run_vzlogger_control
{
	my ($action) = @_;
	my $script = "$installfolder/bin/plugins/$psubfolder/vzlogger_control.pl";
	return wantarray ? ("", 0) : "" if (!-e $script);
	my $output = `$^X "$script" "$action" 2>&1`;
	my $exit = $? >> 8;
	return wantarray ? ($output, $exit) : $output;
}

sub restore_implementation_runtime
{
	my ($implementation) = @_;
	if ($implementation eq "vzlogger") {
		remove_legacy_cronjobs($installfolder, $psubfolder);
		return run_vzlogger_control("activate-vzlogger");
	}
	my ($output, $exit) = run_vzlogger_control("disable-vzlogger");
	if ($implementation eq "legacy") {
		my ($runtime_output, $runtime_ok) = synchronize_legacy_runtime($installfolder, $psubfolder, $plugin_cfg);
		$output .= $runtime_output;
		$exit = 1 if (!$runtime_ok);
	} else {
		remove_legacy_cronjobs($installfolder, $psubfolder);
	}
	return ($output, $exit);
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

sub load_page_header
{
	require LoxBerry::Web;
	my $help_file = "$installfolder/templates/plugins/$psubfolder/multi/help.html";
	my $helptext = "";
	if (open(my $help_fh, "<", $help_file)) {
		local $/;
		$helptext = <$help_fh> || "";
		close($help_fh);
		$helptext =~ s/<!--\$psubfolder-->/$psubfolder/g;
	}
	LoxBerry::Web::lbheader($template_title, "https://www.loxwiki.eu/x/mA-L", $helptext);
}
