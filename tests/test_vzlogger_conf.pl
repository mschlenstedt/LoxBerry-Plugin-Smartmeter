#!/usr/bin/perl

use strict;
use warnings;
use File::Temp qw(tempdir);
use FindBin;
use JSON::PP;
use Test::More;

my $lib    = "$FindBin::Bin/../.github/ci/perl-lib";
my $bin    = "$FindBin::Bin/../bin";
my $script = "$bin/vzlogger_conf.pl";
my $dir    = tempdir(CLEANUP => 1);

sub write_file
{
	my ($path, $content) = @_;
	open(my $fh, ">", $path) or die "cannot write $path: $!";
	print $fh $content;
	close($fh);
}

# A plain (non-TLS) LoxBerry MQTT gateway and a unique installation id.
write_file("$dir/mqtt.json", '{"brokerhost":"mqtt.example","brokerport":1884,"brokeruser":"gwuser","brokerpass":"gwpass","tls":0}');
write_file("$dir/loxberryid.cfg", "LB-UUID-123\n");

$ENV{SMARTMETER_CONFIG_DIR}      = $dir;
$ENV{SMARTMETER_MQTT_JSON}       = "$dir/mqtt.json";
$ENV{SMARTMETER_LOXBERRYID_FILE} = "$dir/loxberryid.cfg";
$ENV{SMARTMETER_LOGLEVEL}        = 6;

sub run_conf
{
	my (@args) = @_;
	my $cmd = join(" ", map { "'$_'" } ($^X, "-I", $lib, "-I", $bin, $script, @args));
	my $out = `$cmd`;
	return ($out, $? >> 8);
}

sub get_skeleton
{
	unlink("$dir/vzlogger.conf");
	my ($out, $rc) = run_conf("get");
	die "get failed" if ($rc != 0);
	return JSON::PP->new->decode($out);
}

# verbosity is derived from the plugin loglevel (LoxBerry 0-7 -> vzlogger).
$ENV{SMARTMETER_LOGLEVEL} = 6; is(get_skeleton()->{verbosity}, 5,  "loglevel 6 (info) -> verbosity 5");
$ENV{SMARTMETER_LOGLEVEL} = 7; is(get_skeleton()->{verbosity}, 10, "loglevel 7 (debug) -> verbosity 10");
$ENV{SMARTMETER_LOGLEVEL} = 4; is(get_skeleton()->{verbosity}, 3,  "loglevel 4 (warning) -> verbosity 3");
$ENV{SMARTMETER_LOGLEVEL} = 0; is(get_skeleton()->{verbosity}, 0,  "loglevel 0 (emerg) -> verbosity 0");
$ENV{SMARTMETER_LOGLEVEL} = 6;

# Default skeleton and automatic values.
my $sk = get_skeleton();
is($sk->{mqtt}{topic}, "smartmeter-ng", "default base topic is smartmeter-ng");
is($sk->{local}{port}, 18080, "default local port is 18080");
ok($sk->{local}{enabled}, "local httpd is enabled");
is($sk->{retry}, 30, "default retry is 30");
is($sk->{mqtt}{host}, "mqtt.example", "MQTT host from the gateway");
is($sk->{mqtt}{port}, 1884, "MQTT plain port from the gateway");
is($sk->{mqtt}{user}, "gwuser", "MQTT user from the gateway");
is($sk->{mqtt}{qos}, 0, "qos is fixed at 0");
ok($sk->{mqtt}{retain}, "retain is on");
ok($sk->{mqtt}{timestamp}, "timestamp is on");
ok($sk->{mqtt}{rawAndAgg}, "rawAndAgg is on");
is($sk->{mqtt}{id}, "smartmeter-ng-LB-UUID-123", "client id carries the LoxBerry uuid");
ok(!exists $sk->{push}, "push is never written");
is(ref($sk->{meters}), "ARRAY", "meters is an array");

