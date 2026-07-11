#!/usr/bin/perl

# Copyright 2019 Michael Schlenstedt, michael@loxberry.de
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
use Config::Simple;
use File::Path qw(make_path);
use LoxBerry::System;
#use LoxBerry::Web;
use LoxBerry::JSON; # Available with LoxBerry 2.0
use LoxBerry::Log;
use warnings;
use strict;

##########################################################################
# Variables
##########################################################################

my $log;

# Read Form
my $cgi = CGI->new;
my $q = $cgi->Vars;

my $version = LoxBerry::System::pluginversion();
my $template;
my $plugin_cfg;
my $initial_request = scalar(keys %{$q}) == 0;

# Language Phrases
my %L;

# Globals 
#my %pids;
#my $CFGFILEDEVICES = $lbpconfigdir . "/devices.json";
#my $CFGFILEMQTT = $lbpconfigdir . "/mqtt.json";
#my $CFGFILEOWFS = $lbpconfigdir . "/owfs.json";

##########################################################################
# AJAX
##########################################################################

if( $q->{ajax} ) {
	
	## Handle all ajax requests 
	require JSON;
	# require Time::HiRes;
	my %response;
	ajax_header();

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
	&load_plugin_language($template);
	
        # Default is the active implementation. Explicit tab clicks pass form=...
	$q->{form} = "vzlogger" if !$q->{form};

	if ($q->{form} eq "vzlogger") { &form_vzlogger() }
	elsif ($q->{form} eq "log") { &form_log() }

	# Print the form
	&form_print();
}

exit;

##########################################################################
# Form: OWFS
##########################################################################

