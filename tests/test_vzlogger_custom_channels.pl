#!/usr/bin/perl

use strict;
use warnings;
use File::Temp qw(tempdir);
use FindBin;
use JSON::PP;
use Test::More;
use lib "$FindBin::Bin/../bin";
use SmartMeterVZLoggerChannels qw(stable_uuid);
use SmartMeterVZLoggerCustomChannels qw(assign_custom_channel_uuids registry_file);

my $dir = tempdir(CLEANUP => 1);
my $meter = { channels => [
	{ identifier => "1-0:1.8.0", api => "null", name => "Import" },
	{ identifier => "1-0:2.8.0", api => "null", name => "Export" },
] };
my ($ok, $error) = assign_custom_channel_uuids($meter, "reader-1", "smartmeter-v2", $dir);
ok($ok, "initial custom UUID registry is created") or diag($error);
is($meter->{channels}->[0]->{uuid}, stable_uuid("smartmeter-v2:reader-1:0:1-0:1.8.0"), "first migration retains legacy UUID algorithm");
my %uuid_for = map { $_->{identifier} => $_->{uuid} } @{$meter->{channels}};
ok(-e registry_file($dir, "reader-1"), "versioned registry file exists");

my $reordered = { channels => [
	{ identifier => "1-0:2.8.0", api => "null", name => "Export" },
	{ identifier => "1-0:1.8.0", api => "null", name => "Import" },
] };
($ok, $error) = assign_custom_channel_uuids($reordered, "reader-1", "smartmeter-v2", $dir);
ok($ok, "registry accepts reordered channels") or diag($error);
is($reordered->{channels}->[0]->{uuid}, $uuid_for{"1-0:2.8.0"}, "export UUID survives reordering");
is($reordered->{channels}->[1]->{uuid}, $uuid_for{"1-0:1.8.0"}, "import UUID survives reordering");

my $explicit = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
my $explicit_meter = { channels => [{ identifier => "vendor", api => "null", uuid => $explicit }] };
($ok, $error) = assign_custom_channel_uuids($explicit_meter, "reader-2", "smartmeter-v2", $dir);
ok($ok, "explicit UUID is accepted") or diag($error);
is($explicit_meter->{channels}->[0]->{uuid}, $explicit, "explicit UUID takes precedence");

my $duplicate = { channels => [
	{ identifier => "a", uuid => $explicit }, { identifier => "b", uuid => $explicit },
] };
($ok, $error) = assign_custom_channel_uuids($duplicate, "reader-3", "smartmeter-v2", $dir);
ok(!$ok, "duplicate explicit UUID is rejected");
like($error, qr/duplicate/i, "duplicate UUID error is actionable");

my $changed = { channels => [{ identifier => "changed", api => "null", name => "Changed" }] };
($ok, $error) = assign_custom_channel_uuids($changed, "reader-1", "smartmeter-v2", $dir);
ok($ok, "changed channel content receives a registry entry") or diag($error);
isnt($changed->{channels}->[0]->{uuid}, $uuid_for{"1-0:1.8.0"}, "changed channel content does not reuse an unrelated UUID");

my $invalid_file = registry_file($dir, "reader-invalid");
open(my $invalid, ">", $invalid_file) or die $!;
print $invalid "not-json";
close($invalid);
my $recovered = { channels => [{ identifier => "1-0:1.8.0" }] };
($ok, $error) = assign_custom_channel_uuids($recovered, "reader-invalid", "smartmeter-v2", $dir);
ok($ok, "invalid registry is safely reinitialized") or diag($error);
ok($recovered->{channels}->[0]->{uuid}, "registry recovery assigns a UUID");

done_testing();
