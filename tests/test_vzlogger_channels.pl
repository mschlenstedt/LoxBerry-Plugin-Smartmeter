#!/usr/bin/perl

use strict;
use warnings;
use FindBin;
use JSON::PP;
use Test::More;
use lib "$FindBin::Bin/../bin";
use SmartMeterVZLoggerChannels qw(parse_obis compose_obis normalize_obis default_output_key valid_output_key stable_uuid load_catalog lookup_obis new_document migrate_legacy_meter validate_document localize_validation_errors native_channel output_order_mapping ordered_output_names);

my $catalog = load_catalog("$FindBin::Bin/../templates/obis_catalog.json");
is($catalog->{version}, 1, "catalog schema version");

my $plain = parse_obis("1-0:1.8.0");
is_deeply([@$plain{qw(a b c d e f)}], [1, 0, 1, 8, 0, undef], "full electricity OBIS parsed");
is(normalize_obis("1-0:1.8.0*255"), "1-0:1.8.0", "storage 255 is canonical unspecified");
is(normalize_obis("1-0:1.8.0*5"), "1-0:1.8.0*5", "explicit storage index is retained");
is(normalize_obis("1.8.0"), "1.8.0", "short D0 form is retained without inventing A/B");
is(compose_obis("1-0:1.8.0", 254), "1-0:1.8.0*254", "highest explicit storage index is retained");
is(compose_obis("1-0:1.8.0", 255), "1-0:1.8.0", "storage 255 composes to canonical unspecified state");
is(compose_obis("1-0:1.8.0", 256), "", "storage index above the DLMS range is rejected");
is(compose_obis("1-0:1.8.0", -1), "", "negative storage index is rejected");
is(stable_uuid("smartmeter-v2:reader:1-0:1.8.0"), "85dc2e4a-9ce8-78e0-7edb-fe9b8c2716cc", "legacy UUID algorithm remains stable");
my $migrated = new_document();
my $legacy_rows = migrate_legacy_meter($migrated, "reader", "smartmeter-v2",
	[{identifier=>"1-0:1.8.0",name=>"Import_Total_OBIS_1.8.0"},{identifier=>"1-0:2.8.0"}], ["1-0:1.8.0"], ["1-0:1.8.0*5"], $catalog);
is(scalar(@$legacy_rows), 3, "migration retains discovered, deselected, and custom identifiers");
ok($legacy_rows->[0]->{enabled} && !$legacy_rows->[1]->{enabled}, "legacy selection and deselection are retained");
is($legacy_rows->[0]->{uuid}, stable_uuid("smartmeter-v2:reader:1-0:1.8.0"), "first migrated instance keeps its previous UUID");
is($legacy_rows->[0]->{plugin_output}->{key}, "Consumption_Total_OBIS_1.8.0", "migration uses the catalog-based output key");
ok(!exists($legacy_rows->[0]->{plugin_output}->{legacy_keys}), "migration does not create additional cache aliases");
is(compose_obis($legacy_rows->[2]->{obis}, $legacy_rows->[2]->{storage}), "1-0:1.8.0*5", "legacy custom F value is retained");