sub form_vzlogger
{
	my $config_file = "$lbpconfigdir/smartmeter.cfg";
	$plugin_cfg = Config::Simple->new($config_file) or die "Could not read $config_file";

	ensure_vzlogger_defaults();
	if ($initial_request && implementation_mode() eq "legacy") {
		print $cgi->redirect(-url => "./index_legacy.cgi?form=legacy");
		exit;
	}
	my @heads = detect_heads();
	ensure_head_defaults(@heads);

	if ($q->{saveformdata}) {
		save_vzlogger_form(@heads);
		my $action = $q->{submitaction} || "apply";
		my $control_action = "apply";
		$control_action = "apply" if ($action eq "apply");
		$control_action = "validate" if ($action eq "validate");
		$control_action = "debug-log" if ($action eq "debug-log");
		$control_action = "restart-vzlogger" if ($action eq "restart-vzlogger");
		$control_action = "start-vzlogger" if ($action eq "start-vzlogger");
		$control_action = "stop-vzlogger" if ($action eq "stop-vzlogger");
		$control_action = "restart-bridge" if ($action eq "restart-bridge");
		$control_action = "start-bridge" if ($action eq "start-bridge");
		$control_action = "stop-bridge" if ($action eq "stop-bridge");
		my $output = ($control_action eq "apply") ? apply_selected_implementation() : run_control($control_action);
		if ($control_action eq "debug-log" && $output =~ m{Created debug log: \Q$lbhomedir\E/log/plugins/\Q$lbpplugindir\E/([^/\s]+)}) {
			print $cgi->redirect(-url => log_redirect_url("plugins/$lbpplugindir/$1"));
			exit;
		}
		if ($control_action eq "apply") {
			my $apply_log = "$lbhomedir/log/plugins/$lbpplugindir/vzlogger_apply.log";
			make_path("$lbhomedir/log/plugins/$lbpplugindir") if (!-d "$lbhomedir/log/plugins/$lbpplugindir");
			if (open(my $apply_fh, ">", $apply_log)) {
				print $apply_fh $output;
				close($apply_fh);
				$output .= "\nApply log: $apply_log\n";
			}
		}
		$template->param("VZLOGGER_MESSAGE", $output);
		$plugin_cfg = Config::Simple->new($config_file) or die "Could not reload $config_file";
	}

	my @rows = build_head_rows(@heads);
	my $local_port = $plugin_cfg->param("VZLOGGER.LOCALPORT") || 18080;
	my $mqtttopic = $plugin_cfg->param("MAIN.MQTTTOPIC") || "smartmeter";

	$template->param("FORM_VZLOGGER", 1);
	$template->param("IMPLEMENTATION" => implementation_mode());
	$template->param("READ" => $plugin_cfg->param("MAIN.READ") || 0);
	$template->param("CRON" => $plugin_cfg->param("MAIN.CRON") || 5);
	$template->param("SENDUDP" => $plugin_cfg->param("MAIN.SENDUDP") || 0);
	$template->param("UDPPORT" => $plugin_cfg->param("MAIN.UDPPORT") || 7000);
	$template->param("MQTTTOPIC" => $mqtttopic);
	$template->param("VZLOGGER_LOCALPORT" => $local_port);
	my $udp_interval = clean_udp_interval($plugin_cfg->param("VZLOGGER.UDPINTERVAL"), "5");
	$template->param("VZLOGGER_UDPINTERVAL" => $udp_interval);
	$template->param("VZLOGGER_UDPINTERVAL_OPTIONS" => udp_interval_options($udp_interval));
	$template->param("VZLOGGER_DEBUG" => $plugin_cfg->param("VZLOGGER.DEBUG") || 0);
	$template->param("VZLOGGER_SERVICE_DEBUG" => $plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG") || 0);
	$template->param("VZLOGGER_LOGLEVEL" => clean_log_level($plugin_cfg->param("VZLOGGER.LOGLEVEL"), "0"));
	add_service_template_params();
	$template->param("VZLOGGER_CONFIG" => "$lbpconfigdir/vzlogger.conf");
	$template->param("VZLOGGER_LIVEURL" => "http://$ENV{HTTP_HOST}:$local_port/");
	$template->param("VZLOGGER_RENDERED_URL" => "./vzlogger_live.cgi");
	add_http_cache_template_params(@rows);
	$template->param("ROWS" => \@rows);
	return();
}

sub add_service_template_params
{
	my $vzlogger_expected_active = implementation_mode() eq "vzlogger";
	my $bridge_expected_active = $vzlogger_expected_active
		&& (($plugin_cfg->param("MAIN.READ") || "0") eq "1");
	my $vzlogger_state = service_state("vzlogger");
	my $bridge_state = service_state("smartmeter-v2-vzlogger-bridge");

	$template->param("VZLOGGER_SERVICE_CONTROL_DISABLED" => ($vzlogger_expected_active ? "" : "disabled"));
	$template->param("BRIDGE_SERVICE_CONTROL_DISABLED" => ($bridge_expected_active ? "" : "disabled"));
	$template->param("VZLOGGER_SERVICE_STATUS" => service_summary("vzlogger"));
	$template->param("BRIDGE_SERVICE_STATUS" => service_summary("smartmeter-v2-vzlogger-bridge"));
	$template->param("VZLOGGER_SERVICE_STATUS_CLASS" => service_status_class($vzlogger_state, $vzlogger_expected_active));
	$template->param("BRIDGE_SERVICE_STATUS_CLASS" => service_status_class($bridge_state, $bridge_expected_active));
	$template->param("VZLOGGER_SERVICE_RUNNING" => $vzlogger_state eq "active");
	$template->param("BRIDGE_SERVICE_RUNNING" => $bridge_state eq "active");
	$template->param("VZLOGGER_LIVE_DISABLED" => ($vzlogger_state eq "active" ? "" : "ui-disabled"));

	my $vzlogger_log = "$lbhomedir/log/plugins/$lbpplugindir/vzlogger.log";
	my $bridge_log = "$lbhomedir/log/plugins/$lbpplugindir/vzlogger_mqtt_bridge.log";
	$template->param("VZLOGGER_LOG_URL" => log_url("plugins/$lbpplugindir/vzlogger.log"));
	$template->param("VZLOGGER_LOG_DISABLED" => (-e $vzlogger_log ? "" : "ui-disabled"));
	$template->param("BRIDGE_LOG_URL" => log_url("plugins/$lbpplugindir/vzlogger_mqtt_bridge.log"));
	$template->param("BRIDGE_LOG_DISABLED" => (-e $bridge_log ? "" : "ui-disabled"));
}

sub add_http_cache_template_params
{
	my (@rows) = @_;
	my @summaries;
	my $has_cache = 0;

	foreach my $row (@rows) {
		my $serial = $row->{SERIAL} || next;
		my $cache_file = "/var/run/shm/$lbpplugindir/$serial.data";
		if (!-e $cache_file) {
			push @summaries, html_escape("$serial: $L{'VZLOGGER.HTTP_CACHE_MISSING'}");
			next;
		}

		$has_cache = 1;
		my ($last_update, $value_count) = cache_file_summary($cache_file, $serial);
		my $summary = "$serial: $L{'VZLOGGER.HTTP_CACHE_AVAILABLE'}";
		$summary .= " | $L{'VZLOGGER.HTTP_CACHE_LAST_UPDATE'}: $last_update" if ($last_update ne "");
		$summary .= " | $value_count $L{'VZLOGGER.HTTP_CACHE_VALUES'}" if ($value_count > 0);
		push @summaries, html_escape($summary);
	}

	$template->param("HTTP_CACHE_STATUS" => (@summaries ? join("<br>", @summaries) : html_escape($L{'VZLOGGER.HTTP_CACHE_NO_METERS'})));
	$template->param("HTTP_CACHE_URL" => "/plugins/$lbpplugindir/index.php");
	$template->param("HTTP_CACHE_DISABLED" => ($has_cache ? "" : "ui-disabled"));
}

sub cache_file_summary
{
	my ($cache_file, $serial) = @_;
	my $last_update = "";
	my $value_count = 0;

	if (open(my $fh, "<", $cache_file)) {
		while (my $line = <$fh>) {
			chomp($line);
			my ($line_serial, $key, $value) = split(/:/, $line, 3);
			next if (!defined($line_serial) || !defined($key) || $line_serial ne $serial);
			$last_update = $value if ($key eq "Last_Update" && defined($value));
			$value_count++ if ($key ne "Last_Update" && $key ne "Last_UpdateLoxEpoche");
		}
		close($fh);
	}

	return ($last_update, $value_count);
}

sub html_escape
{
	my ($value) = @_;
	$value = "" if (!defined($value));
	return CGI::escapeHTML($value);
}

sub service_status_class
{
	my ($state, $expected_active) = @_;
	return ($state eq "active") ? "service-status-ok" : "service-status-error" if ($expected_active);
	return "service-status-idle" if ($state eq "inactive");
	return "service-status-warning" if ($state eq "active" || $state eq "activating");
	return "service-status-error";
}

sub log_url
{
	my ($logfile) = @_;
	return "/admin/system/tools/logfile.cgi?logfile=$logfile&amp;header=html&amp;format=template";
}

sub log_redirect_url
{
	my ($logfile) = @_;
	return "/admin/system/tools/logfile.cgi?logfile=$logfile&header=html&format=template";
}

sub service_summary
{
	my ($service) = @_;
	my $state = service_state($service);
	my $pid = service_pid($service);
	my $installed = service_installed($service) ? "installed" : "not installed";
	return "$state | PID: " . ($pid || "-") . " | Service: $service | $installed";
}

sub service_state
{
	my ($service) = @_;
	return "unknown" if (!command_exists("systemctl"));
	my $state = `systemctl is-active $service 2>/dev/null`;
	chomp($state);
	return $state || "inactive";
}

sub service_pid
{
	my ($service) = @_;
	return "" if (!command_exists("systemctl"));
	my $pid = `systemctl show -p MainPID --value $service 2>/dev/null`;
	chomp($pid);
	return ($pid && $pid ne "0") ? $pid : "";
}

sub service_installed
{
	my ($service) = @_;
	return 1 if (-e "/etc/systemd/system/$service.service");
	return 1 if (-e "/lib/systemd/system/$service.service");
	return 0;
}

sub command_exists
{
	my ($command) = @_;
	my $path = `command -v $command 2>/dev/null`;
	chomp($path);
	return $path ? 1 : 0;
}

sub load_plugin_language
{
	my ($template) = @_;
	my $lang = "en";
	my $general_cfg = Config::Simple->new("$lbhomedir/config/system/general.cfg");
	$lang = $general_cfg->param("BASE.LANG") if ($general_cfg && $general_cfg->param("BASE.LANG"));
	$lang = $q->{lang} if ($q->{lang});
	$lang =~ tr/a-z//cd;
	$lang = substr($lang, 0, 2) || "en";

	my %phrases;
	Config::Simple->import_from("$lbptemplatedir/en/language.txt", \%phrases) if (-e "$lbptemplatedir/en/language.txt");
	Config::Simple->import_from("$lbptemplatedir/$lang/language.txt", \%phrases) if ($lang ne "en" && -e "$lbptemplatedir/$lang/language.txt");
	foreach my $name (keys %phrases) {
		$template->param("T::$name" => $phrases{$name});
	}
}

sub ensure_vzlogger_defaults
{
	$plugin_cfg->param("MAIN.READ", "0") if (!defined $plugin_cfg->param("MAIN.READ"));
	$plugin_cfg->param("MAIN.IMPLEMENTATION", infer_implementation_mode()) if (!$plugin_cfg->param("MAIN.IMPLEMENTATION"));
	$plugin_cfg->param("MAIN.CRON", "5") if (!$plugin_cfg->param("MAIN.CRON"));
	$plugin_cfg->param("MAIN.SENDUDP", "0") if (!defined $plugin_cfg->param("MAIN.SENDUDP"));
	$plugin_cfg->param("MAIN.UDPPORT", "7000") if (!$plugin_cfg->param("MAIN.UDPPORT"));
	$plugin_cfg->param("MAIN.MQTTTOPIC", "smartmeter") if (!$plugin_cfg->param("MAIN.MQTTTOPIC"));
	$plugin_cfg->param("VZLOGGER.LOCALPORT", "18080") if (!$plugin_cfg->param("VZLOGGER.LOCALPORT"));
	$plugin_cfg->param("VZLOGGER.UDPINTERVAL", "5") if (!defined $plugin_cfg->param("VZLOGGER.UDPINTERVAL"));
	$plugin_cfg->param("VZLOGGER.DEBUG", "0") if (!defined $plugin_cfg->param("VZLOGGER.DEBUG"));
	$plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG", "0") if (!defined $plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG"));
	$plugin_cfg->param("VZLOGGER.LOGLEVEL", "0") if (!defined $plugin_cfg->param("VZLOGGER.LOGLEVEL"));
	$plugin_cfg->save;
}

