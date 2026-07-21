#!/usr/bin/perl

use strict;
use warnings;
use FindBin;
use Test::More;
use lib "$FindBin::Bin/../bin";
use SmartMeterVZLoggerBridge qw(parse_reading channel_mapping identifier_mapping clean_scalar_payload);

my $uuid = "11111111-2222-3333-4444-555555555555";
my $second = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
my $mapping = {
	$uuid => { serial => "reader", name => "Import", identifier => "1-0:1.8.0", channel_index => 0 },
	$second => { serial => "reader", name => "Import2", identifier => "1-0:1.8.0", channel => "chn1", identifier_ambiguous => 1 },
};
my %channels = channel_mapping($mapping);
is($channels{chn0}, $uuid, "channel index fallback is mapped");
is($channels{chn1}, $second, "explicit channel name is mapped");
my %identifiers = identifier_mapping($mapping);
is($identifiers{"1-0:1.8.0"}, $uuid, "non-ambiguous identifier maps to UUID");

my @debug;
my $reading = parse_reading("smartmeter/vzlogger/chn0/raw", "123.5", $mapping, \%channels, sub { push @debug, @_ });
is($reading->{uuid}, $uuid, "raw chnN topic resolves through channel mapping");
is($reading->{value}, "123.5", "numeric scalar payload is retained");
$reading = parse_reading("smartmeter/vzlogger/$uuid", '{"uuid":"' . $uuid . '","value":42,"timestamp":1700000000}', $mapping, \%channels);
is($reading->{timestamp}, 1700000000, "JSON timestamp is parsed");
is($reading->{value}, 42, "JSON value is parsed");
ok(!parse_reading("smartmeter/vzlogger/chn9/raw", "12", $mapping, \%channels, sub { push @debug, @_ }), "unknown channel is ignored");
like(join("\n", @debug), qr/no uuid/i, "ignored message explains mapping failure");
is(clean_scalar_payload('"1-0:1.8.0"'), "1-0:1.8.0", "JSON string payload is unwrapped");

done_testing();
