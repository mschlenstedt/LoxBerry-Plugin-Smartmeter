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
use File::Copy qw(copy);
use File::Path qw(make_path);
use File::Temp qw(tempdir);
use JSON::PP;
use LoxBerry::System;
#use LoxBerry::Web;
use LoxBerry::JSON; # Available with LoxBerry 2.0
use LoxBerry::Log;
use POSIX qw(:sys_wait_h setsid);
use warnings;
use strict;

##########################################################################
# Variables
##########################################################################

my $log;
my $meter_templates_cache;
my $saved_meter_protocols_cache;

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
	my $response = { ok => JSON::PP::false, state => "failed" };
	eval {
		my $action = $q->{ajaxaction} || "";
		if ($action eq "obis-start") {
			my $config_file = "$lbpconfigdir/smartmeter.cfg";
			$plugin_cfg = Config::Simple->new($config_file) or die "Could not read $config_file";
			ensure_vzlogger_defaults();
			my @heads = detect_heads();
			ensure_head_defaults(@heads);
			# Apply the submitted fields only to the in-memory Config::Simple object.
			# OBIS discovery must use the current draft without persisting normal
			# settings or committing staged meter removals.
			save_vzlogger_form("__draft__", @heads);
			cache_pending_meter_protocol($q->{obis_serial});
			$response = start_obis_discovery_background($q->{obis_serial}, @heads);
		} elsif ($action eq "obis-status") {
			$response = obis_discovery_status();
		} elsif ($action eq "obis-cancel") {
			$response = cancel_obis_discovery($q->{job_id});
		} elsif ($action eq "service-status") {
			load_service_ajax_config();
			$response = service_status_response();
		} elsif ($action eq "service-action") {
			die "Service actions require POST." if (($ENV{REQUEST_METHOD} || "") ne "POST");
			load_service_ajax_config();
			$response = run_service_ajax_action($q->{service_action});
		} elsif ($action eq "form-action") {
			die "Configuration actions require POST." if (($ENV{REQUEST_METHOD} || "") ne "POST");
			$response = run_form_ajax_action($q->{submitaction});
		} elsif ($action eq "debug-log") {
			die "Debug-log creation requires POST." if (($ENV{REQUEST_METHOD} || "") ne "POST");
			$response = run_debug_log_ajax();
		} elsif ($action eq "ir-scan") {
			die "I/R head discovery requires POST." if (($ENV{REQUEST_METHOD} || "") ne "POST");
			load_service_ajax_config();
			$response = scan_ir_heads_ajax();
		} else {
			$response->{message} = "Unknown AJAX action.";
		}
	};
	if ($@) {
		my $error = $@;
		$error =~ s/[\r\n]+/ /g;
		$response = { ok => JSON::PP::false, state => "failed", message => $error || "AJAX request failed." };
	}
	ajax_header();
	print JSON::PP->new->utf8->canonical->encode($response);
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
	ensure_legacy_meter_state(@heads);

	if ($q->{saveformdata}) {
		my $action = $q->{submitaction} || "apply";
		if ($action eq "validate") {
			my $validation = run_draft_validation_ajax();
			$template->param("VZLOGGER_MESSAGE", $validation->{message});
		} elsif ($action eq "debug-log") {
			my $debug = run_debug_log_ajax();
			if ($debug->{ok} && $debug->{log_url}) {
				print $cgi->redirect(-url => $debug->{log_url});
				exit;
			}
			$template->param("VZLOGGER_MESSAGE", $debug->{message});
		} else {
		my $implementation_before_save = implementation_mode();
		my $save_output = "";
		if ($action =~ /\A(?:start|stop|restart)-(?:vzlogger|bridge)\z/) {
			save_service_log_settings($action);
		} else {
			$save_output = save_vzlogger_form(@heads);
		}
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
		my $output = $save_output;
		if ($action eq "read-obis") {
			$output .= read_obis_channels($q->{obis_serial}, @heads);
		} else {
			my $activating_vzlogger = $control_action eq "apply" &&
				$implementation_before_save ne "vzlogger" && implementation_mode() eq "vzlogger";
			$output .= ($control_action eq "apply") ? apply_selected_implementation($activating_vzlogger) : run_control($control_action);
		}
		if ($control_action eq "debug-log" && $output =~ m{Created debug log: \Q$lbhomedir\E/log/plugins/\Q$lbpplugindir\E/([^/\s]+)}) {
			print $cgi->redirect(-url => log_redirect_url("plugins/$lbpplugindir/$1"));
			exit;
		}
		if ($control_action eq "apply") {
			write_apply_log($output, \$output);
		}
		$template->param("VZLOGGER_MESSAGE", $output);
		}
		$plugin_cfg = Config::Simple->new($config_file) or die "Could not reload $config_file";
		@heads = detect_heads();
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
	my $implementation = implementation_mode();
	$template->param("IMPLEMENTATION" => $implementation);
	$template->param("IMPLEMENTATION_SWITCH_VALUE" => ($implementation eq "vzlogger" ? "vzlogger" : "none"));
	$template->param("VZLOGGER_IMPLEMENTATION_ACTIVE" => ($implementation eq "vzlogger"));
	$template->param("LEGACY_IMPLEMENTATION_ACTIVE" => ($implementation eq "legacy"));
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
	$template->param("VZLOGGER_CONFIG_URL" => "./vzlogger_config.cgi");
	$template->param("VZLOGGER_CONFIG_DISABLED" => (-e "$lbpconfigdir/vzlogger.conf" ? "" : "ui-disabled"));
	$template->param("VZLOGGER_LIVEURL" => "http://$ENV{HTTP_HOST}:$local_port/");
	$template->param("VZLOGGER_RENDERED_URL" => "./vzlogger_live.cgi");
	$template->param("METER_TEMPLATES_JSON" => JSON::PP->new->utf8->canonical->encode(load_meter_templates()));
	add_http_cache_template_params(@rows);
	$template->param("ROWS" => \@rows);
	return();
}

