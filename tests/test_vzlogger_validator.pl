#!/usr/bin/perl

use strict;
use warnings;

use File::Temp qw(tempdir);
use FindBin;
use JSON::PP;
use Test::More;
use lib "$FindBin::Bin/../bin";
use SmartMeterVZLoggerChannels qw(stable_uuid);

my $dir = tempdir(CLEANUP => 1);
my $device = "$dir/meter-device";
open(my $device_fh, ">", $device) or die $!;
print $device_fh "test\n";
close($device_fh);

my $uuid = stable_uuid("validator-channel");
my $base_config = {
	retry => 30,
	verbosity => 0,
	log => "/dev/null",
	local => { enabled => JSON::PP::true, port => 18080, index => JSON::PP::true, timeout => 30, buffer => -1 },
	mqtt => { enabled => JSON::PP::false, host => "127.0.0.1", port => 1883, keepalive => 30, topic => "smartmeter/vzlogger", retain => JSON::PP::true, rawAndAgg => JSON::PP::false, qos => 0, timestamp => JSON::PP::true },
	meters => [{
		enabled => JSON::PP::true, allowskip => JSON::PP::true, protocol => "sml", device => $device,
		aggtime => 30, interval => -1, baudrate => 9600, parity => "8n1", use_local_time => JSON::PP::false,
		channels => [{ api => "null", uuid => $uuid, identifier => "1-0:1.8.0", aggmode => "none" }],
	}],
};
my $base_definitions = {
	version => 1,
	meters => { reader => [{
		uuid => $uuid, enabled => JSON::PP::true, origin => "manual", obis => "1-0:1.8.0", storage => undef,
		display_name => "Grid import", api => "null", aggmode => "none", duplicates => 0,
		api_options => { volkszaehler => {}, influxdb => {}, mysmartgrid => {} },
		plugin_output => { enabled => JSON::PP::true, key => "Grid_Import" },
	}] },
};
my $base_mapping = {
	$uuid => {
		serial => "reader", name => "Grid_Import", managed_output => JSON::PP::true,
		identifier => "1-0:1.8.0", channel => "chn0", channel_index => 0,
	},
};

sub clone_data
{
	my ($value) = @_;
	return JSON::PP->new->decode(JSON::PP->new->encode($value));
}

sub write_json
{
	my ($file, $value) = @_;
	open(my $fh, ">", $file) or die $!;
	print $fh JSON::PP->new->canonical->pretty->encode($value);
	close($fh);
}

sub run_validator
{
	my (%args) = @_;
	write_json("$dir/vzlogger.conf", $args{config});
	write_json("$dir/vzlogger_channels.json", $args{mapping});
	write_json("$dir/vzlogger_channel_definitions.json", $args{definitions});
	open(my $cfg, ">", "$dir/smartmeter.cfg") or die $!;
	print $cfg "[MAIN]\nIMPLEMENTATION=" . ($args{implementation} || "vzlogger") . "\nREAD=" . ($args{read} || 0) . "\n";
	close($cfg);

	local $ENV{SMARTMETER_CONFIG_DIR} = $dir;
	local $ENV{SMARTMETER_CONFIG_FILE} = "$dir/smartmeter.cfg";
	local $ENV{SMARTMETER_VZLOGGER_CONFIG_FILE} = "$dir/vzlogger.conf";
	local $ENV{SMARTMETER_VZLOGGER_MAPPING_FILE} = "$dir/vzlogger_channels.json";
	local $ENV{SMARTMETER_VZLOGGER_DEFINITIONS_FILE} = "$dir/vzlogger_channel_definitions.json";
	my $path_separator = $^O eq "MSWin32" ? ";" : ":";
	local $ENV{PERL5LIB} = "$FindBin::Bin/../.github/ci/perl-lib" . ($ENV{PERL5LIB} ? "$path_separator$ENV{PERL5LIB}" : "");
	open(my $pipe, "-|", $^X, "$FindBin::Bin/../bin/vzlogger_validate.pl") or die $!;
	local $/;
	my $output = <$pipe>;
	close($pipe);
	return ($? >> 8, $output || "");
}

sub base_case
{
	return (clone_data($base_config), clone_data($base_mapping), clone_data($base_definitions));
}

my ($config, $mapping, $definitions) = base_case();
my ($exit, $output) = run_validator(config=>$config, mapping=>$mapping, definitions=>$definitions);
is($exit, 0, "valid generated configuration passes");
like($output, qr/<OK>/, "success marker is emitted");

($config, $mapping, $definitions) = base_case();
$config->{meters}->[0]->{enabled} = JSON::PP::false;
($exit, $output) = run_validator(config=>$config, mapping=>$mapping, definitions=>$definitions);
isnt($exit, 0, "vzLogger mode requires an active meter");
like($output, qr/No active meter/, "missing active meter is explained");

($config, $mapping, $definitions) = base_case();
$config->{local}->{port} = 70000;
($exit, $output) = run_validator(config=>$config, mapping=>$mapping, definitions=>$definitions);
like($output, qr/local\.port.*1 and 65535/, "port range is checked");

