#!/usr/bin/perl

use strict;
use warnings;
use File::Temp qw(tempdir);
use FindBin;
use JSON::PP;
use Test::More;
use lib "$FindBin::Bin/../bin";
use SmartMeterVZLoggerChannels qw(stable_uuid write_json_atomic);

my $dir = tempdir(CLEANUP => 1);
my $config_file = "$dir/smartmeter.cfg";
open(my $cfg, ">", $config_file) or die $!;
print $cfg <<'CFG';
[MAIN]
IMPLEMENTATION=vzlogger
MQTTTOPIC=smartmeter
[VZLOGGER]
LOCALENABLED=1
LOCALPORT=18080
MQTTENABLED=1
MQTTHOST=127.0.0.1
MQTTPORT=1883
[reader]
SERIAL=reader
METER=sml
PROTOCOL=sml
DEVICE=/dev/null
ENABLED=1
ALLOWSKIP=1
AGGTIME=30
CFG
close($cfg);

my $first_uuid = stable_uuid("first");
my $second_uuid = stable_uuid("second");
my $disabled_uuid = stable_uuid("disabled");
my $document = {
	version => 1,
	meters => { reader => [
		{ uuid=>$first_uuid, enabled=>JSON::PP::true, origin=>"manual", obis=>"1-0:1.8.0", storage=>5, display_name=>"Historic label only", api=>"influxdb", aggmode=>"avg", duplicates=>1,
		  api_options=>{influxdb=>{host=>"http://influx",database=>"meter",organization=>"org",send_uuid=>JSON::PP::true},volkszaehler=>{middleware=>"must-not-leak"},mysmartgrid=>{}}, plugin_output=>{enabled=>JSON::PP::true,key=>"Import_Storage_5",legacy_keys=>["Consumption_Total_OBIS_1.8.0"]} },
		{ uuid=>$second_uuid, enabled=>JSON::PP::true, origin=>"manual", obis=>"1-0:1.8.0", storage=>5, display_name=>"", api=>"null", aggmode=>"none", duplicates=>9,
		  api_options=>{influxdb=>{host=>"must-not-leak"},volkszaehler=>{},mysmartgrid=>{}}, plugin_output=>{enabled=>JSON::PP::false,key=>"Not_Output"} },
		{ uuid=>$disabled_uuid, enabled=>JSON::PP::false, origin=>"manual", obis=>"1-0:2.8.0", storage=>undef, display_name=>"", api=>"volkszaehler", aggmode=>"none", duplicates=>0,
		  api_options=>{influxdb=>{},volkszaehler=>{},mysmartgrid=>{}}, plugin_output=>{enabled=>JSON::PP::true,key=>"Disabled"} },
	] },
};
write_json_atomic("$dir/vzlogger_channel_definitions.json", $document);

local $ENV{SMARTMETER_CONFIG_DIR} = $dir;
local $ENV{SMARTMETER_CONFIG_FILE} = $config_file;
local $ENV{SMARTMETER_VZLOGGER_CONFIG_FILE} = "$dir/vzlogger.conf";
local $ENV{SMARTMETER_VZLOGGER_MAPPING_FILE} = "$dir/vzlogger_channels.json";
local $ENV{SMARTMETER_VZLOGGER_DEFINITIONS_FILE} = "$dir/vzlogger_channel_definitions.json";
local $ENV{SMARTMETER_OBIS_CATALOG_FILE} = "$FindBin::Bin/../templates/obis_catalog.json";
local $ENV{SMARTMETER_VALIDATION_DRAFT} = "1";
my $stub = "$FindBin::Bin/../.github/ci/perl-lib";
my $status = system($^X, "-I", $stub, "$FindBin::Bin/../bin/vzlogger_config.pl");
is($status, 0, "generator succeeds with structured definitions");

sub read_json_file {
	my ($file) = @_;
	open(my $fh, "<", $file) or die $!;
	local $/;
	return JSON::PP->new->utf8->decode(<$fh>);
}

my $generated = read_json_file("$dir/vzlogger.conf");
is(scalar(@{$generated->{meters}->[0]->{channels}}), 2, "only active definitions are generated");
is($generated->{meters}->[0]->{channels}->[0]->{identifier}, "1-0:1.8.0*5", "storage index reaches vzLogger identifier");
is($generated->{meters}->[0]->{channels}->[0]->{host}, "http://influx", "active API field generated");
ok(!exists($generated->{meters}->[0]->{channels}->[0]->{middleware}), "inactive API field omitted");
ok(!exists($generated->{meters}->[0]->{channels}->[0]->{display_name}), "display name is not a vzLogger field");
ok(!exists($generated->{meters}->[0]->{channels}->[0]->{name}), "no general channel name is invented");
ok(!exists($generated->{meters}->[0]->{channels}->[1]->{duplicates}), "duplicates omitted for null API");

my $mapping = read_json_file("$dir/vzlogger_channels.json");
is_deeply([sort keys %$mapping], [$first_uuid], "mapping contains only active plugin outputs");
is($mapping->{$first_uuid}->{name}, "Import_Storage_5", "mapping uses technical output key");
is($mapping->{$first_uuid}->{identifier}, "1-0:1.8.0*5", "mapping preserves full identifier");
is($mapping->{$first_uuid}->{channel}, "chn0", "mapping exposes the vzLogger MQTT DATA channel name");
is($mapping->{$first_uuid}->{channel_index}, 0, "mapping channel number matches the generated channel order");
is($mapping->{$first_uuid}->{catalog_name_de}, "Bezogene Wirkenergie, gesamt", "mapping carries the catalog display name");
is($mapping->{$first_uuid}->{unit}, "kWh", "mapping carries the catalog unit");
is($mapping->{$first_uuid}->{display_factor}, 0.001, "mapping converts the vzLogger Wh value to catalog kWh for display");
ok(!exists($mapping->{$first_uuid}->{legacy_names}), "mapping emits only the configured output key and no aliases");
ok($mapping->{$first_uuid}->{identifier_ambiguous}, "identifier fallback is disabled when another active channel has the same identifier");

done_testing();
