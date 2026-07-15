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
use JSON::PP;
use LoxBerry::System;
#use LoxBerry::Web;
use LoxBerry::JSON; # Available with LoxBerry 2.0
use LoxBerry::Log;
use POSIX ":sys_wait_h";
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
		$control_action = "read-obis" if ($action eq "read-obis");
		my $output = "";
		if ($action eq "read-obis") {
			$output = read_obis_channels($q->{obis_serial}, @heads);
		} else {
			$output = ($control_action eq "apply") ? apply_selected_implementation() : run_control($control_action);
		}
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
	my $local_enabled = clean_boolean($plugin_cfg->param("VZLOGGER.LOCALENABLED"), 1);
	my $local_port = $plugin_cfg->param("VZLOGGER.LOCALPORT") || 18080;
	my $local_index = clean_boolean($plugin_cfg->param("VZLOGGER.LOCALINDEX"), 1);
	my $local_timeout = clean_number($plugin_cfg->param("VZLOGGER.LOCALTIMEOUT"), 30);
	my $local_buffer = clean_integer($plugin_cfg->param("VZLOGGER.LOCALBUFFER"), -1);
	my $retry = clean_number($plugin_cfg->param("VZLOGGER.RETRY"), 30);
	my $mqtttopic = $plugin_cfg->param("MAIN.MQTTTOPIC") || "smartmeter";
	my $loxberry_mqtt = read_loxberry_mqtt_settings();
	my $effective_mqtt = effective_mqtt_settings($loxberry_mqtt);
	my $mqtt_password_status = $plugin_cfg->param("VZLOGGER.MQTTPASS") ?
		($L{'VZLOGGER.MQTT_PASSWORD_CUSTOM_STATUS'} || "Custom password stored") :
		$loxberry_mqtt->{pass} ?
		($L{'VZLOGGER.MQTT_PASSWORD_LOXBERRY_STATUS'} || "LoxBerry password is used") :
		($L{'VZLOGGER.MQTT_PASSWORD_NONE_STATUS'} || "No password configured");

	$template->param("FORM_VZLOGGER", 1);
	$template->param("IMPLEMENTATION" => implementation_mode());
	$template->param("READ" => $plugin_cfg->param("MAIN.READ") || 0);
	$template->param("CRON" => $plugin_cfg->param("MAIN.CRON") || 5);
	$template->param("SENDUDP" => $plugin_cfg->param("MAIN.SENDUDP") || 0);
	$template->param("UDPPORT" => $plugin_cfg->param("MAIN.UDPPORT") || 7000);
	$template->param("MQTTTOPIC" => $mqtttopic);
	$template->param("VZLOGGER_LOCALENABLED" => $local_enabled);
	$template->param("VZLOGGER_LOCALPORT" => $local_port);
	$template->param("VZLOGGER_LOCALINDEX" => $local_index);
	$template->param("VZLOGGER_LOCALTIMEOUT" => $local_timeout);
	$template->param("VZLOGGER_LOCALBUFFER" => $local_buffer);
	$template->param("VZLOGGER_RETRY" => $retry);
	my $udp_interval = clean_udp_interval($plugin_cfg->param("VZLOGGER.UDPINTERVAL"), "5");
	$template->param("VZLOGGER_UDPINTERVAL" => $udp_interval);
	$template->param("VZLOGGER_UDPINTERVAL_OPTIONS" => udp_interval_options($udp_interval));
	$template->param("VZLOGGER_DEBUG" => $plugin_cfg->param("VZLOGGER.DEBUG") || 0);
	$template->param("VZLOGGER_SERVICE_DEBUG" => $plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG") || 0);
	$template->param("VZLOGGER_LOGLEVEL" => clean_log_level($plugin_cfg->param("VZLOGGER.LOGLEVEL"), "0"));
	$template->param("VZLOGGER_MQTTENABLED" => clean_boolean($plugin_cfg->param("VZLOGGER.MQTTENABLED"), 1));
	$template->param("VZLOGGER_MQTTHOST" => $effective_mqtt->{host});
	$template->param("VZLOGGER_MQTTPORT" => $effective_mqtt->{port});
	$template->param("VZLOGGER_MQTTCAFILE" => $plugin_cfg->param("VZLOGGER.MQTTCAFILE") || "");
	$template->param("VZLOGGER_MQTTCAPATH" => $plugin_cfg->param("VZLOGGER.MQTTCAPATH") || "");
	$template->param("VZLOGGER_MQTTCERTFILE" => $plugin_cfg->param("VZLOGGER.MQTTCERTFILE") || "");
	$template->param("VZLOGGER_MQTTKEYFILE" => $plugin_cfg->param("VZLOGGER.MQTTKEYFILE") || "");
	$template->param("VZLOGGER_MQTTKEEPALIVE" => clean_number($plugin_cfg->param("VZLOGGER.MQTTKEEPALIVE"), 30));
	$template->param("VZLOGGER_MQTTID" => $plugin_cfg->param("VZLOGGER.MQTTID") || "");
	$template->param("VZLOGGER_MQTTUSER" => $effective_mqtt->{user});
	$template->param("VZLOGGER_MQTTPASS_STATUS" => $mqtt_password_status);
	$template->param("VZLOGGER_MQTTRETAIN" => clean_boolean($plugin_cfg->param("VZLOGGER.MQTTRETAIN"), 1));
	$template->param("VZLOGGER_MQTTRAWANDAGG" => clean_boolean($plugin_cfg->param("VZLOGGER.MQTTRAWANDAGG"), 0));
	$template->param("VZLOGGER_MQTTQOS" => clean_qos($plugin_cfg->param("VZLOGGER.MQTTQOS"), 0));
	$template->param("VZLOGGER_MQTTTIMESTAMP" => clean_boolean($plugin_cfg->param("VZLOGGER.MQTTTIMESTAMP"), 1));
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
	my $mqtt_enabled = clean_boolean($plugin_cfg->param("VZLOGGER.MQTTENABLED"), 1);
	my $bridge_available = $vzlogger_expected_active && $mqtt_enabled;
	my $bridge_expected_active = $bridge_available && (($plugin_cfg->param("MAIN.READ") || "0") eq "1");
	my $vzlogger_state = service_state("vzlogger");
	my $bridge_state = service_state("smartmeter-v2-vzlogger-bridge");
	my $bridge_unavailable = !$vzlogger_expected_active ?
		($L{'VZLOGGER.BRIDGE_UNAVAILABLE_VZLOGGER'} || "Unavailable: vzLogger is disabled") :
		!$mqtt_enabled ?
		($L{'VZLOGGER.BRIDGE_UNAVAILABLE_MQTT'} || "Unavailable: MQTT is disabled") : "";

	$template->param("VZLOGGER_SERVICE_CONTROL_DISABLED" => ($vzlogger_expected_active ? "" : "disabled"));
	$template->param("BRIDGE_SERVICE_CONTROL_DISABLED" => ($bridge_expected_active ? "" : "disabled"));
	$template->param("BRIDGE_ACTIVATION_DISABLED" => ($bridge_available ? "" : "disabled"));
	$template->param("VZLOGGER_SERVICE_STATUS" => service_summary("vzlogger"));
	$template->param("BRIDGE_SERVICE_STATUS" => ($bridge_unavailable || service_summary("smartmeter-v2-vzlogger-bridge")));
	$template->param("BRIDGE_AVAILABILITY_HELP" => ($bridge_unavailable || ($L{'VZLOGGER.BRIDGE_SERVICE_CONTROL_HELP'} || "Manual control of the SmartMeter bridge.")));
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
	$plugin_cfg->param("VZLOGGER.RETRY", "30") if (!defined $plugin_cfg->param("VZLOGGER.RETRY"));
	$plugin_cfg->param("VZLOGGER.LOCALENABLED", "1") if (!defined $plugin_cfg->param("VZLOGGER.LOCALENABLED"));
	$plugin_cfg->param("VZLOGGER.LOCALPORT", "18080") if (!$plugin_cfg->param("VZLOGGER.LOCALPORT"));
	$plugin_cfg->param("VZLOGGER.LOCALINDEX", "1") if (!defined $plugin_cfg->param("VZLOGGER.LOCALINDEX"));
	$plugin_cfg->param("VZLOGGER.LOCALTIMEOUT", "30") if (!defined $plugin_cfg->param("VZLOGGER.LOCALTIMEOUT"));
	$plugin_cfg->param("VZLOGGER.LOCALBUFFER", "-1") if (!defined $plugin_cfg->param("VZLOGGER.LOCALBUFFER"));
	$plugin_cfg->param("VZLOGGER.UDPINTERVAL", "5") if (!defined $plugin_cfg->param("VZLOGGER.UDPINTERVAL"));
	$plugin_cfg->param("VZLOGGER.DEBUG", "0") if (!defined $plugin_cfg->param("VZLOGGER.DEBUG"));
	$plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG", "0") if (!defined $plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG"));
	$plugin_cfg->param("VZLOGGER.LOGLEVEL", "0") if (!defined $plugin_cfg->param("VZLOGGER.LOGLEVEL"));
	$plugin_cfg->param("VZLOGGER.MQTTENABLED", "1") if (!defined $plugin_cfg->param("VZLOGGER.MQTTENABLED"));
	$plugin_cfg->param("VZLOGGER.MQTTHOST", "") if (!defined $plugin_cfg->param("VZLOGGER.MQTTHOST"));
	$plugin_cfg->param("VZLOGGER.MQTTPORT", "") if (!defined $plugin_cfg->param("VZLOGGER.MQTTPORT"));
	$plugin_cfg->param("VZLOGGER.MQTTCAFILE", "") if (!defined $plugin_cfg->param("VZLOGGER.MQTTCAFILE"));
	$plugin_cfg->param("VZLOGGER.MQTTCAPATH", "") if (!defined $plugin_cfg->param("VZLOGGER.MQTTCAPATH"));
	$plugin_cfg->param("VZLOGGER.MQTTCERTFILE", "") if (!defined $plugin_cfg->param("VZLOGGER.MQTTCERTFILE"));
	$plugin_cfg->param("VZLOGGER.MQTTKEYFILE", "") if (!defined $plugin_cfg->param("VZLOGGER.MQTTKEYFILE"));
	$plugin_cfg->param("VZLOGGER.MQTTKEYPASS", "") if (!defined $plugin_cfg->param("VZLOGGER.MQTTKEYPASS"));
	$plugin_cfg->param("VZLOGGER.MQTTKEEPALIVE", "30") if (!defined $plugin_cfg->param("VZLOGGER.MQTTKEEPALIVE"));
	$plugin_cfg->param("VZLOGGER.MQTTID", "") if (!defined $plugin_cfg->param("VZLOGGER.MQTTID"));
	$plugin_cfg->param("VZLOGGER.MQTTUSER", "") if (!defined $plugin_cfg->param("VZLOGGER.MQTTUSER"));
	$plugin_cfg->param("VZLOGGER.MQTTPASS", "") if (!defined $plugin_cfg->param("VZLOGGER.MQTTPASS"));
	$plugin_cfg->param("VZLOGGER.MQTTRETAIN", "1") if (!defined $plugin_cfg->param("VZLOGGER.MQTTRETAIN"));
	$plugin_cfg->param("VZLOGGER.MQTTRAWANDAGG", "0") if (!defined $plugin_cfg->param("VZLOGGER.MQTTRAWANDAGG"));
	$plugin_cfg->param("VZLOGGER.MQTTQOS", "0") if (!defined $plugin_cfg->param("VZLOGGER.MQTTQOS"));
	$plugin_cfg->param("VZLOGGER.MQTTTIMESTAMP", "1") if (!defined $plugin_cfg->param("VZLOGGER.MQTTTIMESTAMP"));
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
		$plugin_cfg->param("$serial.OBISCHANNELS", "");
		$plugin_cfg->param("$serial.OBISCUSTOM", "");
	}
	$plugin_cfg->save;
}

