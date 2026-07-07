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
	
        # Default is owfs form
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
	my @heads = detect_heads();
	ensure_head_defaults(@heads);

	if ($q->{saveformdata}) {
		save_vzlogger_form(@heads);
		my $action = $q->{submitaction} || "generate";
		my $control_action = "generate";
		$control_action = "apply" if ($action eq "apply");
		$control_action = "install-vzlogger" if ($action eq "install-vzlogger");
		$control_action = "install-bridge-service" if ($action eq "install-bridge-service");
		$control_action = "validate" if ($action eq "validate");
		$control_action = "debug-log" if ($action eq "debug-log");
		my $output = run_control($control_action);
		$template->param("VZLOGGER_MESSAGE", $output);
		$plugin_cfg = Config::Simple->new($config_file) or die "Could not reload $config_file";
	}

	my @rows = build_head_rows(@heads);
	my $local_port = $plugin_cfg->param("VZLOGGER.LOCALPORT") || 18080;
	my $mqtttopic = $plugin_cfg->param("MAIN.MQTTTOPIC") || "smartmeter";

	$template->param("FORM_VZLOGGER", 1);
	$template->param("READ" => $plugin_cfg->param("MAIN.READ") || 0);
	$template->param("CRON" => $plugin_cfg->param("MAIN.CRON") || 5);
	$template->param("SENDUDP" => $plugin_cfg->param("MAIN.SENDUDP") || 0);
	$template->param("UDPPORT" => $plugin_cfg->param("MAIN.UDPPORT") || 7000);
	$template->param("MQTTTOPIC" => $mqtttopic);
	$template->param("VZLOGGER_LOCALPORT" => $local_port);
	$template->param("VZLOGGER_VERBOSITY" => $plugin_cfg->param("VZLOGGER.VERBOSITY") || 5);
	$template->param("VZLOGGER_UDPINTERVAL" => $plugin_cfg->param("VZLOGGER.UDPINTERVAL") || 5);
	$template->param("VZLOGGER_DEBUG" => $plugin_cfg->param("VZLOGGER.DEBUG") || 0);
	$template->param("VZLOGGER_STATUS" => run_control("status"));
	$template->param("VZLOGGER_CONFIG" => "$lbpconfigdir/vzlogger.conf");
	$template->param("VZLOGGER_LIVEURL" => "http://$ENV{HTTP_HOST}:$local_port/");
	$template->param("ROWS" => \@rows);
	return();
}

sub ensure_vzlogger_defaults
{
	$plugin_cfg->param("MAIN.READ", "0") if (!defined $plugin_cfg->param("MAIN.READ"));
	$plugin_cfg->param("MAIN.CRON", "5") if (!$plugin_cfg->param("MAIN.CRON"));
	$plugin_cfg->param("MAIN.SENDUDP", "0") if (!defined $plugin_cfg->param("MAIN.SENDUDP"));
	$plugin_cfg->param("MAIN.UDPPORT", "7000") if (!$plugin_cfg->param("MAIN.UDPPORT"));
	$plugin_cfg->param("MAIN.MQTTTOPIC", "smartmeter") if (!$plugin_cfg->param("MAIN.MQTTTOPIC"));
	$plugin_cfg->param("VZLOGGER.LOCALPORT", "18080") if (!$plugin_cfg->param("VZLOGGER.LOCALPORT"));
	$plugin_cfg->param("VZLOGGER.VERBOSITY", "5") if (!$plugin_cfg->param("VZLOGGER.VERBOSITY"));
	$plugin_cfg->param("VZLOGGER.UDPINTERVAL", "5") if (!$plugin_cfg->param("VZLOGGER.UDPINTERVAL"));
	$plugin_cfg->param("VZLOGGER.DEBUG", "0") if (!defined $plugin_cfg->param("VZLOGGER.DEBUG"));
	$plugin_cfg->save;
}

sub detect_heads
{
	return sort glob("/dev/serial/smartmeter/*");
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
	}
	$plugin_cfg->save;
}

sub save_vzlogger_form
{
	my (@heads) = @_;
	$plugin_cfg->param("MAIN.READ", clean_config_value($q->{read}, qr/\A[01]\z/, "0"));
	$plugin_cfg->param("MAIN.CRON", clean_config_value($q->{cron}, qr/\A(M|1|3|5|10|15|30|60)\z/, "5"));
	$plugin_cfg->param("MAIN.SENDUDP", clean_config_value($q->{sendudp}, qr/\A[01]\z/, "0"));
	$plugin_cfg->param("MAIN.UDPPORT", clean_config_value($q->{udpport}, qr/\A\d+\z/, "7000"));
	$plugin_cfg->param("MAIN.MQTTTOPIC", clean_config_value($q->{mqtttopic}, qr/\A[^#+]+\z/, "smartmeter"));
	$plugin_cfg->param("VZLOGGER.LOCALPORT", clean_config_value($q->{vzlogger_localport}, qr/\A\d+\z/, "18080"));
	$plugin_cfg->param("VZLOGGER.VERBOSITY", clean_config_value($q->{vzlogger_verbosity}, qr/\A\d+\z/, "5"));
	$plugin_cfg->param("VZLOGGER.UDPINTERVAL", clean_config_value($q->{vzlogger_udpinterval}, qr/\A\d+\z/, "5"));
	$plugin_cfg->param("VZLOGGER.DEBUG", clean_config_value($q->{vzlogger_debug}, qr/\A[01]\z/, "0"));

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
	}
	$plugin_cfg->save;
}

sub build_head_rows
{
	my (@heads) = @_;
	my @rows;
	foreach my $device (@heads) {
		my $serial = $device;
		$serial =~ s%/dev/serial/smartmeter/%%g;
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
		};
	}
	return @rows;
}

sub run_control
{
	my ($action) = @_;
	my $script = "$lbpbindir/vzlogger_control.pl";
	return "Control script not found: $script" if (!-e $script);
	my $output = `$^X "$script" "$action" 2>&1`;
	return $output || "No output.";
}

sub clean_config_value
{
	my ($value, $pattern, $default) = @_;
	return $default if (!defined($value));
	return $value if ($value =~ $pattern);
	return $default;
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
	
	# Navbar
	our %navbar;

	$navbar{10}{Name} = "$L{'MENU.LABEL_VZLOGGER'}";
	$navbar{10}{URL} = 'index.cgi';
	$navbar{10}{active} = 1 if $q->{form} eq "vzlogger";
	
	$navbar{20}{Name} = "$L{'MENU.LABEL_LEGACY'}";
	$navbar{20}{URL} = 'index_legacy.cgi';
	$navbar{20}{active} = 1 if $q->{form} eq "legacy";
	
	# Template
	LoxBerry::Web::lbheader($L{'COMMON.LABEL_PLUGINTITLE'} . " V$version", "https://www.loxwiki.eu/x/mA-L", "");
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

