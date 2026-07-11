#!/usr/bin/perl

use strict;
use warnings;

use Config::Simple;
use JSON::PP;
use LoxBerry::System;

my $home = $lbhomedir;
my $psubfolder = $lbpplugindir;
my $plugin_config_file = "$home/config/plugins/$psubfolder/smartmeter.cfg";
my $config_file = "$home/config/plugins/$psubfolder/vzlogger.conf";
my $mapping_file = "$home/config/plugins/$psubfolder/vzlogger_channels.json";

my @errors;
my @warnings;

my $config = read_json_file($config_file, "vzLogger config");
my $mapping = read_json_file($mapping_file, "channel mapping");

if ($config) {
	validate_config($config);
}
if ($mapping) {
	validate_mapping($mapping);
}

if (@errors) {
	foreach my $error (@errors) {
		print "<FAIL> $error\n";
	}
	foreach my $warning (@warnings) {
		print "<WARNING> $warning\n";
	}
	exit 1;
}

foreach my $warning (@warnings) {
	print "<WARNING> $warning\n";
}
print "<OK> vzLogger configuration validation passed.\n";
exit 0;

sub read_json_file
{
	my ($file, $label) = @_;
	if (!-e $file) {
		push @errors, "$label file is missing: $file";
		return undef;
	}

	open(my $fh, "<", $file) or do {
		push @errors, "Could not open $label file $file: $!";
		return undef;
	};
	local $/;
	my $text = <$fh>;
	close($fh);

	my $data = eval { JSON::PP->new->utf8->decode($text) };
	if ($@) {
		push @errors, "$label file is not valid JSON: $@";
		return undef;
	}
	return $data;
}

sub validate_config
{
	my ($config) = @_;

	push @errors, "Top-level config must be a JSON object." if (ref($config) ne "HASH");
	return if (ref($config) ne "HASH");

	push @errors, "mqtt section is missing." if (ref($config->{mqtt}) ne "HASH");
	push @errors, "local section is missing." if (ref($config->{local}) ne "HASH");
	push @errors, "meters section must be an array." if (ref($config->{meters}) ne "ARRAY");
	return if (ref($config->{meters}) ne "ARRAY");

	if (!@{$config->{meters}}) {
		if (vzlogger_meter_reading_enabled()) {
			push @errors, "No meter preset is configured. Select a meter for at least one detected I/R head before starting vzLogger.";
		} else {
			push @warnings, "No meters are configured because vzLogger meter reading is disabled.";
		}
	}

	if (ref($config->{mqtt}) eq "HASH") {
		push @errors, "mqtt.host is missing." if (!defined($config->{mqtt}->{host}) || $config->{mqtt}->{host} eq "");
		push @errors, "mqtt.port is missing or invalid." if (!is_port($config->{mqtt}->{port}));
		push @errors, "mqtt.topic is missing." if (!defined($config->{mqtt}->{topic}) || $config->{mqtt}->{topic} eq "");
	}

	if (ref($config->{local}) eq "HASH") {
		push @errors, "local.port is missing or invalid." if (!is_port($config->{local}->{port}));
	}

	my %uuid_seen;
	for (my $i = 0; $i < @{$config->{meters}}; $i++) {
		my $meter = $config->{meters}->[$i];
		my $prefix = "meters[$i]";

		if (ref($meter) ne "HASH") {
			push @errors, "$prefix must be a JSON object.";
			next;
		}

		push @errors, "$prefix.protocol must be sml or d0." if (!defined($meter->{protocol}) || $meter->{protocol} !~ /\A(?:sml|d0)\z/);
		push @errors, "$prefix.device is missing." if (!defined($meter->{device}) || $meter->{device} eq "");
		push @errors, "$prefix.channels must be an array." if (ref($meter->{channels}) ne "ARRAY");
		next if (ref($meter->{channels}) ne "ARRAY");
		push @warnings, "$prefix has no channels." if (!@{$meter->{channels}});

		for (my $j = 0; $j < @{$meter->{channels}}; $j++) {
			my $channel = $meter->{channels}->[$j];
			my $channel_prefix = "$prefix.channels[$j]";
			if (ref($channel) ne "HASH") {
				push @errors, "$channel_prefix must be a JSON object.";
				next;
			}
			push @errors, "$channel_prefix.uuid is missing or malformed." if (!defined($channel->{uuid}) || $channel->{uuid} !~ /\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/i);
			push @errors, "$channel_prefix.identifier is missing." if (!defined($channel->{identifier}) || $channel->{identifier} eq "");
			if (defined($channel->{uuid})) {
				push @errors, "$channel_prefix.uuid is duplicated." if ($uuid_seen{$channel->{uuid}}++);
			}
		}
	}
}

sub validate_mapping
{
	my ($mapping) = @_;
	if (ref($mapping) ne "HASH") {
		push @errors, "Channel mapping must be a JSON object.";
		return;
	}

	foreach my $uuid (keys %$mapping) {
		my $entry = $mapping->{$uuid};
		push @errors, "Mapping key $uuid is not a UUID." if ($uuid !~ /\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/i);
		if (ref($entry) ne "HASH") {
			push @errors, "Mapping entry $uuid must be a JSON object.";
			next;
		}
		push @errors, "Mapping entry $uuid has no serial." if (!defined($entry->{serial}) || $entry->{serial} eq "");
		push @errors, "Mapping entry $uuid has no name." if (!defined($entry->{name}) || $entry->{name} eq "");
		push @errors, "Mapping entry $uuid has no identifier." if (!defined($entry->{identifier}) || $entry->{identifier} eq "");
	}
}

sub is_port
{
	my ($value) = @_;
	return defined($value) && $value =~ /\A\d+\z/ && $value > 0 && $value <= 65535;
}

sub vzlogger_meter_reading_enabled
{
	my %plugin_config;
	return 0 if (!-e $plugin_config_file);
	Config::Simple->import_from($plugin_config_file, \%plugin_config);
	return 0 if (($plugin_config{"MAIN.IMPLEMENTATION"} || "") ne "vzlogger");
	return (($plugin_config{"MAIN.READ"} || "0") eq "1") ? 1 : 0;
}
