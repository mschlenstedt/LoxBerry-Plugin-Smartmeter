#!/usr/bin/perl

use strict;
use warnings;
use FindBin;
use Test::More;
use lib "$FindBin::Bin/../bin";
use SmartMeterVZLoggerConfig qw(validate_legacy_general normalized_meter_mode protocol_for_meter serial_mode sanitize_topic clean_qos implementation_mode set_implementation_mode);

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
is(implementation_mode(TestConfig->new("MAIN.IMPLEMENTATION" => "legacy", "MAIN.READ" => 0)), "legacy", "explicit Legacy mode is retained independently of READ");
is(implementation_mode(TestConfig->new("MAIN.IMPLEMENTATION" => "vzlogger", "MAIN.READ" => 1)), "vzlogger", "explicit vzLogger mode is retained independently of READ");
is(implementation_mode(TestConfig->new("MAIN.READ" => 1)), "legacy", "missing mode infers Legacy from enabled reads");
is(implementation_mode(TestConfig->new("MAIN.READ" => 0)), "vzlogger", "missing mode infers vzLogger from disabled Legacy reads");

foreach my $transition (
	[legacy => "vzlogger"], [legacy => "none"],
	[vzlogger => "legacy"], [vzlogger => "none"],
	[none => "legacy"], [none => "vzlogger"],
) {
	my ($from, $to) = @$transition;
	my $transition_cfg = TestConfig->new(
		"MAIN.IMPLEMENTATION" => $from,
		"reader.LEGACY_METER" => "legacy-sentinel",
		"reader.METER" => "vzlogger-sentinel",
	);
	is(set_implementation_mode($transition_cfg, $to), $to, "$from -> $to stores the requested mode");
	is(implementation_mode($transition_cfg), $to, "$from -> $to resolves to exactly one mode");
	is_deeply(
		[$transition_cfg->param("reader.LEGACY_METER"), $transition_cfg->param("reader.METER")],
		["legacy-sentinel", "vzlogger-sentinel"],
		"$from -> $to preserves both inactive configurations",
	);
}
eval { set_implementation_mode(TestConfig->new(), "invalid") };
like($@, qr/Invalid SmartMeter implementation mode/, "invalid implementation states are rejected centrally");

my $valid = {
	implementation => "legacy", read => "1", cron => "5", sendudp => "1",
	udpport => "7000", sendmqtt => "0", mqtttopic => "smartmeter/site",
	meters => [{ serial => "reader", meter => "preset" }],
};
is_deeply([validate_legacy_general($valid, { preset => 1 })], [], "valid Legacy general settings pass");

foreach my $case (
	[implementation => "vzlogger", qr/IMPLEMENTATION/], [read => "2", qr/READ/],
	[cron => "2", qr/CRON/], [sendudp => "yes", qr/SENDUDP/],
	[udpport => "0", qr/UDPPORT/], [udpport => "65536", qr/UDPPORT/],
	[sendmqtt => "", qr/SENDMQTT/], [mqtttopic => "bad/#", qr/MQTTTOPIC/],
) {
	my ($field, $value, $expected) = @$case;
	my %copy = %$valid;
	$copy{$field} = $value;
	like(join(",", validate_legacy_general(\%copy, { preset => 1 })), $expected, "$field rejects invalid value");
}
my %unknown_meter = %$valid;
$unknown_meter{meters} = [{ serial => "reader", meter => "not-installed" }];
like(join(",", validate_legacy_general(\%unknown_meter, { preset => 1 })), qr/METER/, "unknown meter template is rejected");

my %manual = %$valid;
$manual{meters} = [{ serial => "reader", meter => "manual", protocol => "sml", startbaudrate => 300,
	baudrate => 9600, timeout => 30, delay => 0, databits => 8, stopbits => 1, parity => "none" }];
is_deeply([validate_legacy_general(\%manual, {})], [], "bounded manual Legacy settings pass");
$manual{meters}->[0]->{baudrate} = 99999999;
like(join(",", validate_legacy_general(\%manual, {})), qr/BAUDRATE/, "unsafe manual baud rate is rejected");

