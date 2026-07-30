#!/usr/bin/perl

use strict;
use warnings;
use File::Temp qw(tempdir);
use FindBin;
use JSON::PP;
use Test::More;
use lib "$FindBin::Bin/../bin";
use SmartMeterIRHeads qw(load_data add_manual add_tibberpulse remove_manual usb_port_short);

my $dir = tempdir(CLEANUP => 1);

# The bulk of these tests use placeholder /dev device paths, so skip the
# device-existence check; a dedicated block below verifies that check on its own.
$ENV{SMARTMETER_IRHEAD_SKIP_DEVICE_CHECK} = 1;

sub read_manual
{
	my ($data) = load_data($dir);
	return $data->{manual};
}

# A fresh directory yields the empty structure.
my ($data) = load_data($dir);
is_deeply($data->{auto}, [], "auto list starts empty");
is_deeply($data->{manual}, [], "manual list starts empty");

# usb_port_short extracts the port from a udev ID_PATH.
is(usb_port_short("platform-xhci-hcd.0-usb-0:1.2:1.0"), "1.2", "USB port is extracted from a tty-interface ID_PATH");
is(usb_port_short("platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.4"), "1.4", "USB port is extracted from a device-level ID_PATH without interface suffix");
is(usb_port_short(""), "", "empty ID_PATH yields empty port");
is(usb_port_short("something-else"), "something-else", "unparsable ID_PATH falls back to the raw value");

# Adding a valid manual head.
my ($ok, $err) = add_manual($dir, "/dev/ttyUSB0", "Kitchen_Meter");
ok($ok, "a valid manual head is added");
is($err, "", "no error on a valid add");
my $manual = read_manual();
is(scalar(@$manual), 1, "one manual head is stored");
is($manual->[0]->{device}, "/dev/ttyUSB0", "device path is stored");
is($manual->[0]->{name}, "Kitchen_Meter", "name is stored");

# Invalid device path and name are rejected.
($ok, $err) = add_manual($dir, "not-a-dev-path", "Name");
ok(!$ok, "a non /dev path is rejected");
is($err, "UI_IRHEAD_INVALID_DEVICE", "invalid device reports the right key");

($ok, $err) = add_manual($dir, "/dev/ttyUSB1", "invalid name");
ok(!$ok, "a name with a space is rejected");
is($err, "UI_IRHEAD_INVALID_NAME", "invalid name reports the right key");

($ok, $err) = add_manual($dir, "/dev/ttyUSB1", "bad/char");
ok(!$ok, "a name with a slash is rejected");
is($err, "UI_IRHEAD_INVALID_NAME", "special characters in the name are rejected");

# Duplicate device or name is rejected.
($ok, $err) = add_manual($dir, "/dev/ttyUSB0", "Other_Name");
ok(!$ok, "a duplicate device is rejected");
is($err, "UI_IRHEAD_DUPLICATE", "duplicate device reports the right key");

($ok, $err) = add_manual($dir, "/dev/ttyUSB9", "Kitchen_Meter");
ok(!$ok, "a duplicate name is rejected");
is($err, "UI_IRHEAD_DUPLICATE", "duplicate name reports the right key");

# A second valid head can be added.
($ok, $err) = add_manual($dir, "/dev/serial/by-id/usb-abc", "Cellar-Meter");
ok($ok, "a second valid manual head with a hyphen name is added");
is(scalar(@{read_manual()}), 2, "two manual heads are stored");

# Removing by device path.
($ok, $err) = remove_manual($dir, "/dev/ttyUSB0");
ok($ok, "an existing manual head is removed");
$manual = read_manual();
is(scalar(@$manual), 1, "one manual head remains");
is($manual->[0]->{device}, "/dev/serial/by-id/usb-abc", "the correct head remains");

# Removing a non-existent device reports an error.
($ok, $err) = remove_manual($dir, "/dev/ttyUSB0");
ok(!$ok, "removing an absent head fails");
is($err, "UI_IRHEAD_NOT_FOUND", "absent head reports the right key");

# The stored file is valid JSON with the expected shape.
open(my $fh, "<", "$dir/irheads.json") or die "cannot read irheads.json: $!";
local $/;
my $raw = <$fh>;
close($fh);
my $stored = JSON::PP->new->decode($raw);
ok(ref($stored->{manual}) eq "ARRAY", "irheads.json keeps manual as an array");
ok(exists($stored->{auto}), "irheads.json keeps the auto key");

# The device-existence check (skipped above): a path that is not present under
# /dev is rejected, while an existing device node passes.
{
	my $edir = tempdir(CLEANUP => 1);
	delete local $ENV{SMARTMETER_IRHEAD_SKIP_DEVICE_CHECK};
	my ($mok, $merr) = add_manual($edir, "/dev/smartmeter_missing_xyz", "Ghost");
	ok(!$mok, "a non-existent device is rejected");
	is($merr, "UI_IRHEAD_DEVICE_MISSING", "missing device reports the right key");
	my ($rok) = add_manual($edir, "/dev/null", "Real_Dev");
	ok($rok, "an existing device (/dev/null) passes the existence check");
}

# Tibber Pulse: input validation happens before the network probe, and an
# unreachable bridge is reported (no real Tibber Pulse in CI).
{
	my $tdir = tempdir(CLEANUP => 1);
	my ($ok, $err) = add_tibberpulse($tdir, "bad name", "192.168.1.50", 1, "pw");
	is($err, "UI_IRHEAD_INVALID_NAME", "tibberpulse rejects an invalid name");
	($ok, $err) = add_tibberpulse($tdir, "Pulse", "bad host", 1, "pw");
	is($err, "UI_TIBBER_INVALID_HOST", "tibberpulse rejects an invalid host");
	($ok, $err) = add_tibberpulse($tdir, "Pulse", "192.168.1.50", "x", "pw");
	is($err, "UI_TIBBER_INVALID_NODE", "tibberpulse rejects a non-numeric node");
	($ok, $err) = add_tibberpulse($tdir, "Pulse", "127.0.0.1:1", 1, "pw");
	ok(!$ok, "tibberpulse add fails for an unreachable bridge");
	is($err, "UI_TIBBER_UNREACHABLE", "unreachable bridge reports the right key");
}

done_testing();
