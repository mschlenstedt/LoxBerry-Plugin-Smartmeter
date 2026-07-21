package SmartMeterVZLoggerExpert;

use strict;
use warnings;
use Exporter qw(import);
use File::Basename qw(dirname);
use File::Path qw(make_path);
use JSON::PP;

our @EXPORT_OK = qw(
	read_text write_text_atomic validate_expert_text format_expert_validation
	build_expert_mapping update_expert_log_settings expert_configs_equal
);

sub read_text
{
	my ($file) = @_;
	return undef if (!defined($file) || !-e $file);
	open(my $fh, "<", $file) or return undef;
	binmode($fh, ":raw");
	local $/;
	my $text = <$fh>;
	close($fh);
	return $text;
}

sub write_text_atomic
{
	my ($file, $text) = @_;
	return 0 if (!defined($file) || !defined($text));
	my $directory = dirname($file);
	make_path($directory) if (!-d $directory);
	my $tmp = "$file.tmp.$$";
	open(my $fh, ">", $tmp) or return 0;
	binmode($fh, ":raw");
	print $fh $text;
	if (!close($fh)) {
		unlink($tmp);
		return 0;
	}
	my $mode = -e $file ? ((stat($file))[2] & 07777) : 0600;
	chmod($mode, $tmp);
	if (!rename($tmp, $file)) {
		unlink($tmp);
		return 0;
	}
	return 1;
}

sub validate_expert_text
{
	my ($text) = @_;
	my (@errors, @warnings);
	if (!defined($text) || $text eq "") {
		push @errors, "The expert configuration is empty.";
		return { valid => 0, errors => \@errors, warnings => \@warnings };
	}
	my $config = eval { JSON::PP->new->utf8->decode($text) };
	if ($@) {
		my $error = $@;
		$error =~ s/\s+at\s+\S+\s+line\s+\d+\.?\s*\z//;
		push @errors, "The expert configuration is not valid JSON: " . ($error || "unknown JSON error");
		return { valid => 0, errors => \@errors, warnings => \@warnings };
	}
	if (ref($config) ne "HASH") {
		push @errors, "The top-level expert configuration must be a JSON object.";
		return { valid => 0, errors => \@errors, warnings => \@warnings, config => $config };
	}

	my %known_root = map { $_ => 1 } qw(retry verbosity log local mqtt meters);
	push @warnings, "Unknown root parameter '$_' is retained for vzLogger."
		foreach grep { !$known_root{$_} } sort keys %$config;
	if (exists($config->{retry}) && !_integer($config->{retry}, 0, undef)) {
		push @errors, "retry must be a non-negative integer.";
	}
	if (exists($config->{verbosity}) && (!_integer($config->{verbosity}) || "$config->{verbosity}" !~ /\A(?:0|1|3|5|10|15)\z/)) {
		push @errors, "verbosity must be one of 0, 1, 3, 5, 10 or 15.";
	}
	if (exists($config->{log}) && (ref($config->{log}) || ($config->{log} ne "" && $config->{log} !~ m{\A/}))) {
		push @errors, "log must be an absolute path or an empty string.";
	}
	_validate_endpoint($config->{local}, "local", \@errors, \@warnings, 0);
	_validate_endpoint($config->{mqtt}, "mqtt", \@errors, \@warnings, 1);

	if (ref($config->{meters}) ne "ARRAY") {
		push @errors, "meters must be an array.";
	} else {
		my %uuids;
		for (my $i = 0; $i < @{$config->{meters}}; $i++) {
			my $meter = $config->{meters}->[$i];
			my $prefix = "meters[$i]";
			if (ref($meter) ne "HASH") {
				push @errors, "$prefix must be an object.";
				next;
			}
			push @errors, "$prefix.enabled must be a JSON boolean."
				if (exists($meter->{enabled}) && !JSON::PP::is_bool($meter->{enabled}));
			push @errors, "$prefix.protocol must be a non-empty string."
				if (!defined($meter->{protocol}) || ref($meter->{protocol}) || $meter->{protocol} eq "");
			if (exists($meter->{channels}) && ref($meter->{channels}) ne "ARRAY") {
				push @errors, "$prefix.channels must be an array.";
				next;
			}
			my $channels = ref($meter->{channels}) eq "ARRAY" ? $meter->{channels} : [];
			for (my $j = 0; $j < @$channels; $j++) {
				my $channel = $channels->[$j];
				my $label = "$prefix.channels[$j]";
				if (ref($channel) ne "HASH") {
					push @errors, "$label must be an object.";
					next;
				}
				my $uuid = defined($channel->{uuid}) && !ref($channel->{uuid}) ? "$channel->{uuid}" : "";
				if ($uuid eq "") {
					push @warnings, "$label has no UUID and cannot be published by the SmartMeter bridge.";
				} elsif ($uuid !~ /\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/i) {
					push @errors, "$label.uuid is malformed.";
				} elsif ($uuids{lc($uuid)}++) {
					push @errors, "$label.uuid is duplicated.";
				}
			}
		}
	}
	return {
		valid => @errors ? 0 : 1,
		errors => \@errors,
		warnings => \@warnings,
		config => $config,
	};
}