open(my $legacy_fh, "<", "$FindBin::Bin/../webfrontend/htmlauth/index_legacy.cgi") or die $!;
binmode($legacy_fh);
my $legacy_shebang = <$legacy_fh>;
is($legacy_shebang, "#!/usr/bin/perl\n", "Legacy CGI shebang uses an executable Unix line ending");
seek($legacy_fh, 0, 0) or die $!;
local $/;
my $legacy_source = <$legacy_fh>;
close($legacy_fh);
like(
	$legacy_source,
	qr/use LoxBerry::System;.*use lib \$lbpbindir;.*use SmartMeterVZLoggerConfig/s,
	"installed Legacy CGI loads shared modules from the LoxBerry plugin bin directory",
);
like($legacy_source, qr/initialize_legacy_heads\(\$plugin_cfg, \@heads\)/, "Legacy page uses shared head migration");
like($legacy_source, qr/\$clearcache = \$is_post.*action.*clearcache/s, "Legacy cache action is POST-only");
unlike($legacy_source, qr/url_param\('clearcache'\)/, "Legacy cache action is not accepted from the query string");
unlike($legacy_source, qr/print\s+["']Content-type:/i, "LoxBerry header owns the Legacy CGI HTTP response header");
like($legacy_source, qr/elsif \(\$implementation ne "vzlogger"\)/, "Saving an unchanged inactive Legacy page cannot disable an active vzLogger mode");
like($legacy_source, qr/restore_implementation_runtime\(\$previous_implementation\)/, "failed Legacy mode transitions restore the preceding runtime state");

open(my $vzlogger_cgi_fh, "<", "$FindBin::Bin/../webfrontend/htmlauth/index.cgi") or die $!;
local $/;
my $vzlogger_cgi_source = <$vzlogger_cgi_fh>;
close($vzlogger_cgi_fh);
like($vzlogger_cgi_source, qr/rollback_failed_vzlogger_activation\(\$previous_implementation\)/, "failed vzLogger activation restores the preceding implementation mode");
like($vzlogger_cgi_source, qr/SMARTMETER_LEGACY_LOCK_HELD/, "vzLogger activation passes its held Legacy polling guard to the service controller");
like($vzlogger_cgi_source, qr/\$starting && implementation_mode\(\) ne "vzlogger"/, "service Start and Restart require saved vzLogger mode server-side");
like($vzlogger_cgi_source, qr/start_obis_discovery_background.*saved_implementation_mode\(\) ne "vzlogger"/s, "OBIS discovery requires saved vzLogger mode server-side");
my ($service_settings_source) = $vzlogger_cgi_source =~ /(sub save_service_log_settings.*?)(?=\nsub generated_config_status)/s;
unlike($service_settings_source || "", qr/set_implementation_mode|remove_legacy_cronjobs/, "service buttons cannot persist an implementation transition themselves");

open(my $legacy_template_fh, "<", "$FindBin::Bin/../templates/multi/main.html") or die $!;
local $/;
my $legacy_template = <$legacy_template_fh>;
close($legacy_template_fh);
like($legacy_template, qr/id="legacy-dependent-content"/, "Legacy dependent UI has a single state container");
like($legacy_template, qr/function refresh_legacy_dependent_state\(\)/, "Legacy UI uses centralized activation rendering");
like($legacy_template, qr/fetch_enabled = enabled && saved_implementation == "legacy" && !vzlogger_service_active/, "manual Legacy polling requires saved Legacy mode and a stopped vzLogger service");
like($legacy_template, qr/id="legacy_cache_form"[^>]*action="\.\/index_legacy\.cgi"/s, "Legacy cache uses a dedicated POST form");

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
like($vzlogger_template, qr/id="bridge_activation_unsaved".*ACTIVATION_UNSAVED_RUNTIME/, "bridge activation draft explains that runtime actions remain locked");

done_testing();
