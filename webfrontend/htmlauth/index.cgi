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
use File::Copy qw(copy);
use File::Path qw(make_path);
use File::Temp qw(tempdir);
use FindBin;
use JSON::PP;
use LoxBerry::System;
use LoxBerry::Log;
#use LoxBerry::Web;
use LoxBerry::JSON; # Available with LoxBerry 2.0
use POSIX qw(:sys_wait_h setsid);
use warnings;
use strict;
umask(0027);
use lib $lbpbindir;
use lib "$FindBin::Bin/../../bin";
use SmartMeterConfig;
use SmartMeterVZLoggerChannels qw(parse_obis compose_obis normalize_obis default_output_key stable_uuid read_json write_json_atomic load_catalog lookup_obis new_document migrate_legacy_meter validate_document localize_validation_errors);
use SmartMeterVZLoggerExpert qw(read_text write_text_atomic validate_expert_text format_expert_validation localize_expert_validation build_expert_mapping update_expert_log_settings expert_configs_equal);
use SmartMeterVZLoggerRuntime qw(acquire_config_lock promote_files_atomic);
use SmartMeterVZLoggerConfig qw(protocol_for_meter normalized_meter_mode serial_mode clean_qos set_implementation_mode);

##########################################################################
# Variables
##########################################################################

my $meter_templates_cache;
my $saved_meter_protocols_cache;
my $channel_document;
my $obis_catalog;
our $configuration_action_deadline;
our $configuration_action_timed_out = 0;

# Read Form
my $cgi = CGI->new;
my $q = $cgi->Vars;

my $version = LoxBerry::System::pluginversion();
my $template;
my $plugin_cfg;
my $initial_request = scalar(keys %{$q}) == 0;

# Language Phrases
my %L;

require LoxBerry::Web;
$template = HTML::Template->new(
	filename => "$lbptemplatedir/settings.html",
	global_vars => 1,
	loop_context_vars => 1,
	die_on_bad_params => 0,
);
%L = LoxBerry::System::readlanguage($template, "language.ini");

sub ui_text
{
	my ($text, %values) = @_;
	$text = "" if (!defined($text));
	foreach my $name (keys %values) {
		my $value = defined($values{$name}) ? $values{$name} : "";
		$text =~ s/\{\Q$name\E\}/$value/g;
	}
	return $text;
}

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
	my $request_lock;
	eval {
		my $action = $q->{ajaxaction} || "";
		my %mutating = map { $_ => 1 } qw(obis-start obis-cancel service-action form-action ir-scan expert-mode expert-reset);
		if ($mutating{$action}) {
			my ($lock, $error) = acquire_config_lock("/var/run/shm/$lbpplugindir");
			die "$error\n" if (!$lock);
			$request_lock = $lock;
			$ENV{SMARTMETER_CONFIG_LOCK_HELD} = "1";
		}
		if ($action eq "obis-start") {
			my $config_file = "$lbpconfigdir/smartmeter.json";
			$plugin_cfg = SmartMeterConfig->new($config_file) or die "Could not read $config_file";
			ensure_vzlogger_defaults();
			die $L{'VZLOGGER.UI_SAVE_VZLOGGER_FIRST'} if (implementation_mode() ne "vzlogger");
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
			die $L{'VZLOGGER.UI_SERVICE_ACTION_POST'} if (($ENV{REQUEST_METHOD} || "") ne "POST");
			load_service_ajax_config();
			$response = run_service_ajax_action($q->{service_action});
		} elsif ($action eq "form-action") {
			die $L{'VZLOGGER.UI_CONFIG_ACTION_POST'} if (($ENV{REQUEST_METHOD} || "") ne "POST");
			$response = run_form_ajax_action($q->{submitaction});
		} elsif ($action eq "debug-log") {
			die $L{'VZLOGGER.UI_DEBUG_LOG_POST'} if (($ENV{REQUEST_METHOD} || "") ne "POST");
			$response = run_debug_log_ajax();
		} elsif ($action eq "ir-scan") {
			die $L{'VZLOGGER.UI_IR_SCAN_POST'} if (($ENV{REQUEST_METHOD} || "") ne "POST");
			load_service_ajax_config();
			$response = scan_ir_heads_ajax();
		} elsif ($action eq "expert-mode") {
			die $L{'VZLOGGER.UI_EXPERT_MODE_POST'} if (($ENV{REQUEST_METHOD} || "") ne "POST");
			load_service_ajax_config();
			$response = set_expert_mode_ajax($q->{enabled});
		} elsif ($action eq "expert-reset") {
			die $L{'VZLOGGER.UI_EXPERT_RESET_POST'} if (($ENV{REQUEST_METHOD} || "") ne "POST");
			load_service_ajax_config();
			$response = reset_expert_configuration_ajax();
		} else {
			$response->{message} = $L{'VZLOGGER.UI_UNKNOWN_AJAX'};
		}
	};
	if ($@) {
		my $error = $@;
		$error =~ s/[\r\n]+/ /g;
		$response = { ok => JSON::PP::false, state => "failed", message => $error || $L{'VZLOGGER.UI_AJAX_FAILED'} };
	}
	ajax_header();
	print JSON::PP->new->utf8->canonical->encode($response);
	exit;

##########################################################################
# Normal request (not AJAX)
##########################################################################

} else {
	
	$q->{form} = "vzlogger" if !$q->{form};

	if ($q->{form} eq "vzlogger") { &form_vzlogger() }

	# Print the form
	&form_print();
}

exit;

##########################################################################
# Form: OWFS
##########################################################################

