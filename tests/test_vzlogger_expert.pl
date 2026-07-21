#!/usr/bin/perl

use strict;
use warnings;
use FindBin;
use JSON::PP;
use Test::More;
use lib "$FindBin::Bin/../bin";
use SmartMeterVZLoggerExpert qw(validate_expert_text build_expert_mapping update_expert_log_settings expert_configs_equal);

my $uuid = "11111111-2222-3333-4444-555555555555";
my $config = {
	retry => 30,
	verbosity => 0,
	log => "/dev/null",
	local => { enabled => JSON::PP::true, port => 18080 },
	mqtt => { enabled => JSON::PP::true, host => "127.0.0.1", port => 1883, topic => "smartmeter" },
	meters => [{ enabled => JSON::PP::true, protocol => "custom-protocol", vendor_option => 42, channels => [
		{ api => "null", uuid => $uuid, identifier => "1-0:1.8.0" },
	]}],
	upstream_extension => { enabled => JSON::PP::true },
};
my $text = JSON::PP->new->utf8->pretty->encode($config);
my $valid = validate_expert_text($text);
ok($valid->{valid}, "valid expert configuration passes");
like(join("\n", @{$valid->{warnings}}), qr/upstream_extension/, "unknown root keys are warnings");

my $invalid = validate_expert_text('{"meters": [}');
ok(!$invalid->{valid}, "invalid JSON is retained as an invalid draft");
like($invalid->{errors}->[0], qr/not valid JSON/, "JSON error is reported without content");
ok(expert_configs_equal($text, JSON::PP->new->utf8->canonical->encode($config)), "semantic comparison ignores JSON formatting");
my $changed_text = JSON::PP->new->utf8->canonical->encode({ %$config, retry => 31 });
ok(!expert_configs_equal($text, $changed_text), "semantic comparison detects changed configuration values");
ok(!expert_configs_equal($text, '{'), "semantic comparison rejects invalid JSON");

my ($updated, $updated_status) = update_expert_log_settings($text, 15, "/tmp/vzlogger.log");
ok($updated_status->{valid}, "log update remains valid");
my $updated_json = JSON::PP->new->utf8->decode($updated);
is($updated_json->{verbosity}, 15, "verbosity updated");
is($updated_json->{log}, "/tmp/vzlogger.log", "log path updated");
is($updated_json->{meters}->[0]->{vendor_option}, 42, "unknown meter data retained");

my $existing = {
	$uuid => {
		serial => "reader-a", name => "Import_Total", managed_output => JSON::PP::true,
		identifier => "old", channel => "chn9", channel_index => 9,
	},
};
my ($mapping, $warnings) = build_expert_mapping($valid->{config}, $existing);
is($mapping->{$uuid}->{name}, "Import_Total", "existing bridge output key retained");
is($mapping->{$uuid}->{identifier}, "1-0:1.8.0", "mapping identifier refreshed");
is($mapping->{$uuid}->{channel_index}, 0, "mapping index refreshed");
is(scalar(@$warnings), 0, "known UUID produces no mapping warning");

push @{$valid->{config}->{meters}->[0]->{channels}}, {
	api => "null", uuid => "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", identifier => "1-0:2.8.0",
};
($mapping, $warnings) = build_expert_mapping($valid->{config}, $existing);
ok(!exists($mapping->{"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}), "unknown expert UUID is not auto-published");
like(join("\n", @$warnings), qr/will not be published/, "unknown UUID warning is reported");

open(my $index_fh, "<", "$FindBin::Bin/../webfrontend/htmlauth/index.cgi") or die $!;
local $/;
my $index_source = <$index_fh>;
close($index_fh);
like($index_source, qr/\$enabled eq "1" && !\$was_enabled && !-e expert_config_file\(\)/, "mode activation initializes only a missing expert draft");
unlike($index_source, qr/unlink\(expert_config_file\(\)\)/, "standard apply does not remove the expert draft");
like($index_source, qr/ajaxaction.*expert-reset|\$action eq "expert-reset"/s, "explicit expert reset AJAX action is available");

done_testing();
