#!/usr/bin/perl

# Migrates the plugin configuration to the current JSON format and applies
# key-level migrations. Safe to run repeatedly: every step checks first.
#
# Usage: migrate_config.pl <plugin config directory>
#
# 1. If only the old INI file (smartmeter.cfg) exists, it is converted to
#    smartmeter.json. MAIN and VZLOGGER become top-level objects, every other
#    section is a reader and moves into METERS. Values stay strings, so the
#    comparisons throughout the plugin keep behaving identically.
# 2. Settings of removed features are dropped and defaults for missing keys are
#    added.

use strict;
use warnings;
use FindBin;
use lib $FindBin::Bin;
use SmartMeterConfig;

my $configdir = shift @ARGV;
die "Usage: $0 <plugin config directory>\n" if (!defined($configdir) || $configdir eq "");

my $ini_file = "$configdir/smartmeter.cfg";
my $json_file = "$configdir/smartmeter.json";

if (!-e $json_file && -e $ini_file) {
	convert_ini_to_json($ini_file, $json_file);
}

if (!-e $json_file) {
	print "No configuration found in $configdir. Nothing to migrate.\n";
	exit 0;
}

my $cfg = SmartMeterConfig->new($json_file);
die "Could not read $json_file: " . SmartMeterConfig->error() . "\n" if (!$cfg);

my $changed = 0;

# Settings of features that no longer exist.
foreach my $obsolete (qw(MAIN.CRON MAIN.SENDMQTT MAIN.SENDUDP MAIN.UDPPORT MAIN.READ VZLOGGER.DEBUG VZLOGGER.UDPINTERVAL)) {
	next if (!defined($cfg->param($obsolete)));
	$cfg->delete($obsolete);
	$changed = 1;
	print "<INFO> Removed obsolete setting $obsolete\n";
}

# Legacy reader settings were kept next to the vzLogger ones.
foreach my $key ($cfg->param()) {
	next if ($key !~ /\.LEGACY_/);
	$cfg->delete($key);
	$changed = 1;
}

# A stored Legacy mode becomes inactive so vzLogger has to be enabled on purpose.
my $implementation = $cfg->param("MAIN.IMPLEMENTATION");
if (!defined($implementation) || $implementation !~ /\A(?:none|vzlogger)\z/) {
	$cfg->param("MAIN.IMPLEMENTATION", "none");
	$changed = 1;
	if (defined($implementation) && $implementation eq "legacy") {
		print "<WARNING> The Legacy implementation was removed. Meter reading is now inactive.\n";
		print "<WARNING> Open the plugin page and activate vzLogger to resume reading.\n";
	} else {
		print "<INFO> Set implementation mode to none\n";
	}
}

my %defaults = (
	"MAIN.MQTTTOPIC" => "smartmeter",
	"VZLOGGER.EXPERTMODE" => "0",
	"VZLOGGER.RETRY" => "30",
	"VZLOGGER.LOCALENABLED" => "1",
	"VZLOGGER.LOCALPORT" => "18080",
	"VZLOGGER.LOCALINDEX" => "1",
	"VZLOGGER.LOCALTIMEOUT" => "30",
	"VZLOGGER.LOCALBUFFER" => "-1",
	"VZLOGGER.VZLOGGERDEBUG" => "0",
	"VZLOGGER.LOGLEVEL" => "0",
	"VZLOGGER.MQTTENABLED" => "1",
	"VZLOGGER.MQTTKEEPALIVE" => "30",
	"VZLOGGER.MQTTRETAIN" => "1",
	"VZLOGGER.MQTTRAWANDAGG" => "0",
	"VZLOGGER.MQTTQOS" => "0",
	"VZLOGGER.MQTTTIMESTAMP" => "0",
);
foreach my $key (sort keys %defaults) {
	next if (defined($cfg->param($key)));
	$cfg->param($key, $defaults{$key});
	$changed = 1;
	print "<INFO> Added default $key\n";
}

if ($changed) {
	$cfg->save;
	print "<INFO> Migrated plugin configuration\n";
} else {
	print "<INFO> Plugin configuration is already up to date\n";
}
exit 0;

# Reads the Config::Simple style INI file without depending on Config::Simple
# and writes it as JSON. The INI format used here is plain: [SECTION] headers
# and KEY=VALUE lines, with ; and # starting a comment.
sub convert_ini_to_json
{
	my ($source, $target) = @_;
	open(my $fh, "<", $source) or die "Could not read $source: $!\n";
	my %sections;
	my $section = "MAIN";
	while (my $line = <$fh>) {
		$line =~ s/\r?\n\z//;
		$line =~ s/\A\s+|\s+\z//g;
		next if ($line eq "" || $line =~ /\A[;#]/);
		if ($line =~ /\A\[([^\]]+)\]\z/) {
			$section = $1;
			$sections{$section} ||= {};
			next;
		}
		my ($key, $value) = split(/=/, $line, 2);
		next if (!defined($value));
		$key =~ s/\A\s+|\s+\z//g;
		$value =~ s/\A\s+|\s+\z//g;
		# Config::Simple quotes values that contain spaces.
		$value = $1 if ($value =~ /\A"(.*)"\z/s);
		$sections{$section}->{$key} = $value;
	}
	close($fh);

	my $data = { MAIN => {}, VZLOGGER => {}, METERS => {} };
	foreach my $name (keys %sections) {
		if ($name eq "MAIN" || $name eq "VZLOGGER") {
			$data->{$name} = $sections{$name};
		} else {
			$data->{METERS}->{$name} = $sections{$name};
		}
	}

	my $cfg = SmartMeterConfig->create($target);
	die "Could not create $target: " . SmartMeterConfig->error() . "\n" if (!$cfg);
	%{$cfg->data()} = %$data;
	$cfg->save;

	# Keep the old file as a fallback instead of deleting user configuration.
	rename($source, "$source.pre-json");
	my $meters = scalar(keys %{$data->{METERS}});
	print "<INFO> Converted $source to JSON ($meters reader configuration(s)); kept a copy as $source.pre-json\n";
	return 1;
}