sub detect_heads
{
	my %heads = map { $_ => 1 } glob("/dev/serial/smartmeter/*");
	my %config;
	Config::Simple->import_from("$lbpconfigdir/smartmeter.cfg", \%config);
	while (my ($name, $value) = each %config) {
		$heads{$value} = 1 if ($name =~ /\.DEVICE\z/ && $value);
	}
	return sort keys %heads;
}

sub ensure_head_defaults
{
	my (@heads) = @_;
	foreach my $device (@heads) {
		my $serial = $device;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		next if ($plugin_cfg->param("$serial.DEVICE"));
		$plugin_cfg->param("$serial.NAME", "$serial");
		$plugin_cfg->param("$serial.SERIAL", "$serial");
		$plugin_cfg->param("$serial.DEVICE", "$device");
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
		$plugin_cfg->param("$serial.OBISCHANNELS", join(",", map { $_->{identifier} } default_obis_channels()));
		$plugin_cfg->param("$serial.OBISCUSTOM", "");
	}
	$plugin_cfg->save;
}

sub save_vzlogger_form
{
	my (@heads) = @_;
	$plugin_cfg->param("MAIN.IMPLEMENTATION", clean_config_value($q->{implementation}, qr/\A(?:legacy|vzlogger)\z/, implementation_mode()));
	$plugin_cfg->param("MAIN.READ", clean_config_value($q->{read}, qr/\A[01]\z/, "0"));
	# Disabled form controls are not submitted. Preserve their saved values while
	# meter reading is off instead of silently restoring defaults.
	$plugin_cfg->param("MAIN.CRON", clean_config_value($q->{cron}, qr/\A(M|1|3|5|10|15|30|60)\z/, $plugin_cfg->param("MAIN.CRON") || "5"));
	$plugin_cfg->param("MAIN.SENDUDP", clean_config_value($q->{sendudp}, qr/\A[01]\z/, $plugin_cfg->param("MAIN.SENDUDP") || "0"));
	$plugin_cfg->param("MAIN.UDPPORT", clean_config_value($q->{udpport}, qr/\A\d+\z/, $plugin_cfg->param("MAIN.UDPPORT") || "7000"));
	$plugin_cfg->param("MAIN.MQTTTOPIC", clean_config_value($q->{mqtttopic}, qr/\A[^#+]+\z/, $plugin_cfg->param("MAIN.MQTTTOPIC") || "smartmeter"));
	$plugin_cfg->param("VZLOGGER.LOCALPORT", clean_config_value($q->{vzlogger_localport}, qr/\A\d+\z/, $plugin_cfg->param("VZLOGGER.LOCALPORT") || "18080"));
	$plugin_cfg->param("VZLOGGER.UDPINTERVAL", clean_udp_interval($q->{vzlogger_udpinterval}, $plugin_cfg->param("VZLOGGER.UDPINTERVAL") || "5"));
	$plugin_cfg->param("VZLOGGER.DEBUG", clean_config_value($q->{vzlogger_debug}, qr/\A[01]\z/, $plugin_cfg->param("VZLOGGER.DEBUG") || "0"));
	$plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG", clean_config_value($q->{vzlogger_service_debug}, qr/\A[01]\z/, $plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG") || "0"));
	$plugin_cfg->param("VZLOGGER.LOGLEVEL", clean_log_level($q->{vzlogger_loglevel}, $plugin_cfg->param("VZLOGGER.LOGLEVEL") || "0"));

	foreach my $device (@heads) {
		my $serial = $device;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		$plugin_cfg->param("$serial.NAME", clean_config_value($q->{"$serial\_name"}, qr/\A[A-Za-z0-9_-]+\z/, $serial));
		$plugin_cfg->param("$serial.METER", clean_config_value($q->{"$serial\_meter"}, qr/\A[A-Za-z0-9_.:-]+\z/, "0"));
		$plugin_cfg->param("$serial.PROTOCOL", clean_config_value($q->{"$serial\_protocol"}, qr/\A[A-Za-z0-9_.:-]*\z/, ""));
		$plugin_cfg->param("$serial.STARTBAUDRATE", clean_config_value($q->{"$serial\_startbaudrate"}, qr/\A\d*\z/, ""));
		$plugin_cfg->param("$serial.BAUDRATE", clean_config_value($q->{"$serial\_baudrate"}, qr/\A\d*\z/, ""));
		$plugin_cfg->param("$serial.TIMEOUT", clean_config_value($q->{"$serial\_timeout"}, qr/\A\d*\z/, ""));
		$plugin_cfg->param("$serial.DATABITS", clean_config_value($q->{"$serial\_databits"}, qr/\A\d*\z/, ""));
		$plugin_cfg->param("$serial.STOPBITS", clean_config_value($q->{"$serial\_stopbits"}, qr/\A\d*\z/, ""));
		$plugin_cfg->param("$serial.PARITY", clean_config_value($q->{"$serial\_parity"}, qr/\A[A-Za-z0-9_.:-]*\z/, ""));
		my @selected_obis = grep { defined($_) && $_ =~ /\A\d-\d:\d+\.\d+\.\d+\z/ } $cgi->multi_param("$serial\_obis");
		$plugin_cfg->param("$serial.OBISCHANNELS", join(",", @selected_obis));
		$plugin_cfg->param("$serial.OBISCUSTOM", clean_multiline_obis($q->{"$serial\_obis_custom"}));
	}
	$plugin_cfg->save;
}