sub form_vzlogger
{
	my $config_file = "$lbpconfigdir/smartmeter.json";
	$plugin_cfg = SmartMeterConfig->new($config_file) or die "Could not read $config_file";

	my @heads = detect_heads();
	{
		# Initial defaulting and one-time channel migration may write configuration.
		my ($initialization_lock, $lock_error) = acquire_config_lock("/var/run/shm/$lbpplugindir");
		die "$lock_error\n" if (!$initialization_lock);
		ensure_vzlogger_defaults();
		ensure_head_defaults(@heads);
		load_or_migrate_channel_document(@heads);
	}

	if ($q->{saveformdata}) {
		my ($form_lock, $lock_error) = acquire_config_lock("/var/run/shm/$lbpplugindir");
		die "$lock_error\n" if (!$form_lock);
		local $ENV{SMARTMETER_CONFIG_LOCK_HELD} = "1";
		my $action = $q->{submitaction} || "apply";
		if (expert_mode_enabled()) {
			my $status = expert_draft_status();
			if ($action eq "validate") {
				$template->param("VZLOGGER_MESSAGE", $status->{message});
			} else {
				my $output = save_expert_allowed_form();
				$status = promote_expert_configuration();
				$output .= $status->{message};
				$output .= run_control("apply-expert") if ($status->{valid});
				$template->param("VZLOGGER_MESSAGE", $output);
			}
		} elsif ($action eq "validate") {
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
		my $replace_expert_runtime = !expert_mode_enabled() && expert_configuration_applied();
		my $save_output = "";
		if ($action =~ /\A(?:start|stop|restart)-vzlogger\z/) {
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
		$control_action = "read-obis" if ($action eq "read-obis");
		my $output = $save_output;
		if ($action eq "read-obis") {
			$output .= read_obis_channels($q->{obis_serial}, @heads);
		} else {
			my $activating_vzlogger = $control_action eq "apply" &&
				$implementation_before_save ne "vzlogger" && implementation_mode() eq "vzlogger";
			$output .= ($control_action eq "apply") ? apply_selected_implementation($activating_vzlogger, $implementation_before_save, $replace_expert_runtime) : run_control($control_action);
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
		$plugin_cfg = SmartMeterConfig->new($config_file) or die "Could not reload $config_file";
		@heads = detect_heads();
		load_or_migrate_channel_document(@heads);
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
	$template->param("MQTTTOPIC" => $mqtttopic);
	$template->param("VZLOGGER_LOCALENABLED" => $local_enabled);
	$template->param("VZLOGGER_LOCALPORT" => $local_port);
	$template->param("VZLOGGER_LOCALINDEX" => $local_index);
	$template->param("VZLOGGER_LOCALTIMEOUT" => $local_timeout);
	$template->param("VZLOGGER_LOCALBUFFER" => $local_buffer);
	$template->param("VZLOGGER_RETRY" => $retry);
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
	my $expert_mode = expert_mode_enabled();
	$template->param("VZLOGGER_EXPERT_MODE" => $expert_mode);
	$template->param("VZLOGGER_EXPERT_MODE_VALUE" => $expert_mode ? 1 : 0);
	$template->param("VZLOGGER_EXPERT_SOURCE_PRESENT" => -e expert_config_file() ? 1 : 0);
	$template->param("VZLOGGER_EXPERT_APPLIED" => expert_configuration_applied() ? 1 : 0);
	add_service_template_params();
	$template->param("VZLOGGER_CONFIG" => "$lbpconfigdir/vzlogger.conf");
	my $ui_language = $L{'COMMON.LANGUAGE_CODE'} || "en";
	$template->param("VZLOGGER_CONFIG_URL" => "./vzlogger_config.cgi?lang=$ui_language");
	my $visible_config_exists = $expert_mode ? -e expert_config_file() : -e "$lbpconfigdir/vzlogger.conf";
	$template->param("VZLOGGER_CONFIG_DISABLED" => ($visible_config_exists ? "" : "ui-disabled"));
	my $runtime_config = read_json("$lbpconfigdir/vzlogger.conf") || {};
	$template->param("EXPERT_MQTT_ENABLED" => (ref($runtime_config->{mqtt}) eq "HASH" && $runtime_config->{mqtt}->{enabled}) ? 1 : 0);
	$template->param("VZLOGGER_LIVEURL" => "http://$ENV{HTTP_HOST}:$local_port/");
	$template->param("VZLOGGER_RENDERED_URL" => "./vzlogger_live.cgi?lang=$ui_language");
	$template->param("METER_TEMPLATES_JSON" => JSON::PP->new->utf8->canonical->encode(load_meter_templates()));
	$template->param("CHANNEL_DEFINITIONS_JSON" => JSON::PP->new->utf8->canonical->encode($channel_document || new_document()));
	$template->param("CHANNEL_INDICES_JSON" => JSON::PP->new->utf8->canonical->encode(runtime_channel_indices()));
	$template->param("OBIS_CATALOG_JSON" => JSON::PP->new->utf8->canonical->encode($obis_catalog || load_catalog("$lbptemplatedir/obis_catalog.json")));
	$template->param("ROWS" => \@rows);
	return();
}

sub add_service_template_params
{
	my $vzlogger_expected_active = implementation_mode() eq "vzlogger";
	my $vzlogger_state = service_state("vzlogger");

	$template->param("VZLOGGER_SERVICE_STATUS" => service_summary("vzlogger"));
	$template->param("VZLOGGER_SERVICE_STATUS_CLASS" => service_status_class($vzlogger_state, $vzlogger_expected_active));
	$template->param("VZLOGGER_SERVICE_RUNNING" => $vzlogger_state eq "active");
	$template->param("VZLOGGER_LIVE_DISABLED" => ($vzlogger_state eq "active" ? "" : "ui-disabled"));

	# vzLogger writes its own log at a fixed path (configured in vzlogger.conf).
	# The control log is a LoxBerry session with a timestamped name, so its button
	# links to the most recent file; both also appear in the LoxBerry log manager.
	my $vzlogger_log = "$lbhomedir/log/plugins/$lbpplugindir/vzlogger.log";
	$template->param("VZLOGGER_LOG_URL" => log_url("plugins/$lbpplugindir/vzlogger.log"));
	$template->param("VZLOGGER_LOG_DISABLED" => (-e $vzlogger_log ? "" : "ui-disabled"));

	my $control_log = latest_plugin_log_name("control");
	$template->param("CONTROL_LOG_URL" => $control_log ? log_url("plugins/$lbpplugindir/$control_log") : "#");
	$template->param("CONTROL_LOG_DISABLED" => ($control_log ? "" : "ui-disabled"));
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

# Returns the basename of the newest LoxBerry log file for a base name
# (e.g. "control"), or undef. The high-resolution timestamp prefix
# sorts chronologically, so the last entry is the most recent.
sub latest_plugin_log_name
{
	my ($name) = @_;
	my @files = sort glob("$lbhomedir/log/plugins/$lbpplugindir/*_$name.log");
	return undef if (!@files);
	my ($base) = $files[-1] =~ m{([^/]+)\z};
	return $base;
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
	my $installed = service_installed($service) ? $L{'VZLOGGER.UI_INSTALLED'} : $L{'VZLOGGER.UI_NOT_INSTALLED'};
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
	my $config_file = "$lbpconfigdir/smartmeter.json";
	$plugin_cfg = SmartMeterConfig->new($config_file) or die "Could not read $config_file";
}

sub service_status_response
{
	my $vzlogger_expected = implementation_mode() eq "vzlogger";
	my $mqtt_enabled = effective_vzlogger_mqtt_enabled();
	my $config = generated_config_status();
	my $expert = expert_draft_status();
	my $expert_applied = expert_configuration_applied();
	$config->{expert_mode} = expert_mode_enabled() ? JSON::PP::true : JSON::PP::false;
	$config->{expert_present} = $expert->{present} ? JSON::PP::true : JSON::PP::false;
	$config->{expert_valid} = $expert->{valid} ? JSON::PP::true : JSON::PP::false;
	$config->{expert_message} = $expert->{message};
	$config->{expert_applied} = $expert_applied ? JSON::PP::true : JSON::PP::false;
	my $vzlogger_startable = $config->{valid};
	$vzlogger_startable = 0 if (expert_mode_enabled() && (!$expert->{valid} || !$expert_applied));
	return {
		ok => JSON::PP::true,
		applied => {
			vzlogger_enabled => $vzlogger_expected ? JSON::PP::true : JSON::PP::false,
			mqtt_enabled => $mqtt_enabled ? JSON::PP::true : JSON::PP::false,
		},
		config => {
			present => $config->{present} ? JSON::PP::true : JSON::PP::false,
			valid => $config->{valid} ? JSON::PP::true : JSON::PP::false,
			mqtt_enabled => $config->{mqtt_enabled} ? JSON::PP::true : JSON::PP::false,
			expert_mode => $config->{expert_mode},
			expert_present => $config->{expert_present},
			expert_valid => $config->{expert_valid},
			expert_message => $config->{expert_message},
			expert_applied => $config->{expert_applied},
		},
		services => {
			vzlogger => service_status_data("vzlogger", $vzlogger_expected, $vzlogger_startable),
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
		status_text => "$state | PID: " . ($pid || "-") . " | Service: $service | " . ($installed ? $L{'VZLOGGER.UI_INSTALLED'} : $L{'VZLOGGER.UI_NOT_INSTALLED'}),
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
	);
	die $L{'VZLOGGER.UI_UNKNOWN_SERVICE_ACTION'} if (!$allowed{$action || ""});
	my $starting = $action =~ /\A(?:start|restart)-/;
	die $L{'VZLOGGER.UI_SAVE_VZLOGGER_FIRST'} if ($starting && implementation_mode() ne "vzlogger");
	my $requested_implementation = clean_config_value($q->{implementation}, qr/\A(?:none|vzlogger)\z/, "");
	my $config = generated_config_status();
	my $expert = expert_draft_status();
	die $L{'VZLOGGER.UI_EXPERT_INVALID_START'}
		if ($starting && expert_mode_enabled() && !$expert->{valid});
	die $L{'VZLOGGER.UI_EXPERT_NOT_APPLIED'}
		if ($starting && expert_mode_enabled() && !expert_configuration_applied());
	die $L{'VZLOGGER.UI_ENABLE_VZLOGGER'} if ($starting && $requested_implementation ne "vzlogger");
	die $L{'VZLOGGER.UI_GENERATED_CONFIG_INVALID'} if ($starting && !$config->{valid});
	# MQTT is the only transport, so starting without it would produce no output.
	die $L{'VZLOGGER.UI_ENABLE_MQTT'} if ($starting && !effective_vzlogger_mqtt_enabled());
	die $L{'VZLOGGER.UI_MQTT_DISABLED_CONFIG'} if ($starting && !$config->{mqtt_enabled});

	save_service_log_settings($action);

	my ($output, $exit) = run_control_result($action);
	my $response = service_status_response();
	my $service_name = "vzlogger";
	my $expected_running = $action =~ /\A(?:start|restart)-/ ? 1 : 0;
	my $running = $response->{services}->{$service_name}->{running} ? 1 : 0;
	if ($exit == 0 && $running != $expected_running) {
		$exit = 1;
		$output .= "\n" . $L{'VZLOGGER.UI_FINAL_STATE_FAILED'} . "\n";
		write_control_log("$action-state-check", "Requested running=$expected_running, observed running=$running.\n");
	}
	my $warning = $output =~ /\bwarning\b/i ? 1 : 0;
	my $failure_output = $output;
	$failure_output =~ s/^Warning:.*(?:\n|\z)//img;
	$exit = 1 if ($exit == 0 && $failure_output =~ /(?:\bcould not\b|\bnot available\b|\bnot installed\b|\broot privileges are required\b|\bskipped\b)/i);
	$response->{ok} = $exit == 0 ? JSON::PP::true : JSON::PP::false;
	$response->{warning} = $warning ? JSON::PP::true : JSON::PP::false;
	$response->{message} = $output;
	return $response;
}

sub run_form_ajax_action
{
	my ($action) = @_;
	my %allowed = map { $_ => 1 } qw(validate apply);
	die $L{'VZLOGGER.UI_UNKNOWN_CONFIG_ACTION'} if (!$allowed{$action || ""});
	die $L{'VZLOGGER.UI_TIMEOUT_COMMAND_MISSING'} if (!command_exists("timeout"));
	local $configuration_action_deadline = time + 60;
	local $configuration_action_timed_out = 0;
	load_service_ajax_config();
	ensure_vzlogger_defaults();
	if (expert_mode_enabled()) {
		my $status = expert_draft_status();
		if ($action eq "validate") {
			return {
				ok => $status->{valid} ? JSON::PP::true : JSON::PP::false,
				action => "validate",
				message => $status->{message},
			};
		}
		my $output = save_expert_allowed_form();
		$status = promote_expert_configuration();
		$output .= $status->{message};
		my $exit = 1;
		if ($status->{valid}) {
			my ($apply_output, $apply_exit) = run_control_result("apply-expert");
			$output .= $apply_output;
			$exit = $apply_exit;
		}
		load_service_ajax_config();
		my $response = service_status_response();
		$response->{ok} = ($status->{valid} && $exit == 0) ? JSON::PP::true : JSON::PP::false;
		$response->{action} = "apply";
		$response->{message} = $output;
		$response->{config_url} = "./vzlogger_config.cgi?lang=" . ($L{'COMMON.LANGUAGE_CODE'} || "en");
		$response->{channel_indices} = runtime_channel_indices();
		write_apply_log($output, \$output);
		return $response;
	}
	return run_draft_validation_ajax() if ($action eq "validate");

	my @heads = detect_heads();
	ensure_head_defaults(@heads);
	my $implementation_before_save = implementation_mode();
	my $replace_expert_runtime = !expert_mode_enabled() && expert_configuration_applied();
	my $output = save_vzlogger_form(@heads);
	my $exit = 0;

	my $activating_vzlogger = $implementation_before_save ne "vzlogger" && implementation_mode() eq "vzlogger";
	my ($apply_output, $apply_exit) = apply_selected_implementation_result($activating_vzlogger, $implementation_before_save, $replace_expert_runtime);
	$output .= $apply_output;
	$exit = $apply_exit;
	# Reload persisted values before producing the service snapshot.
	load_service_ajax_config();
	my $response = service_status_response();
	my $operation_ok = $exit == 0;
	$operation_ok = 0 if ($output =~ /(?:\ACould not|\nCould not|\bnot available\b)/i);
	my $meterless = $output =~ /No meter is configured/i;
	my $vzlogger_expected = $response->{applied}->{vzlogger_enabled} && !$meterless;
	if ($vzlogger_expected && !$response->{services}->{vzlogger}->{running}) {
		$operation_ok = 0;
		$output .= "\n" . $L{'VZLOGGER.UI_APPLY_VZLOGGER_NOT_RUNNING'} . "\n";
	}
	if (!$vzlogger_expected && $response->{services}->{vzlogger}->{running}) {
		$operation_ok = 0;
		$output .= "\n" . $L{'VZLOGGER.UI_APPLY_VZLOGGER_NOT_STOPPED'} . "\n";
	}
	write_apply_log($output, \$output);
	$response->{ok} = $operation_ok ? JSON::PP::true : JSON::PP::false;
	$response->{action} = $action;
	$response->{message} = $output;
	$response->{timed_out} = $configuration_action_timed_out ? JSON::PP::true : JSON::PP::false;
	$response->{config_url} = "./vzlogger_config.cgi?lang=" . ($L{'COMMON.LANGUAGE_CODE'} || "en");
	$response->{channel_indices} = runtime_channel_indices();
	return $response;
}

sub run_draft_validation_ajax
{
	my $live_config_dir = $lbpconfigdir;
	my $draft_dir = tempdir("smartmeter-vzlogger-validation-XXXXXX", TMPDIR => 1, CLEANUP => 1);
	my $draft_config = "$draft_dir/smartmeter.json";
	copy("$live_config_dir/smartmeter.json", $draft_config) or die ui_text($L{'VZLOGGER.UI_DRAFT_PREPARE_FAILED'}, error => $!);
	foreach my $source (glob("$live_config_dir/vzlogger_meter_*.jsonc")) {
		my ($name) = $source =~ m{([^/\\]+)\z};
		copy($source, "$draft_dir/$name") or die ui_text($L{'VZLOGGER.UI_DRAFT_CUSTOM_PREPARE_FAILED'}, error => $!);
	}

	my ($output, $exit);
	{
		local $lbpconfigdir = $draft_dir;
		$plugin_cfg = SmartMeterConfig->new($draft_config) or die $L{'VZLOGGER.UI_DRAFT_READ_FAILED'};
		ensure_vzlogger_defaults();
		my @heads = detect_heads();
		ensure_head_defaults(@heads);
		save_vzlogger_form("__draft__", @heads);
		my $draft_channels = submitted_channel_document(@heads);
		write_json_atomic("$draft_dir/vzlogger_channel_definitions.json", $draft_channels) if ($draft_channels);
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
		local $ENV{SMARTMETER_VZLOGGER_DEFINITIONS_FILE} = "$draft_dir/vzlogger_channel_definitions.json";
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
		timed_out => $configuration_action_timed_out ? JSON::PP::true : JSON::PP::false,
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
		message => $L{'VZLOGGER.UI_DEBUG_TIMEOUT_COMMAND_MISSING'},
	} if (!command_exists("timeout"));
	$output = `timeout --signal=TERM --kill-after=5 45 "$^X" "$script" debug-log 2>&1`;
	$exit = $? >> 8;
	$output .= "\n" . $L{'VZLOGGER.UI_DEBUG_TIMEOUT'} . "\n" if ($exit == 124 || $exit == 137);
	$output ||= $L{'VZLOGGER.UI_NO_OUTPUT'};
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
	my $remaining = defined($configuration_action_deadline) ? int($configuration_action_deadline - time) : 60;
	if ($remaining <= 0) {
		$configuration_action_timed_out = 1;
		return ($L{'VZLOGGER.UI_CONFIG_TIMEOUT'} . "\n", 124);
	}
	my $argument_text = join(" ", map { my $value = $_; $value =~ s/"/\\"/g; qq{"$value"} } @arguments);
	my $output = `timeout --signal=TERM --kill-after=5s ${remaining}s "$^X" "$script" $argument_text 2>&1`;
	my $exit = $? >> 8;
	if ($exit == 124 || $exit == 137) {
		$configuration_action_timed_out = 1;
		$output .= "\n" . $L{'VZLOGGER.UI_CONFIG_TIMEOUT'} . "\n";
	}
	$output ||= $L{'VZLOGGER.UI_NO_OUTPUT'};
	return ($output, $exit);
}

sub save_service_log_settings
{
	my ($action) = @_;
	my $starting = $action =~ /\A(?:start|restart)-/;
	if ($action =~ /-vzlogger\z/) {
		die $L{'VZLOGGER.UI_INVALID_DEBUG_SETTING'} if (!defined($q->{vzlogger_service_debug}) || $q->{vzlogger_service_debug} !~ /\A[01]\z/);
		die $L{'VZLOGGER.UI_INVALID_LOG_LEVEL'} if (!defined($q->{vzlogger_loglevel}) || $q->{vzlogger_loglevel} !~ /\A(?:0|1|3|5|10|15)\z/);
		if ($starting) {
			die $L{'VZLOGGER.UI_INVALID_ACTIVATION'} if (!defined($q->{implementation}) || $q->{implementation} ne "vzlogger");
		}
		$plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG", $q->{vzlogger_service_debug});
		$plugin_cfg->param("VZLOGGER.LOGLEVEL", $q->{vzlogger_loglevel});
	} else {
		if ($starting) {
			die $L{'VZLOGGER.UI_INVALID_ACTIVATION'} if (!defined($q->{implementation}) || $q->{implementation} ne "vzlogger");
		}
	}
	$plugin_cfg->save;
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
	return $status if (!-e $validator || ref($config->{meters}) ne "ARRAY" || !@{$config->{meters}});
	return $status if (!expert_mode_enabled() && !-e $mapping_file);
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
		my $language = $L{'COMMON.LANGUAGE_CODE'} || "en";
		$entry->{label} = $entry->{"label_$language"} || $entry->{label_en} || $entry->{label};
	}
	$meter_templates_cache = $templates;
	return $meter_templates_cache;
}

sub ensure_vzlogger_defaults
{
	my $changed = 0;
	my $set_default = sub {
		my ($key, $value, $empty_is_missing) = @_;
		my $current = $plugin_cfg->param($key);
		return if (defined($current) && (!$empty_is_missing || $current ne ""));
		$plugin_cfg->param($key, $value);
		$changed = 1;
	};
	$set_default->("MAIN.IMPLEMENTATION", implementation_mode(), 1);
	$set_default->("MAIN.MQTTTOPIC", "smartmeter", 1);
	foreach my $entry (
		["VZLOGGER.EXPERTMODE", "0"], ["VZLOGGER.RETRY", "30"], ["VZLOGGER.LOCALENABLED", "1"],
		["VZLOGGER.LOCALINDEX", "1"], ["VZLOGGER.LOCALTIMEOUT", "30"], ["VZLOGGER.LOCALBUFFER", "-1"],
		["VZLOGGER.VZLOGGERDEBUG", "0"],
		["VZLOGGER.LOGLEVEL", "0"], ["VZLOGGER.MQTTENABLED", "1"], ["VZLOGGER.MQTTHOST", ""],
		["VZLOGGER.MQTTPORT", ""], ["VZLOGGER.MQTTCAFILE", ""], ["VZLOGGER.MQTTCAPATH", ""],
		["VZLOGGER.MQTTCERTFILE", ""], ["VZLOGGER.MQTTKEYFILE", ""], ["VZLOGGER.MQTTKEYPASS", ""],
		["VZLOGGER.MQTTKEEPALIVE", "30"], ["VZLOGGER.MQTTID", ""], ["VZLOGGER.MQTTUSER", ""],
		["VZLOGGER.MQTTPASS", ""], ["VZLOGGER.MQTTRETAIN", "1"], ["VZLOGGER.MQTTRAWANDAGG", "0"],
		["VZLOGGER.MQTTQOS", "0"], ["VZLOGGER.MQTTTIMESTAMP", "1"], ["VZLOGGER.REMOVEDHEADS", ""],
	) {
		$set_default->($entry->[0], $entry->[1], 0);
	}
	$set_default->("VZLOGGER.LOCALPORT", "18080", 1);
	$plugin_cfg->save if ($changed);
}

sub expert_mode_enabled
{
	return $plugin_cfg && ($plugin_cfg->param("VZLOGGER.EXPERTMODE") || "0") eq "1" ? 1 : 0;
}

sub effective_vzlogger_mqtt_enabled
{
	if (expert_mode_enabled()) {
		my $config = read_json("$lbpconfigdir/vzlogger.conf");
		return (ref($config) eq "HASH" && ref($config->{mqtt}) eq "HASH" && $config->{mqtt}->{enabled}) ? 1 : 0;
	}
	return clean_boolean($plugin_cfg->param("VZLOGGER.MQTTENABLED"), 1);
}

sub expert_config_file
{
	return "$lbpconfigdir/vzlogger_expert.conf";
}

sub expert_draft_status
{
	my $text = read_text(expert_config_file());
	my $result = validate_expert_text($text);
	return {
		present => defined($text) ? 1 : 0,
		valid => $result->{valid} ? 1 : 0,
		message => format_expert_validation(localize_expert_validation($result, \%L)),
		result => $result,
	};
}

sub set_expert_mode_ajax
{
	my ($enabled) = @_;
	die $L{'VZLOGGER.UI_INVALID_EXPERT_MODE'} if (!defined($enabled) || $enabled !~ /\A[01]\z/);
	my $was_enabled = expert_mode_enabled();
	if ($enabled eq "1" && !$was_enabled && !-e expert_config_file()) {
		my $runtime_file = "$lbpconfigdir/vzlogger.conf";
		my $runtime = read_text($runtime_file);
		die $L{'VZLOGGER.UI_EXPERT_REQUIRES_CONFIG'} if (!defined($runtime));
		die $L{'VZLOGGER.UI_EXPERT_TOO_LARGE'} if (length($runtime) > 1024 * 1024);
		die $L{'VZLOGGER.UI_EXPERT_INIT_FAILED'} if (!write_text_atomic(expert_config_file(), $runtime));
	}
	$plugin_cfg->param("VZLOGGER.EXPERTMODE", $enabled);
	$plugin_cfg->save;
	my $status = expert_draft_status();
	my $expert_config = $status->{result}->{config};
	my $mqtt_enabled = ref($expert_config) eq "HASH" &&
		ref($expert_config->{mqtt}) eq "HASH" && $expert_config->{mqtt}->{enabled};
	return {
		ok => JSON::PP::true,
		expert_mode => $enabled eq "1" ? JSON::PP::true : JSON::PP::false,
		expert_valid => $status->{valid} ? JSON::PP::true : JSON::PP::false,
		expert_applied => expert_configuration_applied() ? JSON::PP::true : JSON::PP::false,
		mqtt_enabled => $mqtt_enabled ? JSON::PP::true : JSON::PP::false,
		validation_message => $status->{message},
		message => $enabled eq "1" ? $L{'VZLOGGER.UI_EXPERT_ENABLED'} : $L{'VZLOGGER.UI_EXPERT_DISABLED'},
	};
}

sub reset_expert_configuration_ajax
{
	die $L{'VZLOGGER.UI_EXPERT_INACTIVE'} if (!expert_mode_enabled());
	my $runtime_file = "$lbpconfigdir/vzlogger.conf";
	my $runtime = read_text($runtime_file);
	die $L{'VZLOGGER.UI_RUNTIME_CONFIG_MISSING'} if (!defined($runtime));
	die $L{'VZLOGGER.UI_EXPERT_TOO_LARGE'} if (length($runtime) > 1024 * 1024);
	die $L{'VZLOGGER.UI_EXPERT_RESET_FAILED'} if (!write_text_atomic(expert_config_file(), $runtime));
	my $status = expert_draft_status();
	my $expert_config = $status->{result}->{config};
	my $mqtt_enabled = ref($expert_config) eq "HASH" &&
		ref($expert_config->{mqtt}) eq "HASH" && $expert_config->{mqtt}->{enabled};
	return {
		ok => JSON::PP::true,
		expert_mode => JSON::PP::true,
		expert_valid => $status->{valid} ? JSON::PP::true : JSON::PP::false,
		expert_applied => expert_configuration_applied() ? JSON::PP::true : JSON::PP::false,
		mqtt_enabled => $mqtt_enabled ? JSON::PP::true : JSON::PP::false,
		validation_message => $status->{message},
		message => $L{'VZLOGGER.UI_EXPERT_RESET_DONE'},
	};
}

sub expert_configuration_applied
{
	return expert_configs_equal(
		read_text(expert_config_file()),
		read_text("$lbpconfigdir/vzlogger.conf"),
	);
}

sub promote_expert_configuration
{
	my $status = expert_draft_status();
	return $status if (!$status->{valid});
	my $text = read_text(expert_config_file());
	my $mapping_file = "$lbpconfigdir/vzlogger_channels.json";
	my $existing = read_json($mapping_file) || {};
	my ($mapping, $mapping_warnings) = build_expert_mapping($status->{result}->{config}, $existing);
	push @{$status->{result}->{warnings}}, @$mapping_warnings;
	$status->{message} = format_expert_validation(localize_expert_validation($status->{result}, \%L));
	my $runtime_file = "$lbpconfigdir/vzlogger.conf";
	my $stage = tempdir(".vzlogger-expert-stage-XXXXXX", DIR => $lbpconfigdir, CLEANUP => 1);
	my $stage_runtime = "$stage/vzlogger.conf";
	my $stage_mapping = "$stage/vzlogger_channels.json";
	my $runtime_ok = write_text_atomic($stage_runtime, $text);
	my $mapping_ok = $runtime_ok ? eval { write_json_atomic($stage_mapping, $mapping); 1 } : 0;
	my ($promoted, $promotion_error) = $mapping_ok
		? promote_files_atomic([[$stage_runtime, $runtime_file, 0600], [$stage_mapping, $mapping_file, 0600]])
		: (0, "Could not stage expert mapping.");
	if (!$runtime_ok || !$mapping_ok || !$promoted) {
		$status->{valid} = 0;
		$status->{message} .= "<FAIL> " . ui_text($L{'VZLOGGER.UI_EXPERT_PROMOTE_FAILED'}, error => $promotion_error) . "\n";
	}
	return $status;
}

sub save_expert_allowed_form
{
	my $implementation = implementation_mode();
	if (($q->{implementation_changed} || "") eq "1") {
		$implementation = clean_config_value($q->{implementation}, qr/\A(?:none|vzlogger)\z/, $implementation);
	}
	set_implementation_mode($plugin_cfg, $implementation);
	$plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG", clean_config_value($q->{vzlogger_service_debug}, qr/\A[01]\z/, $plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG") || "0"));
	$plugin_cfg->param("VZLOGGER.LOGLEVEL", clean_log_level($q->{vzlogger_loglevel}, $plugin_cfg->param("VZLOGGER.LOGLEVEL") || "0"));
	$plugin_cfg->save;

	my $text = read_text(expert_config_file());
	my $debug = ($plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG") || "0") eq "1";
	my $level = clean_log_level($plugin_cfg->param("VZLOGGER.LOGLEVEL"), "0");
	my ($updated, $result) = update_expert_log_settings(
		$text,
		$debug ? $level : 0,
		$debug ? "$lbhomedir/log/plugins/$lbpplugindir/vzlogger.log" : "/dev/null",
	);
	return format_expert_validation(localize_expert_validation($result, \%L)) . $L{'VZLOGGER.UI_EXPERT_LOG_UPDATE_FAILED'} . "\n" if (!defined($updated));
	return $L{'VZLOGGER.UI_EXPERT_LOG_SAVE_FAILED'} . "\n" if (!write_text_atomic(expert_config_file(), $updated));
	return "Updated Expert Mode service settings.\n";
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
	SmartMeterConfig->import_from("$lbpconfigdir/smartmeter.json", \%config);
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
	my $changed = 0;
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
		$changed = 1;
	}
	$plugin_cfg->save if ($changed);
}

sub save_vzlogger_form
{
	my $draft_only = (@_ && $_[0] eq "__draft__") ? shift : "";
	my (@heads) = @_;
	validate_submitted_vzlogger_form(@heads);
	my $submitted_channels = submitted_channel_document(@heads);
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
	set_implementation_mode($plugin_cfg, $implementation);
	# Disabled form controls are not submitted. Preserve their saved values while
	# meter reading is off instead of silently restoring defaults.
	$plugin_cfg->param("MAIN.MQTTTOPIC", clean_config_value($q->{mqtttopic}, qr/\A[^#+]+\z/, $plugin_cfg->param("MAIN.MQTTTOPIC") || "smartmeter"));
	$plugin_cfg->param("VZLOGGER.RETRY", clean_config_value($q->{vzlogger_retry}, qr/\A\d+\z/, defined($plugin_cfg->param("VZLOGGER.RETRY")) ? $plugin_cfg->param("VZLOGGER.RETRY") : "30"));
	$plugin_cfg->param("VZLOGGER.LOCALENABLED", clean_config_value($q->{vzlogger_localenabled}, qr/\A[01]\z/, defined($plugin_cfg->param("VZLOGGER.LOCALENABLED")) ? $plugin_cfg->param("VZLOGGER.LOCALENABLED") : "1"));
	$plugin_cfg->param("VZLOGGER.LOCALPORT", clean_config_value($q->{vzlogger_localport}, qr/\A\d+\z/, $plugin_cfg->param("VZLOGGER.LOCALPORT") || "18080"));
	$plugin_cfg->param("VZLOGGER.LOCALINDEX", clean_config_value($q->{vzlogger_localindex}, qr/\A[01]\z/, defined($plugin_cfg->param("VZLOGGER.LOCALINDEX")) ? $plugin_cfg->param("VZLOGGER.LOCALINDEX") : "1"));
	$plugin_cfg->param("VZLOGGER.LOCALTIMEOUT", clean_config_value($q->{vzlogger_localtimeout}, qr/\A\d+\z/, defined($plugin_cfg->param("VZLOGGER.LOCALTIMEOUT")) ? $plugin_cfg->param("VZLOGGER.LOCALTIMEOUT") : "30"));
	$plugin_cfg->param("VZLOGGER.LOCALBUFFER", clean_config_value($q->{vzlogger_localbuffer}, qr/\A-?\d+\z/, defined($plugin_cfg->param("VZLOGGER.LOCALBUFFER")) ? $plugin_cfg->param("VZLOGGER.LOCALBUFFER") : "-1"));
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
		unlink(pending_obis_channels_file($serial)) if (!$draft_only && ($q->{submitaction} || "") eq "apply" && -e pending_obis_channels_file($serial));
		unlink(pending_meter_draft_file($serial)) if (!$draft_only && ($q->{submitaction} || "") eq "apply" && -e pending_meter_draft_file($serial));
	}
	my @removed_serials = sort keys %remove_serials;
	if (@removed_serials) {
		my %removed_heads = map { $_ => 1 } config_list_values("VZLOGGER.REMOVEDHEADS");
		foreach my $serial (@removed_serials) {
			foreach my $key ($plugin_cfg->param()) {
				next if ($key =~ /\A\Q$serial\E\.(?:NAME|SERIAL|DEVICE)\z/);
				$plugin_cfg->delete($key) if ($key =~ /\A\Q$serial\E\./);
			}
			$removed_heads{$serial} = 1;
		}
		$plugin_cfg->param("VZLOGGER.REMOVEDHEADS", join(",", sort keys %removed_heads));
	}
	$plugin_cfg->save if (!$draft_only);
	if ($submitted_channels && !$draft_only) {
		$channel_document = $submitted_channels;
		write_json_atomic("$lbpconfigdir/vzlogger_channel_definitions.json", $channel_document);
	}
	my $cleanup_output = "";
	foreach my $serial ($draft_only ? () : @removed_serials) {
		$cleanup_output .= remove_meter_artifacts($serial);
	}
	return $cleanup_output;
}

sub validate_submitted_vzlogger_form
{
	my (@heads) = @_;
	my @errors;
	my %integer_fields = (
		vzlogger_retry => [0, undef], vzlogger_localport => [1, 65535],
		vzlogger_localtimeout => [0, undef], vzlogger_localbuffer => [undef, undef],
		vzlogger_mqttport => [1, 65535], vzlogger_mqttkeepalive => [0, undef],
	);
	foreach my $field (sort keys %integer_fields) {
		next if (!defined($q->{$field}) || ($field eq "vzlogger_mqttport" && $q->{$field} eq ""));
		my ($minimum, $maximum) = @{$integer_fields{$field}};
		push @errors, "$field must be an integer" if ($q->{$field} !~ /\A-?\d+\z/);
		next if ($q->{$field} !~ /\A-?\d+\z/);
		push @errors, "$field must be at least $minimum" if (defined($minimum) && $q->{$field} < $minimum);
		push @errors, "$field must not exceed $maximum" if (defined($maximum) && $q->{$field} > $maximum);
	}
	foreach my $field (qw(read vzlogger_localenabled vzlogger_localindex vzlogger_debug vzlogger_service_debug vzlogger_mqttenabled vzlogger_mqttretain vzlogger_mqttrawandagg vzlogger_mqtttimestamp)) {
		push @errors, "$field must be 0 or 1" if (defined($q->{$field}) && $q->{$field} !~ /\A[01]\z/);
	}
	push @errors, "vzlogger_mqttqos must be 0 or 1" if (defined($q->{vzlogger_mqttqos}) && $q->{vzlogger_mqttqos} !~ /\A[01]\z/);
	push @errors, "vzlogger_loglevel must be 0, 1, 3, 5, 10 or 15"
		if (defined($q->{vzlogger_loglevel}) && $q->{vzlogger_loglevel} !~ /\A(?:0|1|3|5|10|15)\z/);
	if (defined($q->{mqtttopic})) {
		push @errors, "mqtttopic must not be empty" if ($q->{mqtttopic} eq "");
		push @errors, "mqtttopic must not start with \$" if ($q->{mqtttopic} =~ /\A\$/);
		push @errors, "mqtttopic must not end with /" if ($q->{mqtttopic} =~ m{/\z});
		push @errors, "mqtttopic must not contain + or #" if ($q->{mqtttopic} =~ /[+#]/);
	}

	foreach my $device (@heads) {
		my $serial = $device;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		my $mode = defined($q->{"$serial\_meter"}) ? $q->{"$serial\_meter"} :
			normalized_meter_mode($plugin_cfg->param("$serial.METER"), $plugin_cfg->param("$serial.PROTOCOL"));
		push @errors, "$serial: invalid meter protocol selection" if ($mode !~ /\A(?:0|sml|d0|oms|user)\z/);
		next if ($mode !~ /\A(?:sml|d0|oms)\z/);
		my $enabled = defined($q->{"$serial\_enabled"}) ? $q->{"$serial\_enabled"} : clean_boolean(config_scalar_value("$serial.ENABLED"), 1);
		push @errors, "$serial: enabled must be 0 or 1" if ($enabled !~ /\A[01]\z/);
		next if ($enabled ne "1");
		foreach my $field (qw(allowskip uselocaltime)) {
			my $name = "$serial\_$field";
			push @errors, "$serial: $field must be 0 or 1" if (defined($q->{$name}) && $q->{$name} !~ /\A[01]\z/);
		}
		foreach my $field (qw(aggtime interval)) {
			my $name = "$serial\_$field";
			next if (!defined($q->{$name}) || $q->{$name} eq "");
			push @errors, "$serial: $field must be -1 or a non-negative integer"
				if ($q->{$name} !~ /\A(?:-1|\d+)\z/);
		}
		my $aggtime = $q->{"$serial\_aggtime"};
		my $interval = $q->{"$serial\_interval"};
		if (defined($aggtime) && defined($interval) && $aggtime =~ /\A\d+\z/ && $interval =~ /\A\d+\z/ && $aggtime > 0 && $interval > 0 && $aggtime < $interval) {
			push @errors, "$serial: aggtime ($aggtime) must not be shorter than interval ($interval)";
		}
		my $pullseq = $q->{"$serial\_pullseq"};
		push @errors, "$serial: pullseq must be empty or an even-length hexadecimal sequence"
			if (defined($pullseq) && $pullseq ne "" && ($pullseq !~ /\A[0-9a-f]+\z/i || length($pullseq) % 2));
		my $baudrate = $q->{"$serial\_baudrate"};
		push @errors, "$serial: baudrate must be between 1 and 4000000"
			if (defined($baudrate) && $baudrate ne "" && ($baudrate !~ /\A\d+\z/ || $baudrate < 1 || $baudrate > 4000000));
		my $parity = $q->{"$serial\_paritymode"};
		push @errors, "$serial: parity must be 8n1, 7e1, 7o1 or 7n1"
			if (defined($parity) && $parity ne "" && $parity !~ /\A(?:8n1|7e1|7o1|7n1)\z/i);
		if ($mode eq "d0") {
			my $ackseq = $q->{"$serial\_ackseq"};
			push @errors, "$serial: ackseq must be empty, auto or an even-length hexadecimal sequence"
				if (defined($ackseq) && $ackseq ne "" && lc($ackseq) ne "auto" && ($ackseq !~ /\A[0-9a-f]+\z/i || length($ackseq) % 2));
			my $baudrate_read = $q->{"$serial\_baudrateread"};
			push @errors, "$serial: baudrate_read must be between 1 and 4000000"
				if (defined($baudrate_read) && $baudrate_read ne "" && ($baudrate_read !~ /\A\d+\z/ || $baudrate_read < 1 || $baudrate_read > 4000000));
			my $wait_sync = $q->{"$serial\_waitsync"};
			push @errors, "$serial: wait_sync must be off or end" if (defined($wait_sync) && $wait_sync ne "" && $wait_sync !~ /\A(?:off|end)\z/);
			my $read_timeout = $q->{"$serial\_readtimeout"};
			push @errors, "$serial: read_timeout must be a positive integer"
				if (defined($read_timeout) && $read_timeout ne "" && ($read_timeout !~ /\A\d+\z/ || $read_timeout < 1));
			my $delay = $q->{"$serial\_baudratechangedelay"};
			push @errors, "$serial: baudrate_change_delay must be a non-negative integer"
				if (defined($delay) && $delay ne "" && $delay !~ /\A\d+\z/);
		}
		if ($mode eq "oms") {
			my $key = $q->{"$serial\_omskey"};
			push @errors, "$serial: OMS key must contain exactly 32 hexadecimal characters"
				if (defined($key) && $key ne "" && $key !~ /\A[0-9a-f]{32}\z/i);
			my $debug = $q->{"$serial\_mbusdebug"};
			push @errors, "$serial: mbus_debug must be 0 or 1" if (defined($debug) && $debug !~ /\A[01]\z/);
		}
	}
	die $L{'VZLOGGER.UI_INVALID_SUBMITTED_CONFIG'} . "\n - " . join("\n - ", @errors) . "\n" if (@errors);
}

sub submitted_channel_document
{
	my (@heads) = @_;
	return undef if (!defined($q->{channel_definitions_json}) || $q->{channel_definitions_json} eq "");
	die "Channel definitions exceed 512 KiB.\n" if (length($q->{channel_definitions_json}) > 524288);
	my $document = eval { JSON::PP->new->utf8->decode($q->{channel_definitions_json}) };
	die $L{'VZLOGGER.UI_INVALID_CHANNEL_JSON'} . "\n" if ($@ || ref($document) ne "HASH");
	my %allowed = map { my $s = $_; $s =~ s%/dev/serial/smartmeter/%%g; $s => 1 } @heads;
	foreach my $serial (keys %{$document->{meters} || {}}) {
		die ui_text($L{'VZLOGGER.UI_UNKNOWN_CHANNEL_METER'}, serial => $serial) . "\n" if (!$allowed{$serial});
		my $mode = normalized_meter_mode($plugin_cfg->param("$serial.METER"), $plugin_cfg->param("$serial.PROTOCOL"));
		foreach my $channel (@{$document->{meters}->{$serial} || []}) {
			$channel->{storage} = undef if ($mode eq "oms" || !defined($channel->{storage}) || $channel->{storage} eq "" || $channel->{storage} eq "255");
		}
	}
	my @errors = validate_document($document);
	@errors = @{localize_validation_errors(\@errors, \%L)};
	die $L{'VZLOGGER.UI_INVALID_CHANNELS'} . "\n - " . join("\n - ", @errors) . "\n" if (@errors);
	return $document;
}

sub load_or_migrate_channel_document
{
	my (@heads) = @_;
	my $file = "$lbpconfigdir/vzlogger_channel_definitions.json";
	$channel_document = read_json($file);
	die "Invalid channel definitions JSON: $file\n" if (-e $file && !defined($channel_document));
	$channel_document ||= new_document();
	$channel_document->{meters} ||= {};
	$obis_catalog = load_catalog("$lbptemplatedir/obis_catalog.json");
	my $changed = !-e $file;
	foreach my $device (@heads) {
		my $serial = $device;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		if (ref($channel_document->{meters}->{$serial}) ne "ARRAY") {
			my @available = available_obis_channels($serial);
			my @selected = config_list_values("$serial.OBISCHANNELS");
			my @custom = custom_channels($serial);
			my $selected_ref = defined($plugin_cfg->param("$serial.OBISCHANNELS")) ? \@selected : undef;
			migrate_legacy_meter($channel_document, $serial, $lbpplugindir, \@available, $selected_ref, \@custom, $obis_catalog);
			$changed = 1;
		}
		foreach my $channel (@{$channel_document->{meters}->{$serial}}) {
			if (defined($channel->{storage}) && ($channel->{storage} eq "" || $channel->{storage} eq "255")) {
				$channel->{storage} = undef;
				$changed = 1;
			}
		}
		foreach my $identifier (read_pending_obis_channels($serial)) {
		my $definitions = $channel_document->{meters}->{$serial};
		my %existing = map { compose_obis($_->{obis}, $_->{storage}) => 1 } @$definitions;
		next if ($existing{$identifier});
		my $parsed = parse_obis($identifier);
		next if (!$parsed);
		my $key = default_output_key($identifier, $obis_catalog);
		my %used = map { lc($_->{plugin_output}->{key} || "") => 1 } @$definitions;
		my $suffix = 2;
		my $base_key = $key;
		$key = substr($base_key, 0, 61) . "_" . $suffix++ while ($used{lc($key)});
		my $info = lookup_obis($obis_catalog, $identifier, "en");
		my $aggtime = clean_integer(config_scalar_value("$serial.AGGTIME"), 0);
		push @$definitions, {
			uuid => stable_uuid("$lbpplugindir:$serial:$identifier"), enabled => JSON::PP::true,
			origin => "discovered", obis => $parsed->{base}, storage => $parsed->{f}, display_name => "",
			api => "null", aggmode => $aggtime > 0 ? ($info->{recommended_aggmode} || "none") : "none", duplicates => 0,
			api_options => { volkszaehler => {}, influxdb => {}, mysmartgrid => {} },
			plugin_output => { enabled => JSON::PP::true, key => $key },
		};
			$changed = 1;
		}
	}
	write_json_atomic($file, $channel_document) if ($changed);
}

sub remove_meter_artifacts
{
	my ($serial) = @_;
	return "" if (!defined($serial) || $serial !~ /\A[A-Za-z0-9_.:-]+\z/);
	my $safe_serial = safe_filename($serial);
	my @files = (
		user_meter_source_file($serial),
		"$lbpconfigdir/vzlogger_user_channel_uuids_$safe_serial.json",
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
	my $definitions_file = "$lbpconfigdir/vzlogger_channel_definitions.json";
	my $definitions = read_json($definitions_file);
	if (ref($definitions) eq "HASH" && ref($definitions->{meters}) eq "HASH" && exists($definitions->{meters}->{$serial})) {
		delete $definitions->{meters}->{$serial};
		eval { write_json_atomic($definitions_file, $definitions); 1 } or push @errors, "$definitions_file: $@";
	}
	my $output = ui_text($L{'VZLOGGER.UI_METER_REMOVED'}, serial => $serial) . "\n";
	$output .= ui_text($L{'VZLOGGER.UI_METER_ARTIFACT_REMOVE_FAILED'}, file => $_) . "\n" foreach @errors;
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
	return $L{'VZLOGGER.UI_SAVE_VZLOGGER_FIRST'} . "\n" if (saved_implementation_mode() ne "vzlogger");
	$target_serial = clean_config_value($target_serial, qr/\A[A-Za-z0-9_.:-]+\z/, "");
	return $L{'VZLOGGER.UI_NO_IR_HEAD'} . "\n" if (!$target_serial);

	my %known_heads = map {
		my $serial = $_;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		$serial => 1;
	} @heads;
	return ui_text($L{'VZLOGGER.UI_UNKNOWN_IR_HEAD'}, serial => $target_serial) . "\n" if (!$known_heads{$target_serial});

	my $was_active = service_state("vzlogger") eq "active";
	my $output = "Read OBIS channels for $target_serial.\n";

	if (!command_exists("vzlogger")) {
		$output .= $L{'VZLOGGER.UI_VZLOGGER_NOT_FOUND'} . "\n";
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
	return obis_error_status($L{'VZLOGGER.UI_SAVE_VZLOGGER_FIRST'}) if (saved_implementation_mode() ne "vzlogger");
	$target_serial = clean_config_value($target_serial, qr/\A[A-Za-z0-9_.:-]+\z/, "");
	return obis_error_status($L{'VZLOGGER.UI_NO_IR_HEAD'}) if (!$target_serial);

	my %known_heads = map {
		my $serial = $_;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		$serial => 1;
	} @heads;
	return obis_error_status(ui_text($L{'VZLOGGER.UI_UNKNOWN_IR_HEAD'}, serial => $target_serial)) if (!$known_heads{$target_serial});
	return obis_error_status($L{'VZLOGGER.UI_VZLOGGER_NOT_FOUND'}) if (!command_exists("vzlogger"));
	return obis_error_status($L{'VZLOGGER.UI_OBIS_TIMEOUT_MISSING'}) if (!command_exists("timeout"));

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
		$status->{message} = $launch_output || $L{'VZLOGGER.UI_OBIS_START_FAILED'};
		$status->{finished_at} = time();
		write_obis_discovery_status_file($status);
	}
	return $status;
}

sub obis_error_status
{
	my ($message) = @_;
	$message ||= $L{'VZLOGGER.UI_OBIS_FAILED'};
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
	return obis_error_status($L{'VZLOGGER.UI_OBIS_NOT_ACTIVE'}) if (!$job_id || ($status->{job_id} || "") ne $job_id);
	return obis_error_status($L{'VZLOGGER.UI_OBIS_NO_LONGER_ACTIVE'}) if (($status->{state} || "") !~ /\A(?:starting|running|cancelling)\z/);

	my $cancel_file = obis_discovery_cancel_file();
	make_path(obis_discovery_runtime_dir()) if (!-d obis_discovery_runtime_dir());
	my $fh;
	if (!open($fh, ">", $cancel_file)) {
		return obis_error_status(ui_text($L{'VZLOGGER.UI_OBIS_CANCEL_FAILED'}, error => $!));
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
	my ($activating_vzlogger, $previous_implementation, $replace_expert_runtime) = @_;
	my ($output) = apply_selected_implementation_result($activating_vzlogger, $previous_implementation, $replace_expert_runtime);
	return $output;
}

sub apply_selected_implementation_result
{
	my ($activating_vzlogger, $previous_implementation, $replace_expert_runtime) = @_;
	return run_control_result("disable-vzlogger") if (implementation_mode() ne "vzlogger");
	# A dormant standard configuration is normally reactivated unchanged. If the
	# current runtime still is the explicitly disabled Expert draft, regenerate it
	# once from the retained standard settings before starting the service.
	my $control_action = $activating_vzlogger && !$replace_expert_runtime ? "activate-vzlogger" : "apply";
	my ($output, $exit) = run_control_result($control_action);
	if ($activating_vzlogger && $exit != 0) {
		$output .= rollback_failed_vzlogger_activation($previous_implementation);
	}
	return ($output, $exit);
}

sub rollback_failed_vzlogger_activation
{
	my ($previous_implementation) = @_;
	$previous_implementation = "none";
	set_implementation_mode($plugin_cfg, $previous_implementation);
	$plugin_cfg->save;
	my ($disable_output, $disable_exit) = run_control_result("disable-vzlogger");
	my $output = "\nRestored implementation mode '$previous_implementation' after failed vzLogger activation.\n" . $disable_output;
	$output .= "Could not completely stop the partially activated vzLogger runtime during rollback.\n" if ($disable_exit != 0);
	return $output;
}

sub write_vzlogger_obis_test_config
{
	my ($serial) = @_;
	my $meter = $plugin_cfg->param("$serial.METER") || "0";
	my $protocol = normalized_meter_mode($meter, $plugin_cfg->param("$serial.PROTOCOL"));
	return ("", "", ui_text($L{'VZLOGGER.UI_NO_PROTOCOL'}, serial => $serial) . "\n") if ($protocol eq "0");
	return ("", "", $L{'VZLOGGER.UI_OBIS_CUSTOM_UNAVAILABLE'} . "\n") if ($protocol eq "user");
	return ("", "", $L{'VZLOGGER.UI_OMS_UNSUPPORTED'} . "\n") if ($protocol eq "oms" && !vzlogger_supports_protocol("oms"));

	my $device = $plugin_cfg->param("$serial.DEVICE") || "/dev/serial/smartmeter/$serial";
	return ("", "", ui_text($L{'VZLOGGER.UI_NO_SERIAL_DEVICE'}, serial => $serial) . "\n") if (!$device);

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
	open(my $fh, ">", $config_file) or return ("", "", ui_text($L{'VZLOGGER.UI_DISCOVERY_CONFIG_WRITE_FAILED'}, file => $config_file, error => $!) . "\n");
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
	return $L{'VZLOGGER.UI_OBIS_TIMEOUT_MISSING'} . "\n" if (!command_exists("timeout"));
	if (-e $watchdog_pid_file && open(my $existing_fh, "<", $watchdog_pid_file)) {
		my $existing_pid = <$existing_fh>;
		close($existing_fh);
		chomp($existing_pid) if (defined($existing_pid));
		return $L{'VZLOGGER.UI_OBIS_ALREADY_RUNNING'} . "\n" if (obis_watchdog_running($existing_pid));
		unlink($watchdog_pid_file);
	}

	my $pid = fork();
	return ui_text($L{'VZLOGGER.UI_OBIS_FORK_FAILED'}, error => $!) . "\n" if (!defined($pid));
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
				@channels ? ui_text($L{'VZLOGGER.UI_OBIS_DETECTED'}, count => scalar(@channels)) :
				$L{'VZLOGGER.UI_OBIS_NONE'};
			my $warning = $restore_failed ? $L{'VZLOGGER.UI_OBIS_RESTORE_FAILED'} : "";
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
		while ($line =~ /ObisIdentifier:((?:\d+-\d+:)?[A-Za-z0-9]+\.\d+\.\d+(?:\*\d+)?)/g) {
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
			while ($line =~ /ObisIdentifier:((?:\d+-\d+:)?[A-Za-z0-9]+\.\d+\.\d+(?:\*\d+)?)/g) {
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
	chmod(0600, $tmp);
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
		return (undef, $error || $L{'VZLOGGER.UI_JSONC_INVALID'}, "");
	}
	return (undef, $L{'VZLOGGER.UI_JSONC_OBJECT_REQUIRED'}, "") if (ref($meter) ne "HASH");
	return (undef, $L{'VZLOGGER.UI_JSONC_ROOT_FORBIDDEN'}, "") if (grep { exists($meter->{$_}) } qw(meters mqtt local push retry verbosity log));
	return (undef, $L{'VZLOGGER.UI_JSONC_PROTOCOL_REQUIRED'}, "") if (!defined($meter->{protocol}) || ref($meter->{protocol}) || $meter->{protocol} eq "");
	if (exists($meter->{channels})) {
		return (undef, $L{'VZLOGGER.UI_JSONC_CHANNELS_ARRAY'}, "") if (ref($meter->{channels}) ne "ARRAY");
		foreach my $channel (@{$meter->{channels}}) {
			return (undef, $L{'VZLOGGER.UI_JSONC_CHANNEL_OBJECT'}, "") if (ref($channel) ne "HASH");
		}
	}
	my $warning = "";
	if (defined($meter->{device}) && !ref($meter->{device}) && $meter->{device} =~ m{\A/} && !-e $meter->{device}) {
		$warning = ui_text($L{'VZLOGGER.UI_CONFIGURED_DEVICE_MISSING'}, device => $meter->{device});
	}
	return ($meter, "", $warning);
}

sub format_json_error
{
	my ($source, $error) = @_;
	$error ||= $L{'VZLOGGER.UI_JSONC_INVALID'};
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
	return SmartMeterVZLoggerConfig::implementation_mode($plugin_cfg);
}

sub saved_implementation_mode
{
	my $saved = SmartMeterConfig->new("$lbpconfigdir/smartmeter.json");
	return $saved ? SmartMeterVZLoggerConfig::implementation_mode($saved) : "none";
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
			"0" => ($L{'COMMON.PLEASE_SELECT'} || "Please select"),
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

sub runtime_channel_indices
{
	my $config = read_json("$lbpconfigdir/vzlogger.conf");
	my %indices;
	my $index = 0;
	return \%indices if (ref($config) ne "HASH" || ref($config->{meters}) ne "ARRAY");
	foreach my $meter (@{$config->{meters}}) {
		next if (ref($meter) ne "HASH" || ref($meter->{channels}) ne "ARRAY");
		foreach my $channel (@{$meter->{channels}}) {
			if (ref($channel) eq "HASH" && defined($channel->{uuid}) && !ref($channel->{uuid}) && $channel->{uuid} ne "") {
				$indices{lc($channel->{uuid})} = $index;
			}
			$index++;
		}
	}
	return \%indices;
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
	return normalize_obis($value);
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
	return (999, 999, 999, 999, 999, 999) if (!defined($identifier));
	if ($identifier =~ /\A(\d+)-(\d+):([A-Za-z0-9]+)\.(\d+)\.(\d+)(?:\*(\d+))?\z/) {
		my ($a, $b, $c_part, $d, $e, $f) = ($1, $2, $3, $4, $5, $6);
		my $c = ($c_part =~ /\A\d+\z/) ? int($c_part) : 900 + ord(uc(substr($c_part, 0, 1)));
		return (int($a), int($b), $c, int($d), int($e), defined($f) ? int($f) : 255);
	}
	if ($identifier =~ /\A([A-Za-z0-9]+)\.(\d+)\.(\d+)(?:\*(\d+))?\z/) {
		my ($c_part, $d, $e, $f) = ($1, $2, $3, $4);
		my $c = ($c_part =~ /\A\d+\z/) ? int($c_part) : 900 + ord(uc(substr($c_part, 0, 1)));
		return (0, 0, $c, int($d), int($e), defined($f) ? int($f) : 255);
	}
	return (999, 999, 999, 999, 999, 999);
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
	my $remaining = defined($configuration_action_deadline) ? int($configuration_action_deadline - time) : 0;
	if (defined($configuration_action_deadline) && $remaining <= 0) {
		$configuration_action_timed_out = 1;
		return ($L{'VZLOGGER.UI_CONFIG_TIMEOUT'} . "\n", 124);
	}
	my $output = defined($configuration_action_deadline)
		? `timeout --signal=TERM --kill-after=5s ${remaining}s "$^X" "$script" "$action" 2>&1`
		: `$^X "$script" "$action" 2>&1`;
	my $exit = $? >> 8;
	if (defined($configuration_action_deadline) && ($exit == 124 || $exit == 137)) {
		$configuration_action_timed_out = 1;
		$output .= "\n" . $L{'VZLOGGER.UI_CONFIG_TIMEOUT'} . "\n";
	}
	$output ||= $L{'VZLOGGER.UI_NO_OUTPUT'};
	write_control_log($action, $output);
	return ($output, $exit);
}

# Lazily opened LoxBerry log session for web interface actions. Fixed file with
# append so the many short CGI requests share one log-manager session; the log
# level comes from PLUGINDB_LOGLEVEL (plugin management widget).
my $webui_log;
sub webui_logger
{
	return $webui_log if ($webui_log);
	my $dir = "$lbhomedir/log/plugins/$lbpplugindir";
	make_path($dir) if (!-d $dir);
	$webui_log = LoxBerry::Log->new(
		name     => "webui",
		filename => "$dir/webui.log",
		package  => $lbpplugindir,
		append   => 1,
	);
	return $webui_log;
}

sub write_control_log
{
	my ($action, $output) = @_;
	my $logger = webui_logger();
	$logger->LOGINF("web-action=$action");
	$logger->LOGINF($output) if (defined($output) && $output ne "");
}

sub write_apply_log
{
	my ($output, $display_output) = @_;
	webui_logger()->LOGINF("apply result:\n$output");
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



##########################################################################
# Print Form
##########################################################################

sub form_print
{
	
	# Template
	my $title = $L{'COMMON.PLUGIN_TITLE'} || "Smartmeter-NG";
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
			-expires => 'now',
			-Cache_Control => 'no-store, no-cache, must-revalidate',
			-X_Content_Type_Options => 'nosniff',
	);
	return();
}	