# Without a loxberryid.cfg (send-statistics off) the client id stays plain.
$ENV{SMARTMETER_LOXBERRYID_FILE} = "$dir/does-not-exist.cfg";
is(get_skeleton()->{mqtt}{id}, "smartmeter-ng", "client id falls back to smartmeter-ng without a LoxBerry id");
$ENV{SMARTMETER_LOXBERRYID_FILE} = "$dir/loxberryid.cfg";

# save keeps the meter but forces the automatic MQTT connection.
write_file("$dir/in.json", JSON::PP->new->encode({
	retry  => 30,
	local  => { port => 18080 },
	mqtt   => { topic => "smartmeter-ng", host => "attacker", user => "eve" },
	meters => [ { enabled => JSON::PP::true, protocol => "sml", device => "/dev/ttyUSB0", channels => [] } ],
}));
my ($out, $rc) = run_conf("save", "$dir/in.json");
is($rc, 0, "save exits cleanly");
my $saved = JSON::PP->new->decode($out);
is(scalar(@{$saved->{meters}}), 1, "the meter is stored");
is($saved->{mqtt}{host}, "mqtt.example", "UI cannot override the MQTT host");
is($saved->{mqtt}{user}, "gwuser", "UI cannot override the MQTT user");

# set-settings changes the three user values and keeps the meter.
write_file("$dir/patch.json", JSON::PP->new->encode({ retry => 60, local => { port => 9090 }, mqtt => { topic => "haus" } }));
($out, $rc) = run_conf("set-settings", "$dir/patch.json");
is($rc, 0, "set-settings exits cleanly");
my $s2 = JSON::PP->new->decode($out);
is($s2->{retry}, 60, "retry updated");
is($s2->{local}{port}, 9090, "local port updated");
is($s2->{mqtt}{topic}, "haus", "base topic updated");
is(scalar(@{$s2->{meters}}), 1, "set-settings keeps the meter");
is($s2->{mqtt}{host}, "mqtt.example", "connection still from the gateway");

# TLS gateway: use the TLS port and point cafile at the local CA.
write_file("$dir/mqtt.json", '{"brokerhost":"broker","brokerport":1883,"tls":1,"tls_brokerport":8883,"tls_cafile":"/etc/mosquitto/tls/ca.crt"}');
my $t = get_skeleton();
is($t->{mqtt}{port}, 8883, "TLS broker port is used");
is($t->{mqtt}{cafile}, "/etc/mosquitto/tls/ca.crt", "cafile points at the local CA");

# --- Meters --------------------------------------------------------------
unlink("$dir/vzlogger.conf");

# Add an SML meter; empty free-text fields are omitted.
write_file("$dir/m1.json", JSON::PP->new->encode({
	name => "Haus", enabled => "1", protocol => "sml", device => "/dev/ttyUSB0",
	interval => "-1", baudrate => "9600", parity => "8n1", pullseq => "", host => "", use_local_time => "0",
}));
($out, $rc) = run_conf("add-meter", "$dir/m1.json");
is($rc, 0, "add-meter exits cleanly");
my $c = JSON::PP->new->decode($out);
ok(!$c->{error_key}, "add-meter reports no error");
is(scalar(@{$c->{meters}}), 1, "one meter stored");
is($c->{meters}[0]{name}, "Haus", "meter name kept as extra key");
is($c->{meters}[0]{protocol}, "sml", "protocol stored");
is($c->{meters}[0]{device}, "/dev/ttyUSB0", "device stored");
is($c->{meters}[0]{baudrate}, 9600, "baudrate stored");
is($c->{meters}[0]{aggtime}, -1, "aggtime forced to -1");
ok(!exists $c->{meters}[0]{host}, "empty host is omitted");
ok(!exists $c->{meters}[0]{pullseq}, "empty pullseq is omitted");
is(ref($c->{meters}[0]{channels}), "ARRAY", "channels is an array");