sub apply_selected_implementation
{
	if (implementation_mode() eq "legacy") {
		my $output = run_control("disable-vzlogger");
		$output .= apply_legacy_cron();
		return $output;
	}

	remove_legacy_cronjobs();
	return run_control("apply");
}

sub implementation_mode
{
	my $mode = $plugin_cfg->param("MAIN.IMPLEMENTATION") || "";
	return $mode if ($mode =~ /\A(?:legacy|vzlogger)\z/);
	return infer_implementation_mode();
}

sub infer_implementation_mode
{
	return (($plugin_cfg->param("MAIN.READ") || "0") eq "1") ? "legacy" : "vzlogger";
}

sub apply_legacy_cron
{
	remove_legacy_cronjobs();
	return "Legacy meter polling is disabled. No cronjob restored.\n" if (($plugin_cfg->param("MAIN.READ") || "0") ne "1");

	my $cron = $plugin_cfg->param("MAIN.CRON") || "5";
	my %cron_map = (
		M  => ["cron.reboot", "reboot_cron_runner.sh", "reboot"],
		1  => ["cron.01min", "fetch.pl", "1 minute"],
		3  => ["cron.03min", "fetch.pl", "3 minutes"],
		5  => ["cron.05min", "fetch.pl", "5 minutes"],
		10 => ["cron.10min", "fetch.pl", "10 minutes"],
		15 => ["cron.15min", "fetch.pl", "15 minutes"],
		30 => ["cron.30min", "fetch.pl", "30 minutes"],
		60 => ["cron.hourly", "fetch.pl", "hourly"],
	);
	return "Unknown cron interval '$cron'. No legacy cronjob restored.\n" if (!$cron_map{$cron});

	my ($cronfolder, $scriptname, $label) = @{$cron_map{$cron}};
	create_legacy_cronjob($cronfolder, $scriptname);
	return "Restored legacy meter polling cronjob: $label\n";
}