sub add_service_template_params
{
	my $vzlogger_expected_active = implementation_mode() eq "vzlogger";
	my $mqtt_enabled = clean_boolean($plugin_cfg->param("VZLOGGER.MQTTENABLED"), 1);
	my $bridge_expected_active = $vzlogger_expected_active && $mqtt_enabled && (($plugin_cfg->param("MAIN.READ") || "0") eq "1");
	my $vzlogger_state = service_state("vzlogger");
	my $bridge_state = service_state("smartmeter-v2-vzlogger-bridge");

	$template->param("VZLOGGER_SERVICE_STATUS" => service_summary("vzlogger"));
	$template->param("BRIDGE_SERVICE_STATUS" => service_summary("smartmeter-v2-vzlogger-bridge"));
	$template->param("BRIDGE_AVAILABILITY_HELP" => ($L{'VZLOGGER.BRIDGE_SERVICE_CONTROL_HELP'} || "Manual control of the SmartMeter bridge."));
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
	$template->param("HTTP_CACHE_AVAILABLE" => ($has_cache ? "1" : "0"));
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

sub load_service_ajax_config
{
	my $config_file = "$lbpconfigdir/smartmeter.cfg";
	$plugin_cfg = Config::Simple->new($config_file) or die "Could not read $config_file";
}

sub service_status_response
{
	my $vzlogger_expected = implementation_mode() eq "vzlogger";
	my $mqtt_enabled = clean_boolean($plugin_cfg->param("VZLOGGER.MQTTENABLED"), 1);
	my $bridge_enabled = (($plugin_cfg->param("MAIN.READ") || "0") eq "1");
	my $bridge_expected = $vzlogger_expected && $mqtt_enabled && $bridge_enabled;
	my $config = generated_config_status();
	my $bridge_startable = $config->{valid} && $mqtt_enabled && $config->{mqtt_enabled};
	return {
		ok => JSON::PP::true,
		applied => {
			vzlogger_enabled => $vzlogger_expected ? JSON::PP::true : JSON::PP::false,
			mqtt_enabled => $mqtt_enabled ? JSON::PP::true : JSON::PP::false,
			bridge_enabled => $bridge_enabled ? JSON::PP::true : JSON::PP::false,
		},
		config => {
			present => $config->{present} ? JSON::PP::true : JSON::PP::false,
			valid => $config->{valid} ? JSON::PP::true : JSON::PP::false,
			mqtt_enabled => $config->{mqtt_enabled} ? JSON::PP::true : JSON::PP::false,
		},
		services => {
			vzlogger => service_status_data("vzlogger", $vzlogger_expected, $config->{valid}),
			bridge => service_status_data("smartmeter-v2-vzlogger-bridge", $bridge_expected, $bridge_startable),
		},
	};
}

sub service_status_data
{
	my ($service, $expected_active, $startable) = @_;
	my $state = service_state($service);
	my $pid = service_pid($service);
	my $installed = service_installed($service);
	my $running = $state eq "active";
	return {
		state => $state,
		pid => $pid,
		installed => $installed ? JSON::PP::true : JSON::PP::false,
		running => $running ? JSON::PP::true : JSON::PP::false,
		status_text => "$state | PID: " . ($pid || "-") . " | Service: $service | " . ($installed ? "installed" : "not installed"),
		status_class => service_status_class($state, $expected_active),
		config_valid => $startable ? JSON::PP::true : JSON::PP::false,
		can_start => $startable ? JSON::PP::true : JSON::PP::false,
		can_restart => $startable ? JSON::PP::true : JSON::PP::false,
		can_stop => $running ? JSON::PP::true : JSON::PP::false,
	};
}

sub run_service_ajax_action
{
	my ($action) = @_;
	my %allowed = map { $_ => 1 } qw(
		start-vzlogger stop-vzlogger restart-vzlogger
		start-bridge stop-bridge restart-bridge
	);
	die "Unknown service action." if (!$allowed{$action || ""});
	my $starting = $action =~ /\A(?:start|restart)-/;
	my $bridge_action = $action =~ /-bridge\z/;
	my $requested_implementation = clean_config_value($q->{implementation}, qr/\A(?:none|vzlogger)\z/, "");
	my $config = generated_config_status();
	if ($action =~ /-vzlogger\z/) {
		die "Enable vzLogger before starting the service." if ($starting && $requested_implementation ne "vzlogger");
	} else {
		my $requested_read = clean_config_value($q->{read}, qr/\A[01]\z/, "");
		die "Enable vzLogger and the SmartMeter bridge before starting the service." if ($starting && ($requested_implementation ne "vzlogger" || $requested_read ne "1"));
	}
	die "The generated vzLogger configuration is missing or invalid. Use Save and apply first." if ($starting && !$config->{valid});
	die "Enable and apply MQTT before starting the SmartMeter bridge." if ($starting && $bridge_action && !clean_boolean($plugin_cfg->param("VZLOGGER.MQTTENABLED"), 1));
	die "MQTT is disabled in the generated vzLogger configuration. Use Save and apply first." if ($starting && $bridge_action && !$config->{mqtt_enabled});

	save_service_log_settings($action);

	my ($output, $exit) = run_control_result($action);
	my $response = service_status_response();
	$response->{ok} = $exit == 0 ? JSON::PP::true : JSON::PP::false;
	$response->{message} = $output;
	return $response;
}

sub run_form_ajax_action
{
	my ($action) = @_;
	my %allowed = map { $_ => 1 } qw(validate apply);
	die "Unknown configuration action." if (!$allowed{$action || ""});
	return run_draft_validation_ajax() if ($action eq "validate");

	load_service_ajax_config();
	ensure_vzlogger_defaults();
	my @heads = detect_heads();
	ensure_head_defaults(@heads);
	ensure_legacy_meter_state(@heads);
	my $implementation_before_save = implementation_mode();
	my $output = save_vzlogger_form(@heads);
	my $exit = 0;

	my $activating_vzlogger = $implementation_before_save ne "vzlogger" && implementation_mode() eq "vzlogger";
	my ($apply_output, $apply_exit) = apply_selected_implementation_result($activating_vzlogger);
	$output .= $apply_output;
	$exit = $apply_exit;

	# Reload persisted values before producing the service snapshot.
	load_service_ajax_config();
	my $response = service_status_response();
	my $operation_ok = $exit == 0;
	$operation_ok = 0 if ($output =~ /(?:\ACould not|\nCould not|\bnot available\b)/i);
	my $meterless = $output =~ /No meter is configured/i;
	my $vzlogger_expected = $response->{applied}->{vzlogger_enabled} && !$meterless;
	my $bridge_expected = $vzlogger_expected && $response->{applied}->{mqtt_enabled} && $response->{applied}->{bridge_enabled};
	if ($vzlogger_expected && !$response->{services}->{vzlogger}->{running}) {
		$operation_ok = 0;
		$output .= "\nApply did not leave the vzLogger service running.\n";
	}
	if ($bridge_expected && !$response->{services}->{bridge}->{running}) {
		$operation_ok = 0;
		$output .= "\nApply did not leave the SmartMeter bridge running.\n";
	}
	if (!$vzlogger_expected && $response->{services}->{vzlogger}->{running}) {
		$operation_ok = 0;
		$output .= "\nApply did not stop the vzLogger service.\n";
	}
	if (!$bridge_expected && $response->{services}->{bridge}->{running}) {
		$operation_ok = 0;
		$output .= "\nApply did not stop the SmartMeter bridge.\n";
	}
	write_apply_log($output, \$output);
	$response->{ok} = $operation_ok ? JSON::PP::true : JSON::PP::false;
	$response->{action} = $action;
	$response->{message} = $output;
	$response->{config_url} = "./vzlogger_config.cgi";
	return $response;
}

sub run_draft_validation_ajax
{
	my $live_config_dir = $lbpconfigdir;
	my $draft_dir = tempdir("smartmeter-vzlogger-validation-XXXXXX", TMPDIR => 1, CLEANUP => 1);
	my $draft_config = "$draft_dir/smartmeter.cfg";
	copy("$live_config_dir/smartmeter.cfg", $draft_config) or die "Could not prepare temporary configuration: $!";
	foreach my $source (glob("$live_config_dir/vzlogger_meter_*.jsonc")) {
		my ($name) = $source =~ m{([^/\\]+)\z};
		copy($source, "$draft_dir/$name") or die "Could not prepare temporary custom meter configuration: $!";
	}

	my ($output, $exit);
	{
		local $lbpconfigdir = $draft_dir;
		$plugin_cfg = Config::Simple->new($draft_config) or die "Could not read temporary configuration";
		ensure_vzlogger_defaults();
		my @heads = detect_heads();
		ensure_head_defaults(@heads);
		ensure_legacy_meter_state(@heads);
		save_vzlogger_form("__draft__", @heads);
		foreach my $device (@heads) {
			my $serial = $device;
			$serial =~ s%/dev/serial/smartmeter/%%g;
			my $mode = normalized_meter_mode($plugin_cfg->param("$serial.METER"), $plugin_cfg->param("$serial.PROTOCOL"));
			save_user_meter_source($serial, $q->{"$serial\_userjson"}) if ($mode eq "user" && defined($q->{"$serial\_userjson"}));
		}
		$plugin_cfg->save;

		local $ENV{SMARTMETER_CONFIG_DIR} = $draft_dir;
		local $ENV{SMARTMETER_CONFIG_FILE} = $draft_config;
		local $ENV{SMARTMETER_VZLOGGER_CONFIG_FILE} = "$draft_dir/vzlogger.conf";
		local $ENV{SMARTMETER_VZLOGGER_MAPPING_FILE} = "$draft_dir/vzlogger_channels.json";
		local $ENV{SMARTMETER_VALIDATION_DRAFT} = "1";
		my ($generate_output, $generate_exit) = run_perl_file_result("$lbpbindir/vzlogger_config.pl");
		$output = $generate_output;
		$exit = $generate_exit;
		if ($exit == 0) {
			my ($validate_output, $validate_exit) = run_perl_file_result("$lbpbindir/vzlogger_validate.pl");
			$output .= $validate_output;
			$exit = $validate_exit;
		}
	}

	return {
		ok => $exit == 0 ? JSON::PP::true : JSON::PP::false,
		action => "validate",
		message => $output,
	};
}

sub run_debug_log_ajax
{
	my $script = "$lbpbindir/vzlogger_control.pl";
	die "Control script not found: $script" if (!-e $script);
	my $output;
	my $exit;
	return {
		ok => JSON::PP::false,
		state => "failed",
		message => "The required timeout command is not available; debug-log creation was not started.",
	} if (!command_exists("timeout"));
	$output = `timeout --signal=TERM --kill-after=5 45 "$^X" "$script" debug-log 2>&1`;
	$exit = $? >> 8;
	$output .= "\nDebug-log creation exceeded the 45-second limit and was stopped.\n" if ($exit == 124 || $exit == 137);
	$output ||= "No output.";
	my $response = {
		ok => $exit == 0 ? JSON::PP::true : JSON::PP::false,
		state => $exit == 0 ? "completed" : "failed",
		message => $output,
	};
	if ($exit == 0 && $output =~ m{Created debug log: \Q$lbhomedir\E/log/plugins/\Q$lbpplugindir\E/([^/\s]+)}) {
		$response->{log_url} = log_redirect_url("plugins/$lbpplugindir/$1");
	} else {
		$response->{ok} = JSON::PP::false;
	}
	return $response;
}

sub run_perl_file_result
{
	my ($script, @arguments) = @_;
	return ("Script not found: $script", 1) if (!-e $script);
	my $argument_text = join(" ", map { my $value = $_; $value =~ s/"/\\"/g; qq{"$value"} } @arguments);
	my $output = `$^X "$script" $argument_text 2>&1`;
	my $exit = $? >> 8;
	$output ||= "No output.";
	return ($output, $exit);
}

sub save_service_log_settings
{
	my ($action) = @_;
	my $starting = $action =~ /\A(?:start|restart)-/;
	if ($action =~ /-vzlogger\z/) {
		die "Invalid vzLogger debug setting." if (!defined($q->{vzlogger_service_debug}) || $q->{vzlogger_service_debug} !~ /\A[01]\z/);
		die "Invalid vzLogger log level." if (!defined($q->{vzlogger_loglevel}) || $q->{vzlogger_loglevel} !~ /\A(?:0|1|3|5|10|15)\z/);
		if ($starting) {
			die "Invalid vzLogger activation setting." if (!defined($q->{implementation}) || $q->{implementation} ne "vzlogger");
			$plugin_cfg->param("MAIN.IMPLEMENTATION", $q->{implementation});
		}
		$plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG", $q->{vzlogger_service_debug});
		$plugin_cfg->param("VZLOGGER.LOGLEVEL", $q->{vzlogger_loglevel});
	} else {
		die "Invalid bridge debug setting." if (!defined($q->{vzlogger_debug}) || $q->{vzlogger_debug} !~ /\A[01]\z/);
		if ($starting) {
			die "Invalid vzLogger activation setting." if (!defined($q->{implementation}) || $q->{implementation} ne "vzlogger");
			die "Invalid bridge activation setting." if (!defined($q->{read}) || $q->{read} ne "1");
			$plugin_cfg->param("MAIN.IMPLEMENTATION", $q->{implementation});
			$plugin_cfg->param("MAIN.READ", $q->{read});
		}
		$plugin_cfg->param("VZLOGGER.DEBUG", $q->{vzlogger_debug});
	}
	$plugin_cfg->save;
	remove_legacy_cronjobs() if ($starting);
}

sub generated_config_status
{
	my $config_file = "$lbpconfigdir/vzlogger.conf";
	my $mapping_file = "$lbpconfigdir/vzlogger_channels.json";
	my $validator = "$lbpbindir/vzlogger_validate.pl";
	my $status = { present => -e $config_file ? 1 : 0, valid => 0, mqtt_enabled => 0 };
	return $status if (!$status->{present});
	open(my $fh, "<", $config_file) or return $status;
	local $/;
	my $json = <$fh>;
	close($fh);
	my $config = eval { JSON::PP->new->utf8->decode($json) };
	return $status if ($@ || ref($config) ne "HASH");
	$status->{mqtt_enabled} = (ref($config->{mqtt}) eq "HASH" && $config->{mqtt}->{enabled}) ? 1 : 0;
	return $status if (!-e $mapping_file || !-e $validator || ref($config->{meters}) ne "ARRAY" || !@{$config->{meters}});
	my $output = `$^X "$validator" 2>&1`;
	$status->{valid} = (($? >> 8) == 0) ? 1 : 0;
	return $status;
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

sub load_meter_templates
{
	return $meter_templates_cache if ($meter_templates_cache);
	my $catalog_file = "$lbptemplatedir/meter_templates.json";
	open(my $catalog_fh, "<", $catalog_file) or die "Could not read meter template catalog $catalog_file: $!";
	local $/;
	my $json = <$catalog_fh>;
	close($catalog_fh);
	my $templates = eval { JSON::PP->new->utf8->decode($json) };
	die "Invalid meter template catalog $catalog_file: $@" if (!$templates || ref($templates) ne "ARRAY");
	my %ids;
	foreach my $entry (@{$templates}) {
		die "Invalid meter template entry in $catalog_file" if (ref($entry) ne "HASH");
		my $id = $entry->{id} || "";
		die "Invalid or duplicate meter template id '$id'" if ($id !~ /\A[A-Za-z0-9_.:-]+\z/ || $ids{$id}++);
		die "Invalid protocol in meter template '$id'" if (($entry->{protocol} || "") !~ /\A(?:sml|d0)\z/);
		die "Invalid serial mode in meter template '$id'" if (($entry->{serial_mode} || "") !~ /\A(?:8n1|7e1|7o1|7n1)\z/i);
		foreach my $field (qw(initial_baudrate read_baudrate read_timeout)) {
			die "Invalid $field in meter template '$id'" if (!defined($entry->{$field}) || $entry->{$field} !~ /\A\d+\z/);
		}
	}
	$meter_templates_cache = $templates;
	return $meter_templates_cache;
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
	$plugin_cfg->param("VZLOGGER.REMOVEDHEADS", "") if (!defined $plugin_cfg->param("VZLOGGER.REMOVEDHEADS"));
	$plugin_cfg->save;
}

sub detect_heads
{
	my %connected = map { $_ => 1 } glob("/dev/serial/smartmeter/*");
	my %removed = map { $_ => 1 } config_list_values("VZLOGGER.REMOVEDHEADS");
	if (($q->{rescan} || "") eq "1") {
		my $changed = 0;
		foreach my $device (keys %connected) {
			my $serial = $device;
			$serial =~ s%/dev/serial/smartmeter/%%g;
			$changed = 1 if (delete $removed{$serial});
		}
		if ($changed) {
			$plugin_cfg->param("VZLOGGER.REMOVEDHEADS", join(",", sort keys %removed));
			$plugin_cfg->save;
		}
	}
	my %heads;
	foreach my $device (keys %connected) {
		my $serial = $device;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		$heads{$device} = 1 if (!$removed{$serial});
	}
	my %config;
	Config::Simple->import_from("$lbpconfigdir/smartmeter.cfg", \%config);
	while (my ($name, $value) = each %config) {
		$heads{$value} = 1 if ($name =~ /\.DEVICE\z/ && $value);
	}
	return sort keys %heads;
}

sub scan_ir_heads_ajax
{
	my @connected = sort glob("/dev/serial/smartmeter/*");
	my %removed = map { $_ => 1 } config_list_values("VZLOGGER.REMOVEDHEADS");
	my %staged = map { $_ => 1 } grep { defined($_) && $_ =~ /\A[A-Za-z0-9_.:-]+\z/ } $cgi->multi_param("staged_removed");
	my @new_devices;
	my @staged_devices;
	my $removed_changed = 0;
	foreach my $device (@connected) {
		my $serial = $device;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		my $was_removed = delete($removed{$serial}) ? 1 : 0;
		$removed_changed ||= $was_removed;
		push @new_devices, $device if ($was_removed || !$plugin_cfg->param("$serial.DEVICE"));
		push @staged_devices, $device if ($staged{$serial} && $plugin_cfg->param("$serial.DEVICE"));
	}
	if ($removed_changed) {
		$plugin_cfg->param("VZLOGGER.REMOVEDHEADS", join(",", sort keys %removed));
		$plugin_cfg->save;
	}

	# Reuse the regular defaults so a newly discovered or explicitly restored
	# reader behaves exactly like one found by the former full-page rescan.
	my @visible_heads = detect_heads();
	ensure_head_defaults(@visible_heads);
	foreach my $device (@new_devices) {
		my $serial = $device;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		mark_pending_meter_new($serial);
	}
	my @found = map {
		my $device = $_;
		my $serial = $device;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		{
			serial => $serial,
			name => $plugin_cfg->param("$serial.NAME") || $serial,
			path => $device,
		}
	} @new_devices;
	my @staged_found = map {
		my $device = $_;
		my $serial = $device;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		{
			serial => $serial,
			name => $plugin_cfg->param("$serial.NAME") || $serial,
			path => $device,
		}
	} @staged_devices;

	my $result = !@connected ? "none" : @found ? "found" : @staged_found ? "staged" : "no_new";
	return {
		ok => JSON::PP::true,
		state => "completed",
		result => $result,
		connected_count => scalar(@connected),
		new_count => scalar(@found),
		heads => \@found,
		staged_count => scalar(@staged_found),
		staged_heads => \@staged_found,
		reload => JSON::PP::false,
	};
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
		$plugin_cfg->param("$serial.ENABLED", "1");
		$plugin_cfg->param("$serial.ALLOWSKIP", "1");
		$plugin_cfg->param("$serial.AGGTIME", "-1");
		$plugin_cfg->param("$serial.PROTOCOL", "");
		$plugin_cfg->param("$serial.STARTBAUDRATE", "");
		$plugin_cfg->param("$serial.BAUDRATE", "");
		$plugin_cfg->param("$serial.BAUDRATESET", "0");
		$plugin_cfg->param("$serial.TIMEOUT", "");
		$plugin_cfg->param("$serial.DELAY", "");
		$plugin_cfg->param("$serial.HANDSHAKE", "");
		$plugin_cfg->param("$serial.DATABITS", "");
		$plugin_cfg->param("$serial.STOPBITS", "");
		$plugin_cfg->param("$serial.PARITY", "");
		$plugin_cfg->param("$serial.INTERVAL", "");
		$plugin_cfg->param("$serial.PULLSEQ", "");
		$plugin_cfg->param("$serial.USELOCALTIME", "0");
		$plugin_cfg->param("$serial.DUMPFILE", "");
		$plugin_cfg->param("$serial.ACKSEQ", "");
		$plugin_cfg->param("$serial.BAUDRATEREAD", "");
		$plugin_cfg->param("$serial.PARITYMODE", "");
		$plugin_cfg->param("$serial.PARITYSET", "0");
		$plugin_cfg->param("$serial.WAITSYNC", "");
		$plugin_cfg->param("$serial.READTIMEOUT", "");
		$plugin_cfg->param("$serial.BAUDRATECHANGEDELAY", "");
		$plugin_cfg->param("$serial.OMSKEY", "");
		$plugin_cfg->param("$serial.MBUSDEBUG", "0");
		$plugin_cfg->param("$serial.OBISCHANNELS", "");
		$plugin_cfg->param("$serial.OBISCUSTOM", "");
	}
	$plugin_cfg->save;
}

sub ensure_legacy_meter_state
{
	my (@heads) = @_;
	my @fields = qw(METER PROTOCOL STARTBAUDRATE BAUDRATE TIMEOUT DELAY HANDSHAKE DATABITS STOPBITS PARITY CRC);
	my $changed = 0;
	foreach my $device (@heads) {
		my $serial = $device;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		next if (defined($plugin_cfg->param("$serial.LEGACY_METER")));
		foreach my $field (@fields) {
			my $value = $plugin_cfg->param("$serial.$field");
			$value = $field eq "METER" ? "0" : "" if (!defined($value));
			$plugin_cfg->param("$serial.LEGACY_$field", $value);
		}
		$changed = 1;
	}
	$plugin_cfg->save if ($changed);
}

sub save_vzlogger_form
{
	my $draft_only = (@_ && $_[0] eq "__draft__") ? shift : "";
	my (@heads) = @_;
	my %known_serials = map {
		my $serial = $_;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		$serial => 1;
	} @heads;
	my %remove_serials;
	if ($draft_only || ($q->{submitaction} || "") eq "apply") {
		foreach my $serial ($cgi->multi_param("remove_meter")) {
			next if (!defined($serial) || $serial !~ /\A[A-Za-z0-9_.:-]+\z/);
			$remove_serials{$serial} = 1 if ($known_serials{$serial});
		}
	}
	my $implementation = implementation_mode();
	if (($q->{implementation_changed} || "") eq "1") {
		$implementation = clean_config_value($q->{implementation}, qr/\A(?:none|vzlogger)\z/, $implementation);
	}
	$plugin_cfg->param("MAIN.IMPLEMENTATION", $implementation);
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

	foreach my $device ($implementation eq "vzlogger" ? @heads : ()) {
		my $serial = $device;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		next if ($remove_serials{$serial});
		my $previous_meter = $plugin_cfg->param("$serial.METER") || "0";
		$plugin_cfg->param("$serial.NAME", clean_config_value($q->{"$serial\_name"}, qr/\A[A-Za-z0-9_-]+\z/, $plugin_cfg->param("$serial.NAME") || $serial));
		my $mode = clean_config_value($q->{"$serial\_meter"}, qr/\A(?:0|sml|d0|oms|user)\z/, normalized_meter_mode($previous_meter, $plugin_cfg->param("$serial.PROTOCOL")));
		$plugin_cfg->param("$serial.METER", $mode);
		my $meter_enabled = 1;
		if ($mode =~ /\A(?:sml|d0|oms)\z/) {
			$meter_enabled = clean_config_value($q->{"$serial\_enabled"}, qr/\A[01]\z/, clean_boolean(config_scalar_value("$serial.ENABLED"), 1));
			$plugin_cfg->param("$serial.ENABLED", $meter_enabled);
		}
		if ($mode =~ /\A(?:sml|d0|oms)\z/ && $meter_enabled) {
			$plugin_cfg->param("$serial.ALLOWSKIP", clean_config_value($q->{"$serial\_allowskip"}, qr/\A[01]\z/, clean_boolean(config_scalar_value("$serial.ALLOWSKIP"), 1)));
			$plugin_cfg->param("$serial.AGGTIME", clean_config_value($q->{"$serial\_aggtime"}, qr/\A(?:-?\d+)?\z/, config_scalar_value("$serial.AGGTIME")));
			$plugin_cfg->param("$serial.INTERVAL", clean_config_value($q->{"$serial\_interval"}, qr/\A(?:-?\d+)?\z/, config_scalar_value("$serial.INTERVAL")));
			$plugin_cfg->param("$serial.PULLSEQ", clean_config_value($q->{"$serial\_pullseq"}, qr/\A[A-Fa-f0-9]*\z/, config_scalar_value("$serial.PULLSEQ")));
			$plugin_cfg->param("$serial.BAUDRATE", clean_config_value($q->{"$serial\_baudrate"}, qr/\A\d*\z/, config_scalar_value("$serial.BAUDRATE")));
			$plugin_cfg->param("$serial.PARITYMODE", clean_config_value($q->{"$serial\_paritymode"}, qr/\A(?:|8n1|7e1|7o1|7n1)\z/i, configured_parity_optional($serial)));
			$plugin_cfg->param("$serial.BAUDRATESET", (defined($q->{"$serial\_baudrate"}) && $q->{"$serial\_baudrate"} ne "") ? "1" : "0");
			$plugin_cfg->param("$serial.PARITYSET", (defined($q->{"$serial\_paritymode"}) && $q->{"$serial\_paritymode"} ne "") ? "1" : "0");
			$plugin_cfg->param("$serial.USELOCALTIME", clean_config_value($q->{"$serial\_uselocaltime"}, qr/\A[01]\z/, clean_boolean(config_scalar_value("$serial.USELOCALTIME"), 0)));
		}
		if ($mode eq "d0" && $meter_enabled) {
			$plugin_cfg->param("$serial.DUMPFILE", clean_config_value($q->{"$serial\_dumpfile"}, qr/\A[^\r\n]*\z/, config_scalar_value("$serial.DUMPFILE")));
			$plugin_cfg->param("$serial.ACKSEQ", clean_config_value($q->{"$serial\_ackseq"}, qr/\A(?:auto|[A-Fa-f0-9]*)\z/, config_scalar_value("$serial.ACKSEQ")));
			$plugin_cfg->param("$serial.BAUDRATEREAD", clean_config_value($q->{"$serial\_baudrateread"}, qr/\A\d*\z/, config_scalar_value("$serial.BAUDRATEREAD") // ""));
			$plugin_cfg->param("$serial.WAITSYNC", clean_config_value($q->{"$serial\_waitsync"}, qr/\A(?:|off|end)\z/, config_scalar_value("$serial.WAITSYNC")));
			$plugin_cfg->param("$serial.READTIMEOUT", clean_config_value($q->{"$serial\_readtimeout"}, qr/\A\d*\z/, first_config_value($serial, "READTIMEOUT", "TIMEOUT") || ""));
			$plugin_cfg->param("$serial.BAUDRATECHANGEDELAY", clean_config_value($q->{"$serial\_baudratechangedelay"}, qr/\A\d*\z/, config_scalar_value("$serial.BAUDRATECHANGEDELAY")));
		}
		if ($mode eq "oms" && $meter_enabled) {
			$plugin_cfg->param("$serial.OMSKEY", clean_config_value($q->{"$serial\_omskey"}, qr/\A(?:[A-Fa-f0-9]{32})?\z/, config_scalar_value("$serial.OMSKEY")));
			$plugin_cfg->param("$serial.MBUSDEBUG", clean_config_value($q->{"$serial\_mbusdebug"}, qr/\A[01]\z/, clean_boolean(config_scalar_value("$serial.MBUSDEBUG"), 0)));
		}
		if (!$draft_only && $mode eq "user" && defined($q->{"$serial\_userjson"})) {
			save_user_meter_source($serial, $q->{"$serial\_userjson"});
		}
		if ($mode =~ /\A(?:sml|d0|oms)\z/ && $meter_enabled) {
			my @selected_obis = grep { normalize_obis_identifier($_) ne "" } $cgi->multi_param("$serial\_obis");
			@selected_obis = map { normalize_obis_identifier($_) } @selected_obis;
			$plugin_cfg->param("$serial.OBISCHANNELS", join(",", @selected_obis));
			$plugin_cfg->param("$serial.OBISCUSTOM", clean_multiline_obis($q->{"$serial\_obis_custom"}));
		}
		unlink(pending_obis_channels_file($serial)) if (!$draft_only && ($q->{submitaction} || "") eq "apply" && -e pending_obis_channels_file($serial));
		unlink(pending_meter_draft_file($serial)) if (!$draft_only && ($q->{submitaction} || "") eq "apply" && -e pending_meter_draft_file($serial));
	}
	my @removed_serials = sort keys %remove_serials;
	if (@removed_serials) {
		my %removed_heads = map { $_ => 1 } config_list_values("VZLOGGER.REMOVEDHEADS");
		foreach my $serial (@removed_serials) {
			foreach my $key ($plugin_cfg->param()) {
				next if ($key =~ /\A\Q$serial\E\.(?:NAME|SERIAL|DEVICE|LEGACY_.+)\z/);
				$plugin_cfg->delete($key) if ($key =~ /\A\Q$serial\E\./);
			}
			$removed_heads{$serial} = 1;
		}
		$plugin_cfg->param("VZLOGGER.REMOVEDHEADS", join(",", sort keys %removed_heads));
	}
	$plugin_cfg->save if (!$draft_only);
	my $cleanup_output = "";
	foreach my $serial ($draft_only ? () : @removed_serials) {
		$cleanup_output .= remove_meter_artifacts($serial);
	}
	return $cleanup_output;
}

sub remove_meter_artifacts
{
	my ($serial) = @_;
	return "" if (!defined($serial) || $serial !~ /\A[A-Za-z0-9_.:-]+\z/);
	my $safe_serial = safe_filename($serial);
	my @files = (
		user_meter_source_file($serial),
		obis_discovery_cache_file($serial),
		pending_obis_channels_file($serial),
		pending_meter_draft_file($serial),
		"$lbpconfigdir/vzLogger_IrTest_$safe_serial.conf",
		"$lbpconfigdir/vzLogger_IrTest_$safe_serial.conf.output.log",
		"$lbhomedir/log/plugins/$lbpplugindir/vzLogger_$safe_serial.log",
		"/var/run/shm/$lbpplugindir/$safe_serial.data",
		"/var/run/shm/$lbpplugindir/$safe_serial.lastcons",
		"/var/run/shm/$lbpplugindir/$safe_serial.lastdel",
	);
	my @errors;
	foreach my $file (@files) {
		next if (!-e $file);
		push @errors, "$file: $!" if (!unlink($file));
	}
	my $mapping_error = remove_meter_channel_mapping($serial);
	push @errors, $mapping_error if ($mapping_error);
	my $output = "Removed meter configuration for $serial.\n";
	$output .= "Could not remove meter artifact $_\n" foreach @errors;
	return $output;
}

sub remove_meter_channel_mapping
{
	my ($serial) = @_;
	my $mapping_file = "$lbpconfigdir/vzlogger_channels.json";
	return "" if (!-e $mapping_file);
	open(my $fh, "<", $mapping_file) or return "$mapping_file: $!";
	local $/;
	my $json = <$fh>;
	close($fh);
	my $mapping = eval { JSON::PP->new->utf8->decode($json || "") };
	return "$mapping_file: invalid JSON" if ($@ || ref($mapping) ne "HASH");
	my $changed = 0;
	foreach my $uuid (keys %{$mapping}) {
		my $entry = $mapping->{$uuid};
		next if (ref($entry) ne "HASH" || !defined($entry->{serial}) || $entry->{serial} ne $serial);
		delete $mapping->{$uuid};
		$changed = 1;
	}
	return "" if (!$changed);
	my $tmp = "$mapping_file.$$";
	open(my $out, ">", $tmp) or return "$tmp: $!";
	print $out JSON::PP->new->utf8->pretty->canonical->encode($mapping);
	close($out) or do { unlink($tmp); return "$tmp: $!"; };
	rename($tmp, $mapping_file) or do { unlink($tmp); return "$mapping_file: $!"; };
	return "";
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

	if (!command_exists("vzlogger")) {
		$output .= "vzlogger binary not found. Install vzlogger before reading OBIS channels.\n";
	} else {
		my ($test_config, $test_log, $config_error) = write_vzlogger_obis_test_config($target_serial);
		if ($config_error) {
			$output .= $config_error;
		} else {
			unlink($test_log) if (-e $test_log);
			my $vzlogger_output = run_vzlogger_obis_test($test_config, $test_log, $was_active);
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

	return $output;
}

sub start_obis_discovery_background
{
	my ($target_serial, @heads) = @_;
	$target_serial = clean_config_value($target_serial, qr/\A[A-Za-z0-9_.:-]+\z/, "");
	return obis_error_status("No I/R head selected for OBIS channel discovery.") if (!$target_serial);

	my %known_heads = map {
		my $serial = $_;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		$serial => 1;
	} @heads;
	return obis_error_status("Unknown I/R head '$target_serial'.") if (!$known_heads{$target_serial});
	return obis_error_status("vzlogger binary not found. Install vzlogger before reading OBIS channels.") if (!command_exists("vzlogger"));
	return obis_error_status("timeout command not found; OBIS discovery was not started.") if (!command_exists("timeout"));

	my $current = read_obis_discovery_status_file();
	if ($current->{state} && $current->{state} =~ /\A(?:starting|running|cancelling)\z/ && obis_discovery_watchdog_is_active()) {
		$current->{ok} = JSON::PP::true;
		return $current;
	}

	my ($test_config, $test_log, $config_error) = write_vzlogger_obis_test_config($target_serial);
	return obis_error_status($config_error) if ($config_error);
	unlink($test_log) if (-e $test_log);

	my $job_id = time() . "-$$-" . int(rand(1000000));
	my $status = {
		ok => JSON::PP::true,
		state => "starting",
		job_id => $job_id,
		serial => $target_serial,
		started_at => time(),
	};
	write_obis_discovery_status_file($status);
	unlink(obis_discovery_cancel_file()) if (-e obis_discovery_cancel_file());

	my $was_active = service_state("vzlogger") eq "active";
	my $launch_output = run_vzlogger_obis_test($test_config, $test_log, $was_active, $target_serial, $job_id, 1);
	if ($launch_output !~ /\Astarted:/) {
		$status->{ok} = JSON::PP::false;
		$status->{state} = "failed";
		$status->{message} = $launch_output || "Could not start OBIS discovery.";
		$status->{finished_at} = time();
		write_obis_discovery_status_file($status);
	}
	return $status;
}

sub obis_error_status
{
	my ($message) = @_;
	$message ||= "OBIS discovery failed.";
	$message =~ s/[\r\n]+\z//;
	return { ok => JSON::PP::false, state => "failed", message => $message };
}

sub obis_discovery_runtime_dir
{
	return "/var/run/shm/$lbpplugindir";
}

sub obis_discovery_status_file
{
	return obis_discovery_runtime_dir() . "/vzlogger_obis_status.json";
}

sub obis_discovery_cancel_file
{
	return obis_discovery_runtime_dir() . "/vzlogger_obis_cancel";
}

sub write_obis_discovery_status_file
{
	my ($status) = @_;
	my $runtime_dir = obis_discovery_runtime_dir();
	make_path($runtime_dir) if (!-d $runtime_dir);
	my $file = obis_discovery_status_file();
	my $tmp = "$file.$$";
	return 0 if (!open(my $fh, ">", $tmp));
	print $fh JSON::PP->new->utf8->canonical->encode($status);
	close($fh);
	return rename($tmp, $file) ? 1 : 0;
}

sub read_obis_discovery_status_file
{
	my $file = obis_discovery_status_file();
	return { state => "idle" } if (!-e $file || !open(my $fh, "<", $file));
	local $/;
	my $json = <$fh>;
	close($fh);
	my $status = eval { JSON::PP->new->utf8->decode($json || "") };
	return ref($status) eq "HASH" ? $status : { state => "idle" };
}

sub obis_discovery_watchdog_is_active
{
	my $pid_file = obis_discovery_runtime_dir() . "/vzlogger_obis_watchdog.pid";
	return 0 if (!-e $pid_file || !open(my $fh, "<", $pid_file));
	my $pid = <$fh>;
	close($fh);
	chomp($pid) if (defined($pid));
	return obis_watchdog_running($pid);
}

sub obis_discovery_status
{
	my $status = read_obis_discovery_status_file();
	if (($status->{state} || "") =~ /\A(?:starting|running|cancelling)\z/ && !obis_discovery_watchdog_is_active()) {
		my $started_at = int($status->{started_at} || 0);
		if (!$started_at || time() - $started_at > 2) {
			$status->{state} = "failed";
			$status->{message} = "The OBIS discovery process ended unexpectedly.";
			$status->{finished_at} = time();
			write_obis_discovery_status_file($status);
		}
	}
	$status->{ok} = JSON::PP::true;
	return $status;
}

sub cancel_obis_discovery
{
	my ($job_id) = @_;
	$job_id = clean_config_value($job_id, qr/\A[0-9-]+\z/, "");
	my $status = read_obis_discovery_status_file();
	return obis_error_status("No matching OBIS discovery is active.") if (!$job_id || ($status->{job_id} || "") ne $job_id);
	return obis_error_status("The OBIS discovery is no longer active.") if (($status->{state} || "") !~ /\A(?:starting|running|cancelling)\z/);

	my $cancel_file = obis_discovery_cancel_file();
	make_path(obis_discovery_runtime_dir()) if (!-d obis_discovery_runtime_dir());
	my $fh;
	if (!open($fh, ">", $cancel_file)) {
		return obis_error_status("Could not request cancellation: $!");
	}
	print $fh $job_id;
	close($fh);
	$status->{state} = "cancelling";
	$status->{ok} = JSON::PP::true;
	write_obis_discovery_status_file($status);
	return $status;
}

sub obis_discovery_cancel_requested
{
	my ($job_id) = @_;
	my $file = obis_discovery_cancel_file();
	return 0 if (!$job_id || !-e $file || !open(my $fh, "<", $file));
	my $requested_job = <$fh>;
	close($fh);
	chomp($requested_job) if (defined($requested_job));
	return ($requested_job || "") eq $job_id ? 1 : 0;
}

sub apply_selected_implementation
{
	my ($activating_vzlogger) = @_;
	my ($output) = apply_selected_implementation_result($activating_vzlogger);
	return $output;
}

sub apply_selected_implementation_result
{
	my ($activating_vzlogger) = @_;
	if (implementation_mode() eq "legacy") {
		my ($output, $exit) = run_control_result("disable-vzlogger");
		$output .= apply_legacy_cron();
		return ($output, $exit);
	}

	remove_legacy_cronjobs();
	return run_control_result("disable-vzlogger") if (implementation_mode() ne "vzlogger");
	return run_control_result($activating_vzlogger ? "activate-vzlogger" : "apply");
}

sub write_vzlogger_obis_test_config
{
	my ($serial) = @_;
	my $meter = $plugin_cfg->param("$serial.METER") || "0";
	my $protocol = normalized_meter_mode($meter, $plugin_cfg->param("$serial.PROTOCOL"));
	return ("", "", "No protocol is configured for $serial.\n") if ($protocol eq "0");
	return ("", "", "OBIS discovery is not available for custom JSON meters.\n") if ($protocol eq "user");
	return ("", "", "The installed vzLogger does not support OMS.\n") if ($protocol eq "oms" && !vzlogger_supports_protocol("oms"));

	my $device = $plugin_cfg->param("$serial.DEVICE") || "/dev/serial/smartmeter/$serial";
	return ("", "", "No serial device is configured for $serial.\n") if (!$device);

	my $meter_config = {
		enabled => JSON::PP::true,
		allowskip => clean_boolean(config_scalar_value("$serial.ALLOWSKIP"), 1) ? JSON::PP::true : JSON::PP::false,
		protocol => $protocol,
		device => $device,
		channels => [],
	};
	set_optional_integer($meter_config, "aggtime", config_scalar_value("$serial.AGGTIME"), 1);

	if ($protocol eq "sml") {
		set_optional_integer($meter_config, "interval", config_scalar_value("$serial.INTERVAL"), 1);
		set_optional_text($meter_config, "pullseq", config_scalar_value("$serial.PULLSEQ"));
		my $legacy_manual = config_scalar_value("$serial.METER") eq "manual";
		set_optional_integer($meter_config, "baudrate", config_scalar_value("$serial.BAUDRATE"), 0) if ($legacy_manual || config_scalar_value("$serial.BAUDRATESET") eq "1");
		set_optional_enum($meter_config, "parity", configured_parity_optional($serial), qr/\A(?:8n1|7e1|7o1|7n1)\z/i) if ($legacy_manual || config_scalar_value("$serial.PARITYSET") eq "1");
		set_optional_boolean($meter_config, "use_local_time", config_scalar_value("$serial.USELOCALTIME"));
	} elsif ($protocol eq "d0") {
		set_optional_integer($meter_config, "interval", config_scalar_value("$serial.INTERVAL"), 1);
		set_optional_text($meter_config, "dump_file", config_scalar_value("$serial.DUMPFILE"));
		set_optional_text($meter_config, "pullseq", config_scalar_value("$serial.PULLSEQ"));
		set_optional_text($meter_config, "ackseq", config_scalar_value("$serial.ACKSEQ"));
		set_optional_integer($meter_config, "baudrate", config_scalar_value("$serial.BAUDRATE"), 0);
		set_optional_integer($meter_config, "baudrate_read", config_scalar_value("$serial.BAUDRATEREAD"), 0);
		set_optional_enum($meter_config, "parity", configured_parity_optional($serial), qr/\A(?:8n1|7e1|7o1|7n1)\z/i);
		set_optional_enum($meter_config, "wait_sync", config_scalar_value("$serial.WAITSYNC"), qr/\A(?:off|end)\z/);
		set_optional_integer($meter_config, "read_timeout", first_config_value($serial, "READTIMEOUT", "TIMEOUT"), 0);
		set_optional_integer($meter_config, "baudrate_change_delay", config_scalar_value("$serial.BAUDRATECHANGEDELAY"), 0);
	} elsif ($protocol eq "oms") {
		set_optional_integer($meter_config, "baudrate", config_scalar_value("$serial.BAUDRATE"), 0);
		set_optional_enum($meter_config, "key", config_scalar_value("$serial.OMSKEY"), qr/\A[A-Fa-f0-9]{32}\z/);
		set_optional_boolean($meter_config, "mbus_debug", config_scalar_value("$serial.MBUSDEBUG"));
		set_optional_boolean($meter_config, "use_local_time", config_scalar_value("$serial.USELOCALTIME"));
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
	my ($config_file, $test_log, $restart_service, $serial, $job_id, $background) = @_;
	my $console_log = "$config_file.output.log";
	my $runtime_dir = "/var/run/shm/$lbpplugindir";
	my $watchdog_pid_file = "$runtime_dir/vzlogger_obis_watchdog.pid";
	unlink($console_log) if (-e $console_log);
	return "timeout command not found; OBIS discovery was not started.\n" if (!command_exists("timeout"));
	if (-e $watchdog_pid_file && open(my $existing_fh, "<", $watchdog_pid_file)) {
		my $existing_pid = <$existing_fh>;
		close($existing_fh);
		chomp($existing_pid) if (defined($existing_pid));
		return "Another vzLogger OBIS discovery run is already active.\n" if (obis_watchdog_running($existing_pid));
		unlink($watchdog_pid_file);
	}

	my $pid = fork();
	return "Could not fork vzlogger discovery run: $!\n" if (!defined($pid));
	if ($pid == 0) {
		setsid() or exit 127;
		$0 = "$lbpplugindir-vzlogger-obis-watchdog";
		open STDIN, "</dev/null";
		open STDOUT, ">", $console_log;
		open STDERR, ">&STDOUT";
		select(STDOUT);
		$| = 1;
		make_path($runtime_dir) if (!-d $runtime_dir);
		if (open(my $pid_fh, ">", $watchdog_pid_file)) {
			print $pid_fh "$$\n";
			close($pid_fh);
		}
		# This watchdog owns the complete service lifecycle. It remains alive if
		# the browser reloads and Apache terminates the parent CGI request.
		my $test_exit = 125;
		my $can_run_test = 1;
		my $cancelled = 0;
		my $restore_failed = 0;
		local $ENV{SMARTMETER_OBIS_WATCHDOG} = "1";
		if ($job_id) {
			write_obis_discovery_status_file({
				ok => JSON::PP::true,
				state => "running",
				job_id => $job_id,
				serial => $serial,
				started_at => time(),
			});
			$cancelled = obis_discovery_cancel_requested($job_id);
		}
		if ($restart_service) {
			system($^X, "$lbpbindir/vzlogger_control.pl", "stop-vzlogger");
			$can_run_test = (($? >> 8) == 0);
		}
		$cancelled = 1 if ($job_id && obis_discovery_cancel_requested($job_id));
		if ($can_run_test && !$cancelled) {
			my $test_pid = fork();
			if (!defined($test_pid)) {
				print "Could not fork bounded vzLogger test process: $!\n";
				$test_exit = 125;
			} elsif ($test_pid == 0) {
				setpgrp(0, 0) or exit 127;
				exec("timeout", "--foreground", "--signal=TERM", "--kill-after=2s", "15s", "vzlogger", "-f", "-c", $config_file);
				exit 127;
			} else {
				if (open(my $pid_fh, ">", $watchdog_pid_file)) {
					print $pid_fh "$$\n$test_pid\n";
					close($pid_fh);
				}
				while (1) {
					sleep(1);
					my $done = waitpid($test_pid, WNOHANG);
					if ($done == $test_pid) {
						$test_exit = wait_status_exit_code($?);
						last;
					}
					if ($done == -1) {
						$test_exit = 125;
						last;
					}
					if ($job_id && obis_discovery_cancel_requested($job_id)) {
						print "OBIS discovery cancellation requested.\n";
						terminate_obis_test_group($test_pid);
						$test_exit = 130;
						$cancelled = 1;
						last;
					}
					my $repeated_channels = repeated_obis_channel_count($test_log);
					if ($repeated_channels > 0) {
						print "Detected $repeated_channels OBIS channel(s) at least twice; stopping discovery early.\n";
						terminate_obis_test_group($test_pid);
						$test_exit = 0;
						last;
					}
				}
			}
		}
		if ($restart_service) {
			system($^X, "$lbpbindir/vzlogger_control.pl", "start-vzlogger");
			if (($? >> 8) != 0) {
				$test_exit = 126;
				$restore_failed = 1;
			}
		}
		if ($job_id) {
			my @channels = $cancelled ? () : channels_from_vzlogger_log($test_log);
			write_obis_discovery_cache($serial, @channels) if (@channels);
			my %pending_channels = map { $_ => 1 } read_pending_obis_channels($serial);
			my %enabled_channels = enabled_obis_channels($serial);
			my @status_channels = map {
				{
					identifier => $_->{identifier},
					name => $_->{name},
					is_new => $pending_channels{$_->{identifier}} ? JSON::PP::true : JSON::PP::false,
					selected => $enabled_channels{$_->{identifier}} ? JSON::PP::true : JSON::PP::false,
				}
			} @channels;
			my $state = $cancelled ? "cancelled" : @channels ? "completed" : "failed";
			my $message = $cancelled ? "OBIS discovery was cancelled." :
				@channels ? "Detected " . scalar(@channels) . " OBIS channel(s)." :
				"No OBIS channels were detected. Check the vzLogger discovery log and meter settings.";
			my $warning = $restore_failed ? "OBIS channels were detected, but the regular vzLogger service could not be restored." : "";
			my $details = "";
			if (-e $console_log && open(my $detail_fh, "<", $console_log)) {
				$details = do { local $/; <$detail_fh> };
				close($detail_fh);
			}
			write_control_log("read-obis-vzlogger", "config=$config_file\nlog=$test_log\nstate=$state\n$message\n" . ($warning ? "warning=$warning\n" : "") . $details);
			write_obis_discovery_status_file({
				ok => $state eq "failed" ? JSON::PP::false : JSON::PP::true,
				state => $state,
				job_id => $job_id,
				serial => $serial,
				channel_count => scalar(@channels),
				channels => \@status_channels,
				message => $message,
				warning => $warning,
				restore_failed => $restore_failed ? JSON::PP::true : JSON::PP::false,
				started_at => read_obis_discovery_status_file()->{started_at} || time(),
				finished_at => time(),
			});
			unlink(obis_discovery_cancel_file()) if (-e obis_discovery_cancel_file());
		}
		unlink($watchdog_pid_file);
		exit($test_exit);
	}
	make_path($runtime_dir) if (!-d $runtime_dir);
	if (open(my $pid_fh, ">", $watchdog_pid_file)) {
		print $pid_fh "$pid\n";
		close($pid_fh);
	}
	return "started:$pid\n" if ($background);

	waitpid($pid, 0);
	my $exit_code = ($? & 127) ? 128 + ($? & 127) : $? >> 8;
	my $status = $exit_code == 124 ? "timeout" : "exit=$exit_code";

	my $output = "";
	if (-e $console_log && open(my $fh, "<", $console_log)) {
		$output = do { local $/; <$fh> };
		close($fh);
	}
	$output .= "\n" if ($output ne "" && $output !~ /\n\z/);
	$output .= "$status\n";
	return $output || "vzlogger discovery run produced no console output.\n";
}

sub repeated_obis_channel_count
{
	my ($log_file) = @_;
	return 0 if (!$log_file || !-e $log_file);
	my %counts;
	open(my $fh, "<", $log_file) or return 0;
	while (my $line = <$fh>) {
		while ($line =~ /ObisIdentifier:((?:\d+-\d+:)?[A-Za-z0-9]+\.\d+\.\d+)(?:\*\d+)?/g) {
			my $identifier = normalize_obis_identifier($1);
			next if (!$identifier || is_discovery_excluded_identifier($identifier));
			$counts{$identifier}++;
		}
	}
	close($fh);
	return 0 if (!keys(%counts));
	foreach my $count (values(%counts)) {
		return 0 if ($count < 2);
	}
	return scalar(keys(%counts));
}

sub terminate_obis_test_group
{
	my ($pid) = @_;
	return if (!$pid || $pid !~ /\A\d+\z/);
	kill("TERM", -int($pid));
	for (my $i = 0; $i < 20; $i++) {
		my $done = waitpid(int($pid), WNOHANG);
		return if ($done == int($pid) || $done == -1);
		select(undef, undef, undef, 0.1);
	}
	kill("KILL", -int($pid));
	waitpid(int($pid), 0);
}

sub wait_status_exit_code
{
	my ($status) = @_;
	return 128 + ($status & 127) if ($status & 127);
	return $status >> 8;
}

sub obis_watchdog_running
{
	my ($pid) = @_;
	return 0 if (!$pid || $pid !~ /\A\d+\z/ || !kill(0, int($pid)));
	open(my $cmdline_fh, "<", "/proc/$pid/cmdline") or return 0;
	local $/;
	my $cmdline = <$cmdline_fh>;
	close($cmdline_fh);
	return ($cmdline || "") =~ /\A\Q$lbpplugindir-vzlogger-obis-watchdog\E(?:\0|\s|\z)/ ? 1 : 0;
}

sub channels_from_vzlogger_log
{
	my ($log_file) = @_;
	return () if (!$log_file || !-e $log_file);

	my @channels;
	my %seen;
	if (open(my $fh, "<", $log_file)) {
		while (my $line = <$fh>) {
			while ($line =~ /ObisIdentifier:((?:\d+-\d+:)?[A-Za-z0-9]+\.\d+\.\d+)(?:\*\d+)?/g) {
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
	return "oms" if (defined($meter) && $meter =~ /oms\z/i);
	return "";
}

sub normalized_meter_mode
{
	my ($meter, $manual_protocol) = @_;
	$meter ||= "0";
	return $meter if ($meter =~ /\A(?:0|sml|d0|oms|user)\z/);
	if ($meter eq "manual") {
		my $mapped = protocol_for_meter($manual_protocol);
		return $mapped || "user";
	}
	return "sml" if ($meter =~ /sml\z/i);
	return "d0" if ($meter =~ /(?:d0|do)\z/i);
	return "oms" if ($meter =~ /oms\z/i);
	return "user";
}

sub first_config_value
{
	my ($section, @keys) = @_;
	foreach my $key (@keys) {
		my $value = config_scalar_value("$section.$key");
		return $value if (defined($value) && $value ne "");
	}
	return undef;
}

sub config_scalar_value
{
	my ($key) = @_;
	my @values = $plugin_cfg->param($key);
	return "" if (!@values);
	return "" if (!defined($values[0]) || ref($values[0]));
	return "$values[0]";
}

sub configured_parity_optional
{
	my ($section) = @_;
	my $mode = config_scalar_value("$section.PARITYMODE");
	return lc($mode) if (defined($mode) && $mode =~ /\A(?:8n1|7e1|7o1|7n1)\z/i);
	my $legacy = serial_mode(
		$plugin_cfg->param("$section.DATABITS"),
		$plugin_cfg->param("$section.PARITY"),
		$plugin_cfg->param("$section.STOPBITS")
	);
	return lc($legacy) if (first_config_value($section, "DATABITS", "PARITY", "STOPBITS"));
	return "";
}

sub set_optional_text
{
	my ($target, $key, $value) = @_;
	return if (!defined($value) || ref($value) || $value eq "");
	$value =~ s/[\r\n]//g;
	$target->{$key} = $value if ($value ne "");
}

sub set_optional_integer
{
	my ($target, $key, $value, $allow_negative) = @_;
	return if (!defined($value) || ref($value) || $value eq "");
	my $pattern = $allow_negative ? qr/\A-?\d+\z/ : qr/\A\d+\z/;
	$target->{$key} = int($value) if ($value =~ $pattern);
}

sub set_optional_enum
{
	my ($target, $key, $value, $pattern) = @_;
	return if (!defined($value) || ref($value) || $value eq "");
	$target->{$key} = lc($value) if ($value =~ $pattern);
}

sub set_optional_boolean
{
	my ($target, $key, $value) = @_;
	return if (!defined($value) || ref($value) || $value !~ /\A[01]\z/);
	$target->{$key} = $value eq "1" ? JSON::PP::true : JSON::PP::false;
}

sub user_meter_source_file
{
	my ($serial) = @_;
	return "$lbpconfigdir/vzlogger_meter_" . safe_filename($serial) . ".jsonc";
}

sub save_user_meter_source
{
	my ($serial, $source) = @_;
	$source = "" if (!defined($source));
	return 0 if (length($source) > 65536);
	make_path($lbpconfigdir) if (!-d $lbpconfigdir);
	my $file = user_meter_source_file($serial);
	my $tmp = "$file.$$";
	open(my $fh, ">", $tmp) or return 0;
	print $fh $source;
	close($fh);
	rename($tmp, $file) or do { unlink($tmp); return 0; };
	return 1;
}

sub read_user_meter_source
{
	my ($serial) = @_;
	my $file = user_meter_source_file($serial);
	return "" if (!-e $file || -s $file > 65536);
	open(my $fh, "<", $file) or return "";
	local $/;
	my $source = <$fh>;
	close($fh);
	return $source;
}

sub validate_user_meter_source
{
	my ($serial) = @_;
	my $file = user_meter_source_file($serial);
	return (undef, "JSONC source file does not exist", "") if (!-e $file);
	return (undef, "JSONC source exceeds 64 KiB", "") if (-s $file > 65536);
	my $source = read_user_meter_source($serial);
	my $meter = eval { JSON::PP->new->utf8->relaxed(1)->decode($source) };
	if ($@) {
		my $error = format_json_error($source, $@);
		return (undef, $error || "Invalid JSONC", "");
	}
	return (undef, "The JSONC source must contain one meter object", "") if (ref($meter) ne "HASH");
	return (undef, "Root sections such as meters, mqtt, local, push or retry are not allowed", "") if (grep { exists($meter->{$_}) } qw(meters mqtt local push retry verbosity log));
	return (undef, "The meter object requires a non-empty protocol string", "") if (!defined($meter->{protocol}) || ref($meter->{protocol}) || $meter->{protocol} eq "");
	if (exists($meter->{channels})) {
		return (undef, "channels must be an array", "") if (ref($meter->{channels}) ne "ARRAY");
		foreach my $channel (@{$meter->{channels}}) {
			return (undef, "Every channels entry must be an object", "") if (ref($channel) ne "HASH");
		}
	}
	my $warning = "";
	if (defined($meter->{device}) && !ref($meter->{device}) && $meter->{device} =~ m{\A/} && !-e $meter->{device}) {
		$warning = "Configured device '$meter->{device}' does not exist.";
	}
	return ($meter, "", $warning);
}

sub format_json_error
{
	my ($source, $error) = @_;
	$error ||= "Invalid JSONC";
	$error =~ s/\s+at\s+\S+\s+line\s+\d+\.?\s*\z//;
	if ($error =~ /character offset\s+(\d+)/i) {
		my $offset = $1;
		my $prefix = substr($source || "", 0, $offset);
		my $line = 1 + ($prefix =~ tr/\n/\n/);
		my $last_newline = rindex($prefix, "\n");
		my $column = length($prefix) - $last_newline;
		$error .= " (line $line, column $column)";
	}
	return $error;
}

sub vzlogger_supports_protocol
{
	my ($protocol) = @_;
	return 0 if (!command_exists("vzlogger"));
	my $help = `vzlogger -h 2>&1`;
	return $help =~ /^\s*\Q$protocol\E\s+/mi ? 1 : 0;
}

sub default_baudrate
{
	my ($meter) = @_;
	foreach my $template (@{load_meter_templates()}) {
		return $template->{initial_baudrate} if (($template->{id} || "") eq ($meter || ""));
	}
	return undef;
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
	return $mode if ($mode =~ /\A(?:none|legacy|vzlogger)\z/);
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
	my $oms_supported = vzlogger_supports_protocol("oms");
	my $saved_meter_protocols = read_saved_vzlogger_meter_protocols();
	foreach my $device (@heads) {
		my $serial = $device;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		my $stored_meter = $plugin_cfg->param("$serial.METER") || "0";
		my $meter_draft = read_pending_meter_draft($serial);
		my $configured_device = $plugin_cfg->param("$serial.DEVICE") || $device;
		my $mode = resolve_meter_mode_for_row(
			$saved_meter_protocols->{$configured_device},
			$meter_draft,
			$stored_meter,
			$plugin_cfg->param("$serial.PROTOCOL"),
		);
		my %enabled_obis = enabled_obis_channels($serial);
		my %pending_obis = map { $_ => 1 } read_pending_obis_channels($serial);
		my @available_obis = available_obis_channels($serial);
		my ($json_error, $device_warning) = ("", "");
		if ($mode eq "user") {
			my $unused_meter;
			($unused_meter, $json_error, $device_warning) = validate_user_meter_source($serial);
		}
		my $oms_warning = ($mode eq "oms" && !$oms_supported) ?
			($L{'VZLOGGER.METER_WARNING_OMS_UNAVAILABLE'} || "The installed vzLogger does not support OMS.") : "";
		my $warning_text = $json_error || $device_warning || $oms_warning;
		$warning_text = ($L{'VZLOGGER.METER_WARNING_INVALID_JSON'} || "Custom meter configuration is invalid") . ": " . $json_error if ($json_error);
		$warning_text = ($L{'VZLOGGER.METER_WARNING_DEVICE'} || "Configured device is unavailable") . ": " . $device_warning if (!$json_error && $device_warning);
		my $warning_kind = $json_error ? "user" : $device_warning ? "user" : $oms_warning ? "oms" : "";
		my %protocol_labels = (
			"0" => ($L{'FORMTABLEROWS.PLEASESELECT'} || "Please select"),
			sml => "SML",
			d0 => "D0",
			oms => "OMS",
			user => ($L{'VZLOGGER.PROTOCOL_USER'} || "Custom (JSON)"),
		);
		my $baudrate = first_config_value($serial, "BAUDRATE");
		$baudrate = undef if ($mode eq "sml" && config_scalar_value("$serial.BAUDRATESET") ne "1" && $stored_meter ne "manual");
		$baudrate = default_baudrate($stored_meter) if (!defined($baudrate) && $mode eq "d0" && $stored_meter ne "d0");
		$baudrate = "" if (!defined($baudrate));
		push @rows, {
			NAME => $plugin_cfg->param("$serial.NAME") || $serial,
			SERIAL => $serial,
			DEVICE => $plugin_cfg->param("$serial.DEVICE") || $device,
			METER => $mode,
			PENDING_METER => $meter_draft->{new_reader} ? 1 : 0,
			PROTOCOL_LABEL => $protocol_labels{$mode},
			METER_ENABLED => clean_boolean(config_scalar_value("$serial.ENABLED"), 1),
			ALLOWSKIP => clean_boolean(config_scalar_value("$serial.ALLOWSKIP"), 1),
			AGGTIME => config_scalar_value("$serial.AGGTIME"),
			INTERVAL => config_scalar_value("$serial.INTERVAL"),
			PULLSEQ => first_config_value($serial, "PULLSEQ") // "",
			BAUDRATE => $baudrate,
			PARITYMODE => ($mode eq "sml" && config_scalar_value("$serial.PARITYSET") ne "1" && $stored_meter ne "manual") ? "" : configured_parity_optional($serial),
			USELOCALTIME => clean_boolean(config_scalar_value("$serial.USELOCALTIME"), 0),
			DUMPFILE => first_config_value($serial, "DUMPFILE") // "",
			ACKSEQ => first_config_value($serial, "ACKSEQ") // "",
			BAUDRATEREAD => config_scalar_value("$serial.BAUDRATEREAD") // "",
			WAITSYNC => first_config_value($serial, "WAITSYNC") // "",
			READTIMEOUT => first_config_value($serial, "READTIMEOUT", "TIMEOUT") // "",
			BAUDRATECHANGEDELAY => first_config_value($serial, "BAUDRATECHANGEDELAY") // "",
			OMSKEY => first_config_value($serial, "OMSKEY") // "",
			MBUSDEBUG => clean_boolean(config_scalar_value("$serial.MBUSDEBUG"), 0),
			USER_JSON => read_user_meter_source($serial),
			HAS_WARNING => $warning_text ? 1 : 0,
			SHOW_WARNING_DETAIL => ($json_error || $device_warning) ? 1 : 0,
			WARNING_TEXT => $warning_text,
			WARNING_KIND => $warning_kind,
			COLLAPSED => ($json_error || (($q->{obis_serial} || "") eq $serial)) ? "false" : "true",
			OMS_SUPPORTED => $oms_supported ? 1 : 0,
			OMS_UNSUPPORTED => $oms_supported ? 0 : 1,
			OBIS_DISABLED => ($mode eq "oms" && !$oms_supported) ? "disabled" : "",
			OBIS_CUSTOM => $plugin_cfg->param("$serial.OBISCUSTOM") || "",
			OBIS_CHANNELS => [
				map {
					{
						FIELD_NAME => "$serial\_obis",
						IDENTIFIER => $_->{identifier},
						NAME => $_->{name},
						CHECKED => $enabled_obis{$_->{identifier}} ? "checked" : "",
						IS_NEW => $pending_obis{$_->{identifier}} ? 1 : 0,
					}
				} @available_obis
			],
			OBIS_CHANNELS_EMPTY => @available_obis ? 0 : 1,
		};
	}
	return @rows;
}

sub resolve_meter_mode_for_row
{
	my ($saved_protocol, $meter_draft, $stored_meter, $stored_protocol) = @_;
	return $saved_protocol if (($saved_protocol || "") =~ /\A(?:sml|d0|oms|user)\z/);
	return $meter_draft->{protocol} if (ref($meter_draft) eq "HASH" && ($meter_draft->{new_reader} || 0) && ($meter_draft->{protocol} || "") =~ /\A(?:sml|d0|oms)\z/);
	return normalized_meter_mode($stored_meter, $stored_protocol);
}

sub read_saved_vzlogger_meter_protocols
{
	return $saved_meter_protocols_cache if (defined($saved_meter_protocols_cache));
	$saved_meter_protocols_cache = {};
	my $config_file = "$lbpconfigdir/vzlogger.conf";
	return $saved_meter_protocols_cache if (!-e $config_file || !open(my $fh, "<", $config_file));
	local $/;
	my $json = <$fh>;
	close($fh);
	my $config = eval { JSON::PP->new->utf8->decode($json || "") };
	return $saved_meter_protocols_cache if ($@ || ref($config) ne "HASH" || ref($config->{meters}) ne "ARRAY");
	foreach my $meter (@{$config->{meters}}) {
		next if (ref($meter) ne "HASH");
		my $device = $meter->{device};
		my $protocol = $meter->{protocol};
		next if (!defined($device) || ref($device) || $device eq "" || !defined($protocol) || ref($protocol) || $protocol eq "");
		$protocol = lc($protocol);
		$saved_meter_protocols_cache->{$device} = $protocol =~ /\A(?:sml|d0|oms)\z/ ? $protocol : "user";
	}
	return $saved_meter_protocols_cache;
}

sub enabled_obis_channels
{
	my ($serial) = @_;
	my %enabled = map { $_ => 1 } config_list_values("$serial.OBISCHANNELS");
	$enabled{$_} = 1 foreach read_pending_obis_channels($serial);
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
	return $value if ($value =~ /\A(?:\d+-\d+:)?[A-Za-z0-9]+\.\d+\.\d+\z/);
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

sub pending_obis_channels_file
{
	my ($serial) = @_;
	$serial =~ s/[^A-Za-z0-9_.:-]/_/g;
	return "$lbpconfigdir/obis_channels_$serial.pending";
}

sub pending_meter_draft_file
{
	my ($serial) = @_;
	$serial = safe_filename($serial || "");
	return "$lbpconfigdir/meter_draft_$serial.json";
}

sub read_pending_meter_draft
{
	my ($serial) = @_;
	my $file = pending_meter_draft_file($serial);
	return {} if (!-e $file || !open(my $fh, "<", $file));
	local $/;
	my $json = <$fh>;
	close($fh);
	my $draft = eval { JSON::PP->new->utf8->decode($json || "") };
	return {} if ($@ || ref($draft) ne "HASH");
	return $draft;
}

sub write_pending_meter_draft
{
	my ($serial, $draft) = @_;
	return 0 if (!defined($serial) || $serial !~ /\A[A-Za-z0-9_.:-]+\z/ || ref($draft) ne "HASH");
	my $file = pending_meter_draft_file($serial);
	my $tmp = "$file.$$";
	open(my $fh, ">", $tmp) or return 0;
	print $fh JSON::PP->new->utf8->canonical->encode($draft);
	close($fh) or do { unlink($tmp); return 0; };
	return rename($tmp, $file) ? 1 : do { unlink($tmp); 0 };
}

sub mark_pending_meter_new
{
	my ($serial) = @_;
	my $draft = read_pending_meter_draft($serial);
	$draft->{new_reader} = 1;
	write_pending_meter_draft($serial, $draft);
}

sub cache_pending_meter_protocol
{
	my ($serial) = @_;
	return if (!defined($serial) || $serial !~ /\A[A-Za-z0-9_.:-]+\z/ || !-e pending_meter_draft_file($serial));
	my $mode = normalized_meter_mode($plugin_cfg->param("$serial.METER"), $plugin_cfg->param("$serial.PROTOCOL"));
	return if ($mode !~ /\A(?:sml|d0|oms)\z/);
	my $draft = read_pending_meter_draft($serial);
	$draft->{new_reader} = 1;
	$draft->{protocol} = $mode;
	write_pending_meter_draft($serial, $draft);
}

sub read_pending_obis_channels
{
	my ($serial) = @_;
	my $file = pending_obis_channels_file($serial);
	return () if (!-e $file || !open(my $fh, "<", $file));
	my %seen;
	my @identifiers;
	while (my $line = <$fh>) {
		chomp($line);
		my $identifier = normalize_obis_identifier($line);
		next if (!$identifier || $seen{$identifier});
		push @identifiers, $identifier;
		$seen{$identifier} = 1;
	}
	close($fh);
	return @identifiers;
}

sub write_pending_obis_channels
{
	my ($serial, @identifiers) = @_;
	my $file = pending_obis_channels_file($serial);
	my %seen;
	@identifiers = grep { $_ && !$seen{$_}++ } map { normalize_obis_identifier($_) } @identifiers;
	if (!@identifiers) {
		unlink($file) if (-e $file);
		return 1;
	}
	my $tmp = "$file.$$";
	open(my $fh, ">", $tmp) or return 0;
	print $fh "$_\n" foreach sort_obis_identifiers(@identifiers);
	close($fh) or do { unlink($tmp); return 0; };
	return rename($tmp, $file) ? 1 : do { unlink($tmp); 0 };
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
	my %known = map { $_->{identifier} => 1 } read_obis_discovery_cache($serial);
	$known{$_} = 1 foreach config_list_values("$serial.OBISCHANNELS");
	my %previous_pending = map { $_ => 1 } read_pending_obis_channels($serial);
	my %found = map { $_->{identifier} => 1 } @channels;
	my @pending = grep { $found{$_} } keys %previous_pending;
	push @pending, map { $_->{identifier} } grep { !$known{$_->{identifier}} } @channels;
	my $file = obis_discovery_cache_file($serial);
	my $tmp = "$file.$$";
	open(my $fh, ">", $tmp) or return;
	foreach my $channel (@channels) {
		print $fh $channel->{identifier} . "\t" . $channel->{name} . "\n";
	}
	close($fh);
	return if (!rename($tmp, $file));
	write_pending_obis_channels($serial, @pending);
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

sub sort_obis_identifiers
{
	return map { $_->{identifier} } sort_obis_channels(map { { identifier => $_ } } @_);
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
	if ($identifier =~ /\A([A-Za-z0-9]+)\.(\d+)\.(\d+)\z/) {
		my ($c_part, $d, $e) = ($1, $2, $3);
		my $c = ($c_part =~ /\A\d+\z/) ? int($c_part) : 900 + ord(uc(substr($c_part, 0, 1)));
		return (0, 0, $c, int($d), int($e));
	}
	return (999, 999, 999, 999, 999);
}

sub run_control
{
	my ($action) = @_;
	my ($output) = run_control_result($action);
	return $output;
}

sub run_control_result
{
	my ($action) = @_;
	my $script = "$lbpbindir/vzlogger_control.pl";
	return ("Control script not found: $script", 1) if (!-e $script);
	my $output = `$^X "$script" "$action" 2>&1`;
	my $exit = $? >> 8;
	$output ||= "No output.";
	write_control_log($action, $output);
	return ($output, $exit);
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

sub write_apply_log
{
	my ($output, $display_output) = @_;
	my $apply_log = "$lbhomedir/log/plugins/$lbpplugindir/vzlogger_apply.log";
	make_path("$lbhomedir/log/plugins/$lbpplugindir") if (!-d "$lbhomedir/log/plugins/$lbpplugindir");
	return if (!open(my $apply_fh, ">", $apply_log));
	print $apply_fh $output;
	close($apply_fh);
	my $notice = "\nApply log: $apply_log\n";
	${$display_output} .= $notice if ($display_output);
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

