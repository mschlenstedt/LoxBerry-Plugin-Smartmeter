#!/usr/bin/perl

use strict;
use warnings;

use Config::Simple;
use FindBin;
use JSON::PP;
use LoxBerry::System;
use lib $FindBin::Bin;
use SmartMeterVZLoggerChannels qw(validate_document);

my $home = $lbhomedir;
my $psubfolder = $lbpplugindir;
my $plugin_config_dir = $ENV{SMARTMETER_CONFIG_DIR} || "$home/config/plugins/$psubfolder";
my $plugin_config_file = $ENV{SMARTMETER_CONFIG_FILE} || "$plugin_config_dir/smartmeter.cfg";
my $config_file = $ENV{SMARTMETER_VZLOGGER_CONFIG_FILE} || "$plugin_config_dir/vzlogger.conf";
my $mapping_file = $ENV{SMARTMETER_VZLOGGER_MAPPING_FILE} || "$plugin_config_dir/vzlogger_channels.json";
my $definitions_file = $ENV{SMARTMETER_VZLOGGER_DEFINITIONS_FILE} || "$plugin_config_dir/vzlogger_channel_definitions.json";

my @errors;
my @warnings;

my $config = read_json_file($config_file, "vzLogger config");
my $mapping = read_json_file($mapping_file, "channel mapping");
my $definitions = read_json_file($definitions_file, "channel definitions");

if ($config) {
	validate_config($config);
}
if ($mapping) {
	validate_mapping($mapping);
}
push @errors, validate_document($definitions) if ($definitions);

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
		if (vzlogger_mode_enabled()) {
			push @errors, "No meter preset is configured. Select a meter for at least one detected I/R head before starting vzLogger.";
		} else {
			push @warnings, "No meters are configured because the vzLogger implementation is disabled.";
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

		push @errors, "$prefix.protocol must be a non-empty string." if (!defined($meter->{protocol}) || ref($meter->{protocol}) || $meter->{protocol} eq "");
		push @errors, "$prefix.protocol oms is not supported by the installed vzLogger." if (defined($meter->{protocol}) && !ref($meter->{protocol}) && $meter->{protocol} eq "oms" && !vzlogger_supports_protocol("oms"));
		foreach my $field (qw(baudrate baudrate_read)) {
			next if (!exists($meter->{$field}));
			push @errors, "$prefix.$field must be a positive integer no greater than 4000000." if (!is_positive_integer($meter->{$field}, 4000000));
		}
		if (!exists($meter->{channels})) {
			next;
		}
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

	my %output_keys;
	foreach my $uuid (keys %$mapping) {
		my $entry = $mapping->{$uuid};
		push @errors, "Mapping key $uuid is not a UUID." if ($uuid !~ /\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/i);
		if (ref($entry) ne "HASH") {
			push @errors, "Mapping entry $uuid must be a JSON object.";
			next;
		}
		push @errors, "Mapping entry $uuid has no serial." if (!defined($entry->{serial}) || $entry->{serial} eq "");
		push @errors, "Mapping entry $uuid has no name." if (!defined($entry->{name}) || $entry->{name} eq "");
		push @errors, "Mapping entry $uuid has an invalid output key." if ($entry->{managed_output} && defined($entry->{name}) && $entry->{name} !~ /\A[A-Za-z0-9_]{1,64}\z/);
		push @errors, "Mapping output key $entry->{name} is duplicated for meter $entry->{serial}." if ($entry->{managed_output} && defined($entry->{name}) && defined($entry->{serial}) && $output_keys{lc("$entry->{serial}\0$entry->{name}")}++);
		push @warnings, "Mapping entry $uuid has no identifier." if (!defined($entry->{identifier}) || $entry->{identifier} eq "");
	}
}

sub is_port
{
	my ($value) = @_;
	return defined($value) && $value =~ /\A\d+\z/ && $value > 0 && $value <= 65535;
}

sub is_positive_integer
{
	my ($value, $maximum) = @_;
	return defined($value) && !ref($value) && "$value" =~ /\A\d+\z/ && $value > 0 && $value <= $maximum;
}

sub vzlogger_supports_protocol
{
	my ($protocol) = @_;
	return 0 if (!command_exists("vzlogger"));
	my $help = `vzlogger -h 2>&1`;
	return $help =~ /^\s*\Q$protocol\E\s+/mi ? 1 : 0;
}

sub command_exists
{
	my ($command) = @_;
	foreach my $dir (split(/:/, $ENV{PATH} || "")) {
		return 1 if (-x "$dir/$command");
	}
	return 0;
}

sub vzlogger_mode_enabled
{
	my %plugin_config;
	return 0 if (!-e $plugin_config_file);
	Config::Simple->import_from($plugin_config_file, \%plugin_config);
	return (($plugin_config{"MAIN.IMPLEMENTATION"} || "") eq "vzlogger") ? 1 : 0;
}