sub remove_legacy_cronjobs
{
	foreach my $cronfolder ("cron.01min", "cron.03min", "cron.05min", "cron.10min", "cron.15min", "cron.30min", "cron.hourly", "cron.reboot") {
		unlink("$lbhomedir/system/cron/$cronfolder/$lbpplugindir");
	}
}

sub create_legacy_cronjob
{
	my ($cronfolder, $scriptname) = @_;
	my $source = "$lbpbindir/$scriptname";
	my $target = "$lbhomedir/system/cron/$cronfolder/$lbpplugindir";
	unlink($target);
	symlink($source, $target);
}

sub build_head_rows
{
	my (@heads) = @_;
	my @rows;
	foreach my $device (@heads) {
		my $serial = $device;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		my %enabled_obis = enabled_obis_channels($serial);
		push @rows, {
			NAME => $plugin_cfg->param("$serial.NAME") || $serial,
			SERIAL => $serial,
			DEVICE => $plugin_cfg->param("$serial.DEVICE") || $device,
			METER => $plugin_cfg->param("$serial.METER") || "0",
			PROTOCOL => $plugin_cfg->param("$serial.PROTOCOL") || "",
			STARTBAUDRATE => $plugin_cfg->param("$serial.STARTBAUDRATE") || "",
			BAUDRATE => $plugin_cfg->param("$serial.BAUDRATE") || "",
			TIMEOUT => $plugin_cfg->param("$serial.TIMEOUT") || "",
			DATABITS => $plugin_cfg->param("$serial.DATABITS") || "",
			STOPBITS => $plugin_cfg->param("$serial.STOPBITS") || "",
			PARITY => $plugin_cfg->param("$serial.PARITY") || "",
			OBIS_CUSTOM => $plugin_cfg->param("$serial.OBISCUSTOM") || "",
			OBIS_CHANNELS => [
				map {
					{
						FIELD_NAME => "$serial\_obis",
						IDENTIFIER => $_->{identifier},
						NAME => $_->{name},
						CHECKED => $enabled_obis{$_->{identifier}} ? "checked" : "",
					}
				} default_obis_channels()
			],
		};
	}
	return @rows;
}