sub expert_configs_equal
{
	my ($left_text, $right_text) = @_;
	return 0 if (!defined($left_text) || !defined($right_text));
	my $left = eval { JSON::PP->new->utf8->decode($left_text) };
	return 0 if ($@ || ref($left) ne "HASH");
	my $right = eval { JSON::PP->new->utf8->decode($right_text) };
	return 0 if ($@ || ref($right) ne "HASH");
	my $json = JSON::PP->new->utf8->canonical;
	return $json->encode($left) eq $json->encode($right) ? 1 : 0;
}

sub _validate_endpoint
{
	my ($value, $name, $errors, $warnings, $mqtt) = @_;
	if (ref($value) ne "HASH") {
		push @$errors, "$name must be an object.";
		return;
	}
	push @$errors, "$name.enabled must be a JSON boolean."
		if (exists($value->{enabled}) && !JSON::PP::is_bool($value->{enabled}));
	if (exists($value->{port}) && !_integer($value->{port}, 1, 65535)) {
		push @$errors, "$name.port must be an integer between 1 and 65535.";
	}
	if ($mqtt && $value->{enabled}) {
		push @$errors, "mqtt.host is required when MQTT is enabled."
			if (!defined($value->{host}) || ref($value->{host}) || $value->{host} eq "");
		push @$errors, "mqtt.topic is required when MQTT is enabled."
			if (!defined($value->{topic}) || ref($value->{topic}) || $value->{topic} eq "");
		push @$errors, "mqtt.topic must not contain MQTT wildcards."
			if (defined($value->{topic}) && !ref($value->{topic}) && $value->{topic} =~ /[+#]/);
		push @$errors, "mqtt.pass requires mqtt.user."
			if (defined($value->{pass}) && !ref($value->{pass}) && $value->{pass} ne "" && (!defined($value->{user}) || ref($value->{user}) || $value->{user} eq ""));
		push @$errors, "mqtt.certfile and mqtt.keyfile must be configured together."
			if (!!_text($value->{certfile}) != !!_text($value->{keyfile}));
	}
}

sub _integer
{
	my ($value, $minimum, $maximum) = @_;
	return 0 if (!defined($value) || ref($value) || "$value" !~ /\A-?\d+\z/);
	return 0 if (defined($minimum) && $value < $minimum);
	return 0 if (defined($maximum) && $value > $maximum);
	return 1;
}

sub _text
{
	my ($value) = @_;
	return defined($value) && !ref($value) ? "$value" : "";
}

sub format_expert_validation
{
	my ($result) = @_;
	my $text = "";
	$text .= "<FAIL> $_\n" foreach @{$result->{errors} || []};
	$text .= "<WARNING> $_\n" foreach @{$result->{warnings} || []};
	$text .= "<OK> Expert vzLogger configuration validation passed.\n" if ($result->{valid});
	return $text;
}

sub build_expert_mapping
{
	my ($config, $existing) = @_;
	$existing = {} if (ref($existing) ne "HASH");
	my (%mapping, @warnings);
	my $index = 0;
	my $meters = ref($config) eq "HASH" && ref($config->{meters}) eq "ARRAY" ? $config->{meters} : [];
	for (my $meter_index = 0; $meter_index < @$meters; $meter_index++) {
		my $meter = $meters->[$meter_index];
		my $channels = ref($meter) eq "HASH" && ref($meter->{channels}) eq "ARRAY" ? $meter->{channels} : [];
		foreach my $channel (@$channels) {
			my $uuid = ref($channel) eq "HASH" ? _text($channel->{uuid}) : "";
			my $old = $uuid ne "" ? $existing->{$uuid} : undef;
			$old = $existing->{lc($uuid)} if (ref($old) ne "HASH" && $uuid ne "");
			if (ref($old) eq "HASH") {
				my %entry = %$old;
				$entry{identifier} = _text($channel->{identifier});
				$entry{channel} = "chn$index";
				$entry{channel_index} = $index;
				$mapping{$uuid} = \%entry;
			} elsif ($uuid ne "") {
				push @warnings, "Expert channel $uuid has no existing SmartMeter output mapping and will not be published by the bridge.";
			}
			$index++;
		}
	}
	return (\%mapping, \@warnings);
}

sub update_expert_log_settings
{
	my ($text, $verbosity, $log_file) = @_;
	my $validation = validate_expert_text($text);
	return (undef, $validation) if (!$validation->{valid});
	my $config = $validation->{config};
	$config->{verbosity} = 0 + $verbosity;
	$config->{log} = "$log_file";
	my $updated = JSON::PP->new->utf8->pretty->canonical->encode($config);
	return ($updated, validate_expert_text($updated));
}

1;