($config, $mapping, $definitions) = base_case();
$config->{mqtt}->{enabled} = JSON::PP::true;
$config->{mqtt}->{topic} = '$invalid/#';
$config->{mqtt}->{cafile} = "$dir/missing-ca";
$config->{mqtt}->{capath} = $dir;
($exit, $output) = run_validator(config=>$config, mapping=>$mapping, definitions=>$definitions);
like($output, qr/either mqtt\.cafile or mqtt\.capath/i, "mutually exclusive MQTT CA settings are rejected");
like($output, qr/wildcards/, "MQTT wildcards are rejected");
like($output, qr/must not start with \$/, "MQTT system topics are rejected");
like($output, qr/readable file/, "missing MQTT certificate file is rejected");

($config, $mapping, $definitions) = base_case();
$config->{meters}->[0]->{interval} = 60;
$config->{meters}->[0]->{aggtime} = 30;
$config->{meters}->[0]->{channels}->[0]->{aggmode} = "avg";
($exit, $output) = run_validator(config=>$config, mapping=>$mapping, definitions=>$definitions);
like($output, qr/aggtime \(30\).*interval \(60\)/, "aggtime must not be shorter than interval");

($config, $mapping, $definitions) = base_case();
$config->{meters}->[0]->{aggtime} = -1;
$config->{meters}->[0]->{channels}->[0]->{aggmode} = "avg";
($exit, $output) = run_validator(config=>$config, mapping=>$mapping, definitions=>$definitions);
like($output, qr/aggmode must be none/, "channel aggregation requires active meter aggregation");

($config, $mapping, $definitions) = base_case();
$config->{meters}->[0]->{protocol} = "d0";
$config->{meters}->[0]->{ackseq} = "123";
$config->{meters}->[0]->{wait_sync} = "middle";
$config->{meters}->[0]->{use_local_time} = JSON::PP::false;
($exit, $output) = run_validator(config=>$config, mapping=>$mapping, definitions=>$definitions);
like($output, qr/unsupported parameter use_local_time/, "protocol-foreign meter fields are rejected");
like($output, qr/ackseq must be empty, auto or an even-length/, "D0 ack sequence is validated");
like($output, qr/wait_sync must be off or end/, "D0 wait_sync enum is validated");

($config, $mapping, $definitions) = base_case();
$config->{meters}->[0]->{protocol} = "oms";
$config->{meters}->[0]->{channels}->[0]->{identifier} = "1.8.0*5";
delete @{$config->{meters}->[0]}{qw(interval parity)};
($exit, $output) = run_validator(config=>$config, mapping=>$mapping, definitions=>$definitions);
like($output, qr/must not contain a storage index for OMS/, "OMS rejects a storage index");

($config, $mapping, $definitions) = base_case();
$definitions->{meters}->{reader}->[0]->{api} = "influxdb";
$definitions->{meters}->{reader}->[0]->{api_options}->{influxdb} = { version=>2, host=>"https://influx", database=>"bucket" };
($exit, $output) = run_validator(config=>$config, mapping=>$mapping, definitions=>$definitions);
like($output, qr/organization is required for version 2/, "InfluxDB 2 organization is required");
like($output, qr/token is required for version 2/, "InfluxDB 2 token is required");

($config, $mapping, $definitions) = base_case();
$mapping->{$uuid}->{channel_index} = 4;
$mapping->{$uuid}->{channel} = "chn4";
($exit, $output) = run_validator(config=>$config, mapping=>$mapping, definitions=>$definitions);
like($output, qr/channel_index must be 0/, "mapping index must match generated channel order");
like($output, qr/channel must be chn0/, "mapping chn name must match generated channel order");

($config, $mapping, $definitions) = base_case();
$definitions->{meters}->{reader}->[0]->{plugin_output}->{enabled} = JSON::PP::false;
$mapping = {};
($exit, $output) = run_validator(config=>$config, mapping=>$mapping, definitions=>$definitions, read=>1);
like($output, qr/bridge is enabled but no active plugin output/i, "enabled bridge requires an output channel");

($config, $mapping, $definitions) = base_case();
$config->{meters}->[0]->{vendor_extension} = "preserved";
$config->{meters}->[0]->{channels}->[0]->{identifier} = "vendor-defined";
$config->{meters}->[0]->{channels}->[0]->{name} = "Vendor cache name";
$mapping->{$uuid}->{identifier} = "vendor-defined";
delete $mapping->{$uuid}->{managed_output};
$definitions->{meters} = {};
($exit, $output) = run_validator(config=>$config, mapping=>$mapping, definitions=>$definitions);
is($exit, 0, "custom JSON meter keeps protocol-specific extension fields and identifiers");

($config, $mapping, $definitions) = base_case();
$config->{meters} = [];
$definitions->{meters} = {};
$mapping = {};
($exit, $output) = run_validator(config=>$config, mapping=>$mapping, definitions=>$definitions, implementation=>"none");
is($exit, 0, "disabled vzLogger mode permits a meterless configuration");
like($output, qr/<WARNING> No meters/, "meterless disabled mode reports a warning");

done_testing();