sub enabled_obis_channels
{
	my ($serial) = @_;
	return map { $_->{identifier} => 1 } default_obis_channels() if (!defined($plugin_cfg->param("$serial.OBISCHANNELS")));
	my %enabled = map { $_ => 1 } config_list_values("$serial.OBISCHANNELS");
	return %enabled;
}

sub config_list_values
{
	my ($key) = @_;
	my $value = $plugin_cfg->param($key);
	return () if (!defined($value));
	return grep { defined($_) && $_ ne "" } @{$value} if (ref($value) eq "ARRAY");
	return grep { $_ ne "" } split(/\s*,\s*/, $value);
}

sub default_obis_channels
{
	return (
		{ identifier => "1-0:1.8.0", name => "Consumption_Total_OBIS_1.8.0" },
		{ identifier => "1-0:1.8.1", name => "Consumption_Tarif1_OBIS_1.8.1" },
		{ identifier => "1-0:1.8.2", name => "Consumption_Tarif2_OBIS_1.8.2" },
		{ identifier => "1-0:1.7.0", name => "Consumption_Power_OBIS_1.7.0" },
		{ identifier => "1-0:21.7.0", name => "Consumption_Power_L1_OBIS_21.7.0" },
		{ identifier => "1-0:41.7.0", name => "Consumption_Power_L2_OBIS_41.7.0" },
		{ identifier => "1-0:61.7.0", name => "Consumption_Power_L3_OBIS_61.7.0" },
		{ identifier => "1-0:2.8.0", name => "Delivery_Total_OBIS_2.8.0" },
		{ identifier => "1-0:2.8.1", name => "Delivery_Tarif1_OBIS_2.8.1" },
		{ identifier => "1-0:2.8.2", name => "Delivery_Tarif2_OBIS_2.8.2" },
		{ identifier => "1-0:2.7.0", name => "Delivery_Power_OBIS_2.7.0" },
		{ identifier => "1-0:15.7.0", name => "Total_Power_OBIS_15.7.0" },
		{ identifier => "1-0:16.7.0", name => "Total_Power_OBIS_16.7.0" },
		{ identifier => "1-0:96.50.1", name => "Manufacturer_ID_OBIS_96.50.1" },
		{ identifier => "1-0:96.1.0", name => "Server_ID_OBIS_96.1.0" },
	);
}

