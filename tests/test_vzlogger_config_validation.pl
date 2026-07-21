#!/usr/bin/perl

use strict;
use warnings;
use FindBin;
use Test::More;
use lib "$FindBin::Bin/../bin";
use SmartMeterVZLoggerConfig qw(validate_legacy_general normalized_meter_mode protocol_for_meter serial_mode sanitize_topic);

is(protocol_for_meter("generic-d0"), "d0", "shared protocol mapper recognizes D0");
is(normalized_meter_mode("manual", "sml"), "sml", "manual legacy mode maps through shared protocol mapper");
is(serial_mode(7, "even", 1), "7E1", "shared serial mode is canonical");
is(sanitize_topic(" /smartmeter/site/ "), "smartmeter/site", "shared topic normalization trims separators");

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
like(
	$legacy_source,
	qr/\$plugin_cfg->save if \(\$defaults_changed\)/,
	"Legacy page saves initialization defaults only when migration changed them",
);

done_testing();