for my $case (
	["1-0:1.8.0", "active_energy_import"], ["1-0:16.7.0", "active_power_total"], ["7-0:1.8.0", "gas_volume"],
	["6-0:1.8.0", "water_volume"], ["5-0:1.8.0", "thermal_energy"],
	["8-0:1.8.0", "heat_cost_allocation"], ["1-0:96.1.0", "identifier"],
) {
	my $info = lookup_obis($catalog, $case->[0], "de");
	ok($info->{known}, "$case->[0] has catalog semantics");
	is($info->{category}, $case->[1], "$case->[0] category");
	ok($info->{short} && $info->{long}, "$case->[0] has short and long text");
}
like(lookup_obis($catalog, "1-0:1.8.0*5", "en")->{long}, qr/index: 5/, "F augments description");
is(default_output_key("1-0:2.8.0", $catalog), "Delivery_Total_OBIS_2.8.0", "default output key combines catalog name and short OBIS code");
is(default_output_key("1-0:2.8.0*5", $catalog), "Delivery_Total_OBIS_2.8.0*5", "default output key retains the canonical storage index");
ok(valid_output_key(q{Name |().-_ []/'%$!*}), "documented spaces and special characters are accepted");
ok(!valid_output_key("Name#Value"), "MQTT wildcard # is rejected in output keys");
ok(!valid_output_key("Name+Value"), "MQTT wildcard + is rejected in output keys");
ok(!valid_output_key("Name:Value"), "colon is rejected in output keys");
ok(!valid_output_key("Name;Value"), "semicolon is rejected in output keys");
ok(!lookup_obis($catalog, "99-0:88.77.66", "en")->{known}, "unknown code stays configurable");
like(lookup_obis($catalog, "99-0:88.77.66", "en")->{long}, qr/A=99.*C=88/, "unknown code is decomposed");

my %priorities;
for my $entry (@{$catalog->{entries}}) {
	ok($entry->{short}->{de} && $entry->{short}->{en}, "$entry->{code}: both short translations");
	ok($entry->{long}->{de} && $entry->{long}->{en}, "$entry->{code}: both long translations");
	ok($entry->{source}, "$entry->{code}: source present");
	ok(!$priorities{$entry->{priority}}++, "$entry->{code}: priority unique");
	ok(parse_obis($entry->{code}), "$entry->{code}: valid code");
	ok(exists($catalog->{sources}->{$entry->{source}}), "$entry->{code}: source identifier resolves");
	ok(!exists($entry->{output_name}) || $entry->{output_name} =~ /\A[A-Za-z0-9_]+\z/, "$entry->{code}: optional technical output name is safe");
}
for my $rule (@{$catalog->{rules}}) {
	ok($rule->{short}->{de} && $rule->{short}->{en}, "rule $rule->{priority}: both short translations");
	ok($rule->{long}->{de} && $rule->{long}->{en}, "rule $rule->{priority}: both long translations");
	ok($rule->{source} && exists($catalog->{sources}->{$rule->{source}}), "rule $rule->{priority}: source resolves");
	ok(!$priorities{$rule->{priority}}++, "rule $rule->{priority}: priority unique");
	my @invalid_groups = grep { $_ !~ /\A[abcde]\z/ } keys %{$rule->{match} || {}};
	ok(!@invalid_groups, "rule $rule->{priority}: only structured A-E match groups");
}

my $doc = new_document();
$doc->{meters}->{reader} = [
	{ uuid => stable_uuid("one"), enabled => JSON::PP::true, origin => "manual", obis => "1-0:1.8.0", storage => undef,
	  display_name => "Grid import", api => "influxdb", aggmode => "avg", duplicates => 1,
	  api_options => { influxdb => { host => "http://influx", database => "meter", token => "secret" }, volkszaehler => { middleware => "inactive" }, mysmartgrid => {} },
	  plugin_output => { enabled => JSON::PP::true, key => "Grid_Import" } },
	{ uuid => stable_uuid("two"), enabled => JSON::PP::true, origin => "manual", obis => "1-0:1.8.0", storage => undef,
	  display_name => "", api => "null", aggmode => "none", duplicates => 0,
	  api_options => { influxdb => { host => "inactive" }, volkszaehler => {}, mysmartgrid => {} },
	  plugin_output => { enabled => JSON::PP::true, key => "Grid_Import_2" } },
];
is_deeply([validate_document($doc)], [], "duplicate identifiers with distinct UUIDs/output keys are valid");
my $native = native_channel($doc->{meters}->{reader}->[0], 30);
is($native->{host}, "http://influx", "active Influx host emitted");
is($native->{aggmode}, "avg", "aggregation emitted when aggtime is active");
ok(!exists($native->{middleware}), "inactive API values are not emitted");
ok(!exists($native->{tokenx}), "unknown API values are not emitted");
is(native_channel($doc->{meters}->{reader}->[0], 0)->{aggmode}, "none", "aggregation forced to none without aggtime");
$doc->{meters}->{reader}->[1]->{plugin_output}->{key} = "grid_import";
like(join("\n", validate_document($doc)), qr/duplicate output key/i, "output keys are unique case-insensitively per reader");
$doc->{meters}->{reader}->[1]->{plugin_output}->{key} = "Readable value 1|Main*(test).8-0";
is_deeply([validate_document($doc)], [], "expanded output-key character set passes document validation");
$doc->{meters}->{reader}->[1]->{plugin_output}->{key} = "Wildcard #key";
like(join("\n", validate_document($doc)), qr/required format: 1-64 characters/, "an MQTT wildcard in the output key is rejected by document validation");
$doc->{meters}->{reader}->[1]->{plugin_output}->{key} = "Readable value 1|Main*(test).8-0";
$doc->{meters}->{reader}->[1]->{plugin_output}->{key} = "invalid:key";
like(join("\n", validate_document($doc)), qr/required format: 1-64 characters/, "invalid output-key error states the required format");
my @technical_errors = validate_document($doc);
like(join("\n", @technical_errors), qr/invalid output key/, "default channel-validation output remains English");
my $localized_errors = localize_validation_errors(\@technical_errors, {
	'VZLOGGER.CHANNEL_VALID_OUTPUT_KEY' => '{path}: ungültiger Output Key (erforderliches Format: {format}).',
});
like(join("\n", @$localized_errors), qr/ungültiger Output Key/, "UI channel-validation output can be localized independently");

my $output_order = output_order_mapping({
	"uuid-2" => { serial => "reader", name => "Second", channel_index => 2 },
	"uuid-0" => { serial => "reader", name => "First", channel_index => 0, legacy_names => ["Ignored_Legacy"] },
	"uuid-x" => { serial => "reader", name => "No_Index" },
});
my %output_values = (
	Second => 2, Last_UpdateLoxEpoche => 3, Extra_Z => 9,
	Last_Update => "2026-07-17 12:00:00", First => 1, Extra_A => 8, No_Index => 7,
);
is_deeply(
	[ordered_output_names(\%output_values, $output_order->{reader})],
	[qw(Last_Update Last_UpdateLoxEpoche First Second Extra_A Extra_Z No_Index)],
	"cache and UDP names are ordered by timestamps, channel number, then unmapped name",
);

done_testing();