sub clean_multiline_obis
{
	my ($value) = @_;
	return "" if (!defined($value));
	my @clean;
	foreach my $line (split(/\\n|\r?\n|,|;/, $value)) {
		my $identifier = normalize_obis_identifier($line);
		push @clean, $identifier if ($identifier);
	}
	return join("\n", @clean);
}

sub normalize_obis_identifier
{
	my ($value) = @_;
	return "" if (!defined($value));
	$value =~ s/^\s+|\s+$//g;
	$value =~ s/\*\d+\z//;
	return $value if ($value =~ /\A\d+-\d+:\d+\.\d+\.\d+\z/);
	return "";
}

sub run_control
{
	my ($action) = @_;
	my $script = "$lbpbindir/vzlogger_control.pl";
	return "Control script not found: $script" if (!-e $script);
	my $output = `$^X "$script" "$action" 2>&1`;
	$output ||= "No output.";
	write_control_log($action, $output);
	return $output;
}

sub write_control_log
{
	my ($action, $output) = @_;
	my $plugin_log_dir = "$lbhomedir/log/plugins/$lbpplugindir";
	my $control_log = "$plugin_log_dir/vzlogger_control.log";
	make_path($plugin_log_dir) if (!-d $plugin_log_dir);
	if (-e $control_log && -s $control_log >= 512 * 1024) {
		unlink("$control_log.1") if (-e "$control_log.1");
		rename($control_log, "$control_log.1");
	}
	open(my $fh, ">>", $control_log) or return;
	print $fh timestamp() . " web-action=$action\n";
	print $fh $output;
	print $fh "\n" if ($output !~ /\n\z/);
	close($fh);
}

