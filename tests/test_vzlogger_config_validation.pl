#!/usr/bin/perl

use strict;
use warnings;
use FindBin;
use Test::More;
use lib "$FindBin::Bin/../bin";
use SmartMeterVZLoggerConfig qw(normalized_meter_mode protocol_for_meter serial_mode sanitize_topic clean_qos implementation_mode set_implementation_mode);

{
	package TestConfig;
	sub new { my $class = shift; return bless { @_ }, $class; }
	sub param { my ($self, $key, $value) = @_; $self->{$key} = $value if (@_ == 3); return $self->{$key}; }
}

is(protocol_for_meter("generic-d0"), "d0", "shared protocol mapper recognizes D0");
is(normalized_meter_mode("manual", "sml"), "sml", "manual legacy mode maps through shared protocol mapper");
is(serial_mode(7, "even", 1), "7E1", "shared serial mode is canonical");
is(sanitize_topic(" /smartmeter/site/ "), "smartmeter/site", "shared topic normalization trims separators");
is(clean_qos("2", 0), 2, "shared QoS cleaner accepts supported values");
is(clean_qos("bad", 1), 1, "shared QoS cleaner retains its validated default");
is(implementation_mode(TestConfig->new("MAIN.IMPLEMENTATION" => "none", "MAIN.READ" => 1)), "none", "explicit inactive mode is retained");
is(implementation_mode(TestConfig->new("MAIN.IMPLEMENTATION" => "vzlogger", "MAIN.READ" => 1)), "vzlogger", "explicit vzLogger mode is retained independently of READ");
is(implementation_mode(TestConfig->new("MAIN.READ" => 1)), "none", "missing mode stays inactive instead of guessing");
is(implementation_mode(TestConfig->new("MAIN.IMPLEMENTATION" => "legacy")), "none", "a stored Legacy mode from older releases resolves to inactive");

foreach my $transition (
	[vzlogger => "none"],
	[none => "vzlogger"],
) {
	my ($from, $to) = @$transition;
	my $transition_cfg = TestConfig->new(
		"MAIN.IMPLEMENTATION" => $from,
		"reader.METER" => "vzlogger-sentinel",
	);
	is(set_implementation_mode($transition_cfg, $to), $to, "$from -> $to stores the requested mode");
	is(implementation_mode($transition_cfg), $to, "$from -> $to resolves to exactly one mode");
	is($transition_cfg->param("reader.METER"), "vzlogger-sentinel", "$from -> $to preserves the meter configuration");
}
eval { set_implementation_mode(TestConfig->new(), "invalid") };
like($@, qr/Invalid SmartMeter implementation mode/, "invalid implementation states are rejected centrally");
eval { set_implementation_mode(TestConfig->new(), "legacy") };
like($@, qr/Invalid SmartMeter implementation mode/, "the removed Legacy mode can no longer be stored");

open(my $vzlogger_cgi_fh, "<", "$FindBin::Bin/../webfrontend/htmlauth/index.cgi") or die $!;
local $/;
my $vzlogger_cgi_source = <$vzlogger_cgi_fh>;
close($vzlogger_cgi_fh);
like($vzlogger_cgi_source, qr/rollback_failed_vzlogger_activation\(\$previous_implementation\)/, "failed vzLogger activation restores the preceding implementation mode");
like($vzlogger_cgi_source, qr/\$starting && implementation_mode\(\) ne "vzlogger"/, "service Start and Restart require saved vzLogger mode server-side");
like($vzlogger_cgi_source, qr/start_obis_discovery_background.*saved_implementation_mode\(\) ne "vzlogger"/s, "OBIS discovery requires saved vzLogger mode server-side");
my ($service_settings_source) = $vzlogger_cgi_source =~ /(sub save_service_log_settings.*?)(?=\nsub generated_config_status)/s;
unlike($service_settings_source || "", qr/set_implementation_mode/, "service buttons cannot persist an implementation transition themselves");

foreach my $removed (qw(
	SmartMeterLegacyRuntime initialize_legacy_heads acquire_legacy_fetch_lock
	synchronize_legacy_runtime remove_legacy_cronjobs SMARTMETER_LEGACY_LOCK_HELD
	index_legacy.cgi logfiles.cgi fetch.cgi
)) {
	unlike($vzlogger_cgi_source, qr/\Q$removed\E/, "the vzLogger CGI no longer references $removed");
}

foreach my $removed_file (qw(
	bin/fetch.pl bin/sm_logger.pl bin/sml_parser.php bin/php_sml_parser.class.php
	bin/reboot_cron_runner.sh bin/SmartMeterLegacyRuntime.pm bin/smartmeter_legacy_runtime.pl
	webfrontend/htmlauth/index_legacy.cgi webfrontend/htmlauth/fetch.cgi
	webfrontend/htmlauth/logfiles.cgi templates/multi/main.html
)) {
	ok(!-e "$FindBin::Bin/../$removed_file", "the removed Legacy artifact $removed_file is gone");
}

open(my $vzlogger_template_fh, "<", "$FindBin::Bin/../templates/settings.html") or die $!;
local $/;
my $vzlogger_template = <$vzlogger_template_fh>;
close($vzlogger_template_fh);
like($vzlogger_template, qr/action == "apply" && response\.ok/, "failed vzLogger apply keeps the saved tab and activation state unchanged");
like($vzlogger_template, qr/var saved_vzlogger = !!applied\.vzlogger_enabled/, "vzLogger runtime buttons use the saved implementation snapshot");
like($vzlogger_template, qr/var vz_enabled = saved_vzlogger && ui\.vzlogger/, "vzLogger Start and Restart require both saved and current draft activation");
like($vzlogger_template, qr/runtime_action_disabled = saved_implementation != "vzlogger"/, "OBIS discovery remains disabled until vzLogger activation is saved");
like($vzlogger_template, qr/class="obis-runtime-action-reason".*OBIS_SAVE_ACTIVATION_HELP/, "disabled OBIS discovery has an inline save-and-apply explanation");
like($vzlogger_template, qr/class="obis-discovery".*?aria-describedby="<TMPL_VAR NAME=SERIAL>_obis_runtime_reason".*?id="<TMPL_VAR NAME=SERIAL>_obis_runtime_reason"/s, "OBIS discovery references its runtime lock explanation accessibly");
like($vzlogger_template, qr/id="implementation_unsaved".*ACTIVATION_UNSAVED_RUNTIME/, "vzLogger activation draft explains that runtime actions remain locked");

done_testing();
