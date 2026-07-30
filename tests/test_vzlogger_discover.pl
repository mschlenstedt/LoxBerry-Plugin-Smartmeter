#!/usr/bin/perl

use strict;
use warnings;
use File::Temp qw(tempdir);
use FindBin;
use JSON::PP;
use Test::More;

my $lib     = "$FindBin::Bin/../.github/ci/perl-lib";
my $bin     = "$FindBin::Bin/../bin";
my $script  = "$bin/vzlogger_discover.pl";
my $catalog = "$FindBin::Bin/../templates/obis_catalog.json";
my $dir     = tempdir(CLEANUP => 1);

# A sample vzLogger discovery log (verbosity 15 prints "Reading:" lines).
open(my $fh, ">", "$dir/disc.log") or die "cannot write log: $!";
print $fh <<'LOG';
<AutoDiscovery Haus> Got 3 new readings from meter:
<AutoDiscovery Haus> Reading: id=1-0:1.8.0*255/1-0:1.8.0*255 value=12345.67 ts=1700000000000
<AutoDiscovery Haus> Reading: id=1-0:16.7.0*255/1-0:16.7.0*255 value=421.00 ts=1700000000000
<AutoDiscovery Haus> Reading: id=1-0:1.8.0*255/1-0:1.8.0*255 value=12345.70 ts=1700000001000
<AutoDiscovery Haus> Reading: id=1-0:99.99.99*255/1-0:99.99.99*255 value=1.00 ts=1700000000000
<AutoDiscovery Haus> a line without any reading
LOG
close($fh);

$ENV{SMARTMETER_OBIS_CATALOG_FILE} = $catalog;

my $cmd = join(" ", map { "'$_'" } ($^X, "-I", $lib, "-I", $bin, $script, "--parse-only=$dir/disc.log"));
my $res = JSON::PP->new->decode(`$cmd`);
ok($res->{ok}, "parse-only succeeds");
my @ch = @{$res->{channels}};
is(scalar(@ch), 3, "distinct OBIS identifiers are found (duplicates collapsed)");
my %by = map { $_->{identifier} => $_->{name} } @ch;
is($by{"1-0:1.8.0"}, "Consumption_Total", "catalog output_name is used for 1-0:1.8.0");
ok(exists $by{"1-0:16.7.0"}, "1-0:16.7.0 is discovered");
ok(!exists $by{"1-0:1.8.0*255"}, "the *255 storage suffix is stripped");
# Not in the catalog: the OBIS code itself becomes the name (MQTT-safe).
is($by{"1-0:99.99.99"}, "1-0_99_99_99", "an unknown OBIS falls back to its sanitized code as the name");

done_testing();