sub timestamp
{
	my ($sec, $min, $hour, $mday, $mon, $year) = localtime();
	return sprintf("%04d%02d%02d-%02d%02d%02d", $year + 1900, $mon + 1, $mday, $hour, $min, $sec);
}

sub clean_config_value
{
	my ($value, $pattern, $default) = @_;
	return $default if (!defined($value));
	return $value if ($value =~ $pattern);
	return $default;
}

sub clean_log_level
{
	my ($value, $default) = @_;
	return $value if (defined($value) && $value =~ /\A(?:0|1|3|5|10|15)\z/);
	return $default;
}

sub clean_udp_interval
{
	my ($value, $default) = @_;
	return $value if (defined($value) && $value =~ /\A(?:5|10|30|60|180|300|600|900|1800|3600)\z/);
	return $default;
}

sub udp_interval_options
{
	my ($selected) = @_;
	my @options = (
		[ "5", $L{'VZLOGGER.INTERVAL_MINIMAL'} || "Minimal" ],
		[ "10", $L{'VZLOGGER.INTERVAL_10_SECONDS'} || "Every 10 seconds" ],
		[ "30", $L{'VZLOGGER.INTERVAL_30_SECONDS'} || "Every 30 seconds" ],
		[ "60", $L{'VZLOGGER.INTERVAL_1_MINUTE'} || "Every 1 minute" ],
		[ "180", $L{'VZLOGGER.INTERVAL_3_MINUTES'} || "Every 3 minutes" ],
		[ "300", $L{'VZLOGGER.INTERVAL_5_MINUTES'} || "Every 5 minutes" ],
		[ "600", $L{'VZLOGGER.INTERVAL_10_MINUTES'} || "Every 10 minutes" ],
		[ "900", $L{'VZLOGGER.INTERVAL_15_MINUTES'} || "Every 15 minutes" ],
		[ "1800", $L{'VZLOGGER.INTERVAL_30_MINUTES'} || "Every 30 minutes" ],
		[ "3600", $L{'VZLOGGER.INTERVAL_60_MINUTES'} || "Every 60 minutes" ],
	);
	return [ map {
		{
			VALUE => $_->[0],
			LABEL => $_->[1],
			SELECTED => ($_->[0] eq $selected ? "selected" : ""),
		}
	} @options ];
}

sub form_log
{
	print $cgi->redirect(-url => "./logfiles.cgi");
	exit;
}


##########################################################################
# Print Form
##########################################################################

sub form_print
{
	
	# Template
	my $title = $L{'COMMON.LABEL_PLUGINTITLE'} || "Smartmeter v2";
	LoxBerry::Web::lbheader("$title V$version", "https://www.loxwiki.eu/x/mA-L", "");
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
	return();
}	