sub save_vzlogger_form
{
	my (@heads) = @_;
	$plugin_cfg->param("MAIN.IMPLEMENTATION", clean_config_value($q->{implementation}, qr/\A(?:legacy|vzlogger)\z/, implementation_mode()));
	$plugin_cfg->param("MAIN.READ", clean_config_value($q->{read}, qr/\A[01]\z/, defined($plugin_cfg->param("MAIN.READ")) ? $plugin_cfg->param("MAIN.READ") : "0"));
	# Disabled form controls are not submitted. Preserve their saved values while
	# meter reading is off instead of silently restoring defaults.
	$plugin_cfg->param("MAIN.CRON", clean_config_value($q->{cron}, qr/\A(M|1|3|5|10|15|30|60)\z/, $plugin_cfg->param("MAIN.CRON") || "5"));
	$plugin_cfg->param("MAIN.SENDUDP", clean_config_value($q->{sendudp}, qr/\A[01]\z/, $plugin_cfg->param("MAIN.SENDUDP") || "0"));
	$plugin_cfg->param("MAIN.UDPPORT", clean_config_value($q->{udpport}, qr/\A\d+\z/, $plugin_cfg->param("MAIN.UDPPORT") || "7000"));
	$plugin_cfg->param("MAIN.MQTTTOPIC", clean_config_value($q->{mqtttopic}, qr/\A[^#+]+\z/, $plugin_cfg->param("MAIN.MQTTTOPIC") || "smartmeter"));
	$plugin_cfg->param("VZLOGGER.RETRY", clean_config_value($q->{vzlogger_retry}, qr/\A\d+\z/, defined($plugin_cfg->param("VZLOGGER.RETRY")) ? $plugin_cfg->param("VZLOGGER.RETRY") : "30"));
	$plugin_cfg->param("VZLOGGER.LOCALENABLED", clean_config_value($q->{vzlogger_localenabled}, qr/\A[01]\z/, defined($plugin_cfg->param("VZLOGGER.LOCALENABLED")) ? $plugin_cfg->param("VZLOGGER.LOCALENABLED") : "1"));
	$plugin_cfg->param("VZLOGGER.LOCALPORT", clean_config_value($q->{vzlogger_localport}, qr/\A\d+\z/, $plugin_cfg->param("VZLOGGER.LOCALPORT") || "18080"));
	$plugin_cfg->param("VZLOGGER.LOCALINDEX", clean_config_value($q->{vzlogger_localindex}, qr/\A[01]\z/, defined($plugin_cfg->param("VZLOGGER.LOCALINDEX")) ? $plugin_cfg->param("VZLOGGER.LOCALINDEX") : "1"));
	$plugin_cfg->param("VZLOGGER.LOCALTIMEOUT", clean_config_value($q->{vzlogger_localtimeout}, qr/\A\d+\z/, defined($plugin_cfg->param("VZLOGGER.LOCALTIMEOUT")) ? $plugin_cfg->param("VZLOGGER.LOCALTIMEOUT") : "30"));
	$plugin_cfg->param("VZLOGGER.LOCALBUFFER", clean_config_value($q->{vzlogger_localbuffer}, qr/\A-?\d+\z/, defined($plugin_cfg->param("VZLOGGER.LOCALBUFFER")) ? $plugin_cfg->param("VZLOGGER.LOCALBUFFER") : "-1"));
	$plugin_cfg->param("VZLOGGER.UDPINTERVAL", clean_udp_interval($q->{vzlogger_udpinterval}, $plugin_cfg->param("VZLOGGER.UDPINTERVAL") || "5"));
	$plugin_cfg->param("VZLOGGER.DEBUG", clean_config_value($q->{vzlogger_debug}, qr/\A[01]\z/, $plugin_cfg->param("VZLOGGER.DEBUG") || "0"));
	$plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG", clean_config_value($q->{vzlogger_service_debug}, qr/\A[01]\z/, $plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG") || "0"));
	$plugin_cfg->param("VZLOGGER.LOGLEVEL", clean_log_level($q->{vzlogger_loglevel}, $plugin_cfg->param("VZLOGGER.LOGLEVEL") || "0"));
	$plugin_cfg->param("VZLOGGER.MQTTENABLED", clean_config_value($q->{vzlogger_mqttenabled}, qr/\A[01]\z/, defined($plugin_cfg->param("VZLOGGER.MQTTENABLED")) ? $plugin_cfg->param("VZLOGGER.MQTTENABLED") : "1"));
	my $loxberry_mqtt = read_loxberry_mqtt_settings();
	save_mqtt_override("MQTTHOST", $q->{vzlogger_mqtthost}, qr/\A[^\r\n]*\z/, $loxberry_mqtt->{host});
	save_mqtt_override("MQTTPORT", $q->{vzlogger_mqttport}, qr/\A\d*\z/, $loxberry_mqtt->{port});
	$plugin_cfg->param("VZLOGGER.MQTTCAFILE", clean_config_value($q->{vzlogger_mqttcafile}, qr/\A[^\r\n]*\z/, $plugin_cfg->param("VZLOGGER.MQTTCAFILE") || ""));
	$plugin_cfg->param("VZLOGGER.MQTTCAPATH", clean_config_value($q->{vzlogger_mqttcapath}, qr/\A[^\r\n]*\z/, $plugin_cfg->param("VZLOGGER.MQTTCAPATH") || ""));
	$plugin_cfg->param("VZLOGGER.MQTTCERTFILE", clean_config_value($q->{vzlogger_mqttcertfile}, qr/\A[^\r\n]*\z/, $plugin_cfg->param("VZLOGGER.MQTTCERTFILE") || ""));
	$plugin_cfg->param("VZLOGGER.MQTTKEYFILE", clean_config_value($q->{vzlogger_mqttkeyfile}, qr/\A[^\r\n]*\z/, $plugin_cfg->param("VZLOGGER.MQTTKEYFILE") || ""));
	if (($q->{vzlogger_mqttkeypass_reset} || "0") eq "1") {
		$plugin_cfg->param("VZLOGGER.MQTTKEYPASS", "");
	} elsif (defined($q->{vzlogger_mqttkeypass}) && $q->{vzlogger_mqttkeypass} ne "") {
		$plugin_cfg->param("VZLOGGER.MQTTKEYPASS", clean_config_value($q->{vzlogger_mqttkeypass}, qr/\A[^\r\n]+\z/, $plugin_cfg->param("VZLOGGER.MQTTKEYPASS") || ""));
	}
	$plugin_cfg->param("VZLOGGER.MQTTKEEPALIVE", clean_config_value($q->{vzlogger_mqttkeepalive}, qr/\A\d+\z/, $plugin_cfg->param("VZLOGGER.MQTTKEEPALIVE") || "30"));
	$plugin_cfg->param("VZLOGGER.MQTTID", clean_config_value($q->{vzlogger_mqttid}, qr/\A[^\r\n]*\z/, $plugin_cfg->param("VZLOGGER.MQTTID") || ""));
	save_mqtt_override("MQTTUSER", $q->{vzlogger_mqttuser}, qr/\A[^\r\n]*\z/, $loxberry_mqtt->{user});
	if (($q->{vzlogger_mqttpass_reset} || "0") eq "1") {
		$plugin_cfg->param("VZLOGGER.MQTTPASS", "");
	} elsif (defined($q->{vzlogger_mqttpass}) && $q->{vzlogger_mqttpass} ne "") {
		$plugin_cfg->param("VZLOGGER.MQTTPASS", clean_config_value($q->{vzlogger_mqttpass}, qr/\A[^\r\n]+\z/, $plugin_cfg->param("VZLOGGER.MQTTPASS") || ""));
	}
	$plugin_cfg->param("VZLOGGER.MQTTRETAIN", clean_config_value($q->{vzlogger_mqttretain}, qr/\A[01]\z/, defined($plugin_cfg->param("VZLOGGER.MQTTRETAIN")) ? $plugin_cfg->param("VZLOGGER.MQTTRETAIN") : "1"));
	$plugin_cfg->param("VZLOGGER.MQTTRAWANDAGG", clean_config_value($q->{vzlogger_mqttrawandagg}, qr/\A[01]\z/, defined($plugin_cfg->param("VZLOGGER.MQTTRAWANDAGG")) ? $plugin_cfg->param("VZLOGGER.MQTTRAWANDAGG") : "0"));
	$plugin_cfg->param("VZLOGGER.MQTTQOS", clean_config_value($q->{vzlogger_mqttqos}, qr/\A[01]\z/, $plugin_cfg->param("VZLOGGER.MQTTQOS") || "0"));
	$plugin_cfg->param("VZLOGGER.MQTTTIMESTAMP", clean_config_value($q->{vzlogger_mqtttimestamp}, qr/\A[01]\z/, defined($plugin_cfg->param("VZLOGGER.MQTTTIMESTAMP")) ? $plugin_cfg->param("VZLOGGER.MQTTTIMESTAMP") : "1"));

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
		my @selected_obis = grep { normalize_obis_identifier($_) ne "" } $cgi->multi_param("$serial\_obis");
		@selected_obis = map { normalize_obis_identifier($_) } @selected_obis;
		$plugin_cfg->param("$serial.OBISCHANNELS", join(",", @selected_obis));
		$plugin_cfg->param("$serial.OBISCUSTOM", clean_multiline_obis($q->{"$serial\_obis_custom"}));
	}
	$plugin_cfg->save;
}