# Duplicate name / device / invalid name are rejected.
write_file("$dir/m2.json", JSON::PP->new->encode({ name => "Haus", protocol => "sml", device => "/dev/ttyUSB9" }));
is(JSON::PP->new->decode((run_conf("add-meter", "$dir/m2.json"))[0])->{error_key}, "UI_METER_DUPLICATE_NAME", "duplicate name rejected");
write_file("$dir/m3.json", JSON::PP->new->encode({ name => "Zwei", protocol => "sml", device => "/dev/ttyUSB0" }));
is(JSON::PP->new->decode((run_conf("add-meter", "$dir/m3.json"))[0])->{error_key}, "UI_METER_DUPLICATE_DEVICE", "duplicate device rejected");
write_file("$dir/m4.json", JSON::PP->new->encode({ name => "bad name", protocol => "sml", device => "/dev/ttyUSB1" }));
is(JSON::PP->new->decode((run_conf("add-meter", "$dir/m4.json"))[0])->{error_key}, "UI_METER_INVALID_NAME", "invalid name rejected");

# Update it to OMS with an AES key.
write_file("$dir/u1.json", JSON::PP->new->encode({
	original_name => "Haus", name => "Keller", enabled => "1", protocol => "oms",
	device => "/dev/ttyUSB0", key => "0102030405060708090a0b0c0d0e0f10", use_local_time => "1",
}));
$c = JSON::PP->new->decode((run_conf("update-meter", "$dir/u1.json"))[0]);
is(scalar(@{$c->{meters}}), 1, "still one meter after update");
is($c->{meters}[0]{name}, "Keller", "meter renamed");
is($c->{meters}[0]{protocol}, "oms", "protocol changed to oms");
is($c->{meters}[0]{key}, "0102030405060708090a0b0c0d0e0f10", "AES key stored");

# Remove it.
write_file("$dir/r1.json", JSON::PP->new->encode({ name => "Keller" }));
$c = JSON::PP->new->decode((run_conf("remove-meter", "$dir/r1.json"))[0]);
is(scalar(@{$c->{meters}}), 0, "meter removed");

# Random test meter: no device required, min/max written as JSON doubles.
unlink("$dir/vzlogger.conf");
write_file("$dir/rnd.json", JSON::PP->new->encode({
	name => "Test", enabled => "1", protocol => "random", interval => "2", min => "5", max => "40",
}));
($out, $rc) = run_conf("add-meter", "$dir/rnd.json");
is($rc, 0, "add random meter exits cleanly");
like($out, qr/"min"\s*:\s*5\.0/, "min is written as a JSON double");
like($out, qr/"max"\s*:\s*40\.0/, "max is written as a JSON double");
$c = JSON::PP->new->decode($out);
ok(!$c->{error_key}, "random meter is accepted without a device");
is($c->{meters}[0]{protocol}, "random", "random protocol stored");
ok(!exists $c->{meters}[0]{device}, "random meter has no device");

# Exec test meter: command required, no device, empty format omitted.
unlink("$dir/vzlogger.conf");
write_file("$dir/ex1.json", JSON::PP->new->encode({
	name => "Exec1", enabled => "1", protocol => "exec", interval => "5", command => "/usr/bin/mycmd", format => "",
}));
$c = JSON::PP->new->decode((run_conf("add-meter", "$dir/ex1.json"))[0]);
ok(!$c->{error_key}, "exec meter is accepted");
is($c->{meters}[0]{protocol}, "exec", "exec protocol stored");
is($c->{meters}[0]{command}, "/usr/bin/mycmd", "command stored");
ok(!exists $c->{meters}[0]{device}, "exec meter has no device");
ok(!exists $c->{meters}[0]{format}, "empty format is omitted");

# Exec without a command is rejected.
write_file("$dir/ex2.json", JSON::PP->new->encode({ name => "Exec2", protocol => "exec" }));
is(JSON::PP->new->decode((run_conf("add-meter", "$dir/ex2.json"))[0])->{error_key}, "UI_METER_COMMAND_REQUIRED", "exec without command rejected");

