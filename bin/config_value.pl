#!/usr/bin/perl

# Reads a single value from the JSON plugin configuration, so shell scripts do
# not have to parse JSON themselves.
#
# Usage:
#   config_value.pl <config file> <SECTION.KEY>     prints the value
#   config_value.pl <config file> --has-meter       exit 0 if a reader has a
#                                                   protocol configured
#
# Exit codes: 0 success, 1 no match, 2 wrong usage, 3 configuration unreadable.

use strict;
use warnings;
use FindBin;
use lib $FindBin::Bin;
use SmartMeterConfig;

my ($file, $what) = @ARGV;
exit 2 if (!defined($file) || !defined($what) || $file eq "" || $what eq "");
exit 3 if (!-e $file);

my $cfg = SmartMeterConfig->new($file);
exit 3 if (!$cfg);

if ($what eq "--has-meter") {
	my $meters = $cfg->meters() || {};
	foreach my $serial (keys %{$meters}) {
		my $meter = $meters->{$serial};
		next if (ref($meter) ne "HASH");
		my $value = $meter->{METER};
		exit 0 if (defined($value) && !ref($value) && $value ne "" && $value ne "0");
	}
	exit 1;
}

my $value = $cfg->param($what);
print(defined($value) && !ref($value) ? $value : "");
exit 0;