sub read_obis_channels
{
	my ($target_serial, @heads) = @_;
	$target_serial = clean_config_value($target_serial, qr/\A[A-Za-z0-9_.:-]+\z/, "");
	return "No I/R head selected for OBIS channel discovery.\n" if (!$target_serial);

	my %known_heads = map {
		my $serial = $_;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		$serial => 1;
	} @heads;
	return "Unknown I/R head '$target_serial'.\n" if (!$known_heads{$target_serial});

	my $was_active = service_state("vzlogger") eq "active";
	my $output = "Read OBIS channels for $target_serial.\n";
	if ($was_active) {
		$output .= "Stopping vzlogger service before OBIS discovery.\n";
		run_control("stop-vzlogger");
	}

	if (!command_exists("vzlogger")) {
		$output .= "vzlogger binary not found. Install vzlogger before reading OBIS channels.\n";
	} else {
		my ($test_config, $test_log, $config_error) = write_vzlogger_obis_test_config($target_serial);
		if ($config_error) {
			$output .= $config_error;
		} else {
			unlink($test_log) if (-e $test_log);
			my $vzlogger_output = run_vzlogger_obis_test($test_config);
			write_control_log("read-obis-vzlogger", "config=$test_config\nlog=$test_log\n$vzlogger_output");
			$output .= "vzLogger OBIS discovery completed. Details were written to the control log.\n";
			$output .= "Discovery log: $test_log\n";

			my @channels = channels_from_vzlogger_log($test_log);
			if (@channels) {
				write_obis_discovery_cache($target_serial, @channels);
				$output .= "Detected " . scalar(@channels) . " OBIS channel(s) for $target_serial.\n";
				$output .= join("\n", map { " - " . $_->{identifier} . " (" . $_->{name} . ")" } @channels) . "\n";
			} else {
				$output .= "No OBIS channels detected for $target_serial. Check the vzLogger discovery log and meter settings.\n";
			}
		}
	}

	if ($was_active) {
		$output .= "Restarting vzlogger service after OBIS channel discovery.\n";
		run_control("start-vzlogger");
	}

	return $output;
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

sub write_vzlogger_obis_test_config
{
	my ($serial) = @_;
	my $meter = $plugin_cfg->param("$serial.METER") || "0";
	return ("", "", "No meter preset is configured for $serial.\n") if ($meter eq "0");

	my $protocol_name = $meter eq "manual" ? ($plugin_cfg->param("$serial.PROTOCOL") || "") : $meter;
	my $protocol = protocol_for_meter($protocol_name);
	return ("", "", "Meter preset '$protocol_name' cannot be mapped to a vzLogger protocol.\n") if (!$protocol);

	my $device = $plugin_cfg->param("$serial.DEVICE") || "/dev/serial/smartmeter/$serial";
	return ("", "", "No serial device is configured for $serial.\n") if (!$device);

	my $meter_config = {
		enabled => JSON::PP::true,
		allowskip => JSON::PP::true,
		aggtime => -1,
		protocol => $protocol,
		device => $device,
		channels => [],
	};

	if ($protocol eq "sml") {
		$meter_config->{interval} = -1;
	} else {
		$meter_config->{interval} = -1;
		$meter_config->{read_timeout} = clean_number($plugin_cfg->param("$serial.TIMEOUT"), 10);
		$meter_config->{baudrate} = clean_number($plugin_cfg->param("$serial.BAUDRATE"), default_baudrate($protocol_name));
		$meter_config->{baudrate_read} = clean_number($plugin_cfg->param("$serial.STARTBAUDRATE"), 300);
		$meter_config->{parity} = serial_mode(
			$plugin_cfg->param("$serial.DATABITS"),
			$plugin_cfg->param("$serial.PARITY"),
			$plugin_cfg->param("$serial.STOPBITS")
		);
	}

	my $safe_serial = safe_filename($serial);
	my $log_file = "$lbhomedir/log/plugins/$lbpplugindir/vzLogger_$safe_serial.log";
	my $config_file = "$lbpconfigdir/vzLogger_IrTest_$safe_serial.conf";
	my $local_port = clean_number($plugin_cfg->param("VZLOGGER.LOCALPORT"), 18080);
	my $config = {
		verbosity => 15,
		log => $log_file,
		retry => 0,
		local => {
			enabled => JSON::PP::true,
			port => $local_port,
			index => JSON::PP::true,
			timeout => 30,
			buffer => -1,
		},
		mqtt => {
			enabled => JSON::PP::false,
		},
		meters => [ $meter_config ],
	};

	make_path("$lbhomedir/log/plugins/$lbpplugindir") if (!-d "$lbhomedir/log/plugins/$lbpplugindir");
	make_path($lbpconfigdir) if (!-d $lbpconfigdir);
	open(my $fh, ">", $config_file) or return ("", "", "Could not write vzLogger discovery config $config_file: $!\n");
	print $fh JSON::PP->new->utf8->pretty->canonical->encode($config);
	close($fh);

	return ($config_file, $log_file, "");
}

sub run_vzlogger_obis_test
{
	my ($config_file) = @_;
	my $console_log = "$config_file.output.log";
	unlink($console_log) if (-e $console_log);

	my $pid = fork();
	return "Could not fork vzlogger discovery run: $!\n" if (!defined($pid));
	if ($pid == 0) {
		open STDIN, "</dev/null";
		open STDOUT, ">", $console_log;
		open STDERR, ">&STDOUT";
		exec("vzlogger", "-c", $config_file);
		exit 1;
	}

	my $status = "timeout";
	for (my $i = 0; $i < 15; $i++) {
		my $done = waitpid($pid, WNOHANG);
		if ($done == $pid) {
			$status = "exit=" . ($? >> 8);
			last;
		}
		sleep(1);
	}
	if ($status eq "timeout") {
		kill("TERM", $pid);
		sleep(1);
		kill("KILL", $pid) if (kill(0, $pid));
		waitpid($pid, 0);
	}

	my $output = "";
	if (-e $console_log && open(my $fh, "<", $console_log)) {
		$output = do { local $/; <$fh> };
		close($fh);
	}
	$output .= "\n" if ($output ne "" && $output !~ /\n\z/);
	$output .= "$status\n";
	return $output || "vzlogger discovery run produced no console output.\n";
}

sub channels_from_vzlogger_log
{
	my ($log_file) = @_;
	return () if (!$log_file || !-e $log_file);

	my @channels;
	my %seen;
	if (open(my $fh, "<", $log_file)) {
		while (my $line = <$fh>) {
			while ($line =~ /ObisIdentifier:([A-Za-z0-9]+-\d+:[A-Za-z0-9]+\.\d+\.\d+)(?:\*\d+)?/g) {
				my $identifier = normalize_obis_identifier($1);
				next if (!$identifier || $seen{$identifier} || is_discovery_excluded_identifier($identifier));
				push @channels, {
					identifier => $identifier,
					name => obis_cache_name($identifier),
				};
				$seen{$identifier} = 1;
			}
		}
		close($fh);
	}
	return sort_obis_channels(@channels);
}

sub protocol_for_meter
{
	my ($meter) = @_;
	return "sml" if (defined($meter) && $meter =~ /sml\z/i);
	return "d0" if (defined($meter) && ($meter =~ /d0\z/i || $meter =~ /do\z/i));
	return "";
}

sub default_baudrate
{
	my ($meter) = @_;
	return 115200 if (defined($meter) && $meter =~ /sagemcom/i);
	return 4800 if (defined($meter) && $meter =~ /landisgyr[e]?(320|350)/i);
	return 2400 if (defined($meter) && $meter =~ /(t550|uh50)/i);
	return 9600 if (defined($meter) && $meter =~ /(iskra|pafal|siemens)/i);
	return 300;
}

sub serial_mode
{
	my ($databits, $parity, $stopbits) = @_;
	$databits ||= 7;
	$parity ||= "even";
	$stopbits ||= 1;

	my $parity_char = "N";
	$parity_char = "E" if (lc($parity) eq "even");
	$parity_char = "O" if (lc($parity) eq "odd");

	return "$databits$parity_char$stopbits";
}

sub clean_number
{
	my ($value, $default) = @_;
	return int($value) if (defined($value) && $value =~ /\A\d+\z/);
	return $default;
}

sub clean_integer
{
	my ($value, $default) = @_;
	return int($value) if (defined($value) && $value =~ /\A-?\d+\z/);
	return $default;
}

sub clean_boolean
{
	my ($value, $default) = @_;
	return int($value) if (defined($value) && $value =~ /\A[01]\z/);
	return $default;
}

sub safe_filename
{
	my ($value) = @_;
	$value ||= "";
	$value =~ s/[^A-Za-z0-9_.:-]/_/g;
	return $value || "unknown";
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
		my @available_obis = available_obis_channels($serial);
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
				} @available_obis
			],
			OBIS_CHANNELS_EMPTY => @available_obis ? 0 : 1,
		};
	}
	return @rows;
}