# --- Channels ------------------------------------------------------------
unlink("$dir/vzlogger.conf");
write_file("$dir/cm.json", JSON::PP->new->encode({ name => "Haus", protocol => "sml", device => "/dev/ttyUSB0" }));
run_conf("add-meter", "$dir/cm.json");

write_file("$dir/ca.json", JSON::PP->new->encode({ meter => "Haus", identifier => "1-0:1.8.0", name => "Bezug" }));
$c = JSON::PP->new->decode((run_conf("add-channel", "$dir/ca.json"))[0]);
ok(!$c->{error_key}, "channel added");
my $chs = $c->{meters}[0]{channels};
is(scalar(@$chs), 1, "one channel stored");
is($chs->[0]{api}, "null", "channel api is null");
is($chs->[0]{identifier}, "1-0:1.8.0", "identifier stored");
is($chs->[0]{name}, "Bezug", "channel name stored");
is($chs->[0]{aggmode}, "none", "aggmode is always none");
is($chs->[0]{mqtt_topic}, "Haus/Bezug", "mqtt_topic is meter/channel");
like($chs->[0]{uuid}, qr/\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/, "uuid has a valid format");
my $ch_uuid = $chs->[0]{uuid};

write_file("$dir/ca2.json", JSON::PP->new->encode({ meter => "Haus", identifier => "1-0:2.8.0", name => "Bezug" }));
is(JSON::PP->new->decode((run_conf("add-channel", "$dir/ca2.json"))[0])->{error_key}, "UI_CHANNEL_DUPLICATE_NAME", "duplicate channel name rejected");

write_file("$dir/ca3.json", JSON::PP->new->encode({ meter => "Nope", identifier => "1-0:1.8.0", name => "X" }));
is(JSON::PP->new->decode((run_conf("add-channel", "$dir/ca3.json"))[0])->{error_key}, "UI_CHANNEL_METER_NOT_FOUND", "channel for unknown meter rejected");

# Renaming the meter updates the channel mqtt_topic and keeps the uuid.
write_file("$dir/ren.json", JSON::PP->new->encode({ original_name => "Haus", name => "Keller", protocol => "sml", device => "/dev/ttyUSB0" }));
$c = JSON::PP->new->decode((run_conf("update-meter", "$dir/ren.json"))[0]);
is($c->{meters}[0]{channels}[0]{mqtt_topic}, "Keller/Bezug", "mqtt_topic follows the meter rename");
is($c->{meters}[0]{channels}[0]{uuid}, $ch_uuid, "channel uuid stays stable across rename");

write_file("$dir/cr.json", JSON::PP->new->encode({ meter => "Keller", uuid => $ch_uuid }));
$c = JSON::PP->new->decode((run_conf("remove-channel", "$dir/cr.json"))[0]);
is(scalar(@{$c->{meters}[0]{channels}}), 0, "channel removed");

# add-channels adds several at once, skipping invalid and existing names.
write_file("$dir/cb.json", JSON::PP->new->encode({ name => "Multi", protocol => "sml", device => "/dev/ttyUSB2" }));
run_conf("add-meter", "$dir/cb.json");
write_file("$dir/cbatch.json", JSON::PP->new->encode({
	meter    => "Multi",
	channels => [ { identifier => "1-0:1.8.0", name => "Bezug" }, { identifier => "1-0:2.8.0", name => "Lieferung" }, { identifier => "x", name => "bad name" } ],
}));
$c = JSON::PP->new->decode((run_conf("add-channels", "$dir/cbatch.json"))[0]);
my ($mm) = grep { $_->{name} eq "Multi" } @{$c->{meters}};
is(scalar(@{$mm->{channels}}), 2, "two valid channels added, the invalid one skipped");

done_testing();