sub enabled_obis_channels
{
	my ($serial) = @_;
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

sub available_obis_channels
{
	my ($serial) = @_;
	my @channels = read_obis_discovery_cache($serial);
	return sort_obis_channels(@channels) if (obis_discovery_cache_exists($serial));

	my %seen;
	foreach my $identifier (config_list_values("$serial.OBISCHANNELS")) {
		$identifier = normalize_obis_identifier($identifier);
		next if (!$identifier || $seen{$identifier});
		push @channels, {
			identifier => $identifier,
			name => obis_cache_name($identifier),
		};
		$seen{$identifier} = 1;
	}
	return sort_obis_channels(@channels);
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

sub custom_channels
{
	my ($serial) = @_;
	my $value = $plugin_cfg->param("$serial.OBISCUSTOM") || "";
	my @channels;
	foreach my $line (split(/\\n|\r?\n|,|;/, $value)) {
		my $identifier = normalize_obis_identifier($line);
		push @channels, $identifier if ($identifier);
	}
	return sort_obis_channels(@channels);
}

sub normalize_obis_identifier
{
	my ($value) = @_;
	return "" if (!defined($value));
	$value =~ s/^\s+|\s+$//g;
	$value =~ s/\*\d+\z//;
	return $value if ($value =~ /\A\d+-\d+:[A-Za-z0-9]+\.\d+\.\d+\z/);
	return "";
}

sub obis_cache_name
{
	my ($identifier) = @_;
	my %known = map { $_->{identifier} => $_->{name} } default_obis_channels();
	return $known{$identifier} if ($known{$identifier});

	my $name = $identifier;
	$name =~ s/\A\d+-\d+://;
	$name =~ s/[^0-9A-Za-z]+/_/g;
	$name =~ s/^_+|_+$//g;
	return "Custom_OBIS_$name";
}

sub obis_discovery_cache_file
{
	my ($serial) = @_;
	$serial =~ s/[^A-Za-z0-9_.:-]/_/g;
	return "$lbpconfigdir/obis_channels_$serial.cache";
}

sub obis_discovery_cache_exists
{
	my ($serial) = @_;
	return -e obis_discovery_cache_file($serial);
}

sub read_obis_discovery_cache
{
	my ($serial) = @_;
	my $file = obis_discovery_cache_file($serial);
	return () if (!-e $file);

	my @channels;
	my %seen;
	if (open(my $fh, "<", $file)) {
		while (my $line = <$fh>) {
			chomp($line);
			my ($identifier, $name) = split(/\t/, $line, 2);
			$identifier = normalize_obis_identifier($identifier);
			next if (!$identifier || $seen{$identifier});
			push @channels, {
				identifier => $identifier,
				name => $name || obis_cache_name($identifier),
			};
			$seen{$identifier} = 1;
		}
		close($fh);
	}
	return @channels;
}

sub write_obis_discovery_cache
{
	my ($serial, @channels) = @_;
	my $file = obis_discovery_cache_file($serial);
	my $tmp = "$file.$$";
	open(my $fh, ">", $tmp) or return;
	foreach my $channel (@channels) {
		print $fh $channel->{identifier} . "\t" . $channel->{name} . "\n";
	}
	close($fh);
	rename($tmp, $file);
}

sub is_discovery_excluded_identifier
{
	my ($identifier) = @_;
	return defined($identifier) && $identifier =~ /\A1-0:(?:1|2)\.99\.0\z/;
}

sub sort_obis_channels
{
	return sort { compare_obis_identifier($a->{identifier}, $b->{identifier}) } @_;
}

sub compare_obis_identifier
{
	my ($left, $right) = @_;
	my @left_parts = obis_sort_parts($left);
	my @right_parts = obis_sort_parts($right);
	for (my $i = 0; $i < @left_parts && $i < @right_parts; $i++) {
		my $cmp = $left_parts[$i] <=> $right_parts[$i];
		return $cmp if ($cmp);
	}
	return ($left || "") cmp ($right || "");
}

sub obis_sort_parts
{
	my ($identifier) = @_;
	return (999, 999, 999, 999, 999) if (!defined($identifier));
	if ($identifier =~ /\A(\d+)-(\d+):([A-Za-z0-9]+)\.(\d+)\.(\d+)\z/) {
		my ($a, $b, $c_part, $d, $e) = ($1, $2, $3, $4, $5);
		my $c = ($c_part =~ /\A\d+\z/) ? int($c_part) : 900 + ord(uc(substr($c_part, 0, 1)));
		return (int($a), int($b), $c, int($d), int($e));
	}
	return (999, 999, 999, 999, 999);
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

sub read_loxberry_mqtt_settings
{
	my ($general_json) = @_;
	$general_json ||= "$lbhomedir/config/system/general.json";
	my %settings = (
		host => "127.0.0.1",
		port => 1883,
		user => "",
		pass => "",
	);
	return \%settings if (!-e $general_json || !open(my $fh, "<", $general_json));
	local $/;
	my $json_text = <$fh>;
	close($fh);
	my $general = eval { JSON::PP->new->utf8->decode($json_text) };
	return \%settings if ($@ || !ref($general) || !ref($general->{Mqtt}));
	my $mqtt = $general->{Mqtt};
	$settings{host} = mqtt_first_value($mqtt, qw(Host Hostname Broker Brokerhost Server IpAddress Ipaddress)) || $settings{host};
	$settings{port} = clean_number(mqtt_first_value($mqtt, qw(Port Brokerport Mqttport)), $settings{port});
	$settings{user} = mqtt_first_value($mqtt, qw(Brokeruser Brokerusername User Username Login)) || "";
	$settings{pass} = mqtt_first_value($mqtt, qw(Brokerpass Brokerpassword Pass Password)) || "";
	return \%settings;
}

sub effective_mqtt_settings
{
	my ($loxberry_mqtt) = @_;
	my %settings = %{$loxberry_mqtt};
	foreach my $mapping ([host => "MQTTHOST"], [user => "MQTTUSER"]) {
		my ($name, $key) = @{$mapping};
		my $override = $plugin_cfg->param("VZLOGGER.$key");
		$settings{$name} = $override if (defined($override) && $override ne "");
	}
	my $port_override = $plugin_cfg->param("VZLOGGER.MQTTPORT");
	$settings{port} = clean_number($port_override, $settings{port}) if (defined($port_override) && $port_override ne "");
	return \%settings;
}

sub save_mqtt_override
{
	my ($key, $value, $pattern, $loxberry_value) = @_;
	return if (!defined($value) || $value !~ $pattern);
	$value = "" if ($value eq "" || $value eq "$loxberry_value");
	$plugin_cfg->param("VZLOGGER.$key", $value);
}

sub mqtt_first_value
{
	my ($hash, @keys) = @_;
	foreach my $key (@keys) {
		return $hash->{$key} if (defined($hash->{$key}) && $hash->{$key} ne "");
	}
	return;
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

sub clean_qos
{
	my ($value, $default) = @_;
	return int($value) if (defined($value) && $value =~ /\A[01]\z/);
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

