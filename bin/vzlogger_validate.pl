#!/usr/bin/perl

use strict;
use warnings;

use Config::Simple;
use File::Basename qw(dirname);
use FindBin;
use JSON::PP;
use LoxBerry::System;
use lib $FindBin::Bin;
use SmartMeterVZLoggerChannels qw(compose_obis parse_obis validate_document valid_output_key output_key_format);

my $home = $lbhomedir;
my $psubfolder = $lbpplugindir;
my $plugin_config_dir = $ENV{SMARTMETER_CONFIG_DIR} || "$home/config/plugins/$psubfolder";
my $plugin_config_file = $ENV{SMARTMETER_CONFIG_FILE} || "$plugin_config_dir/smartmeter.cfg";
my $config_file = $ENV{SMARTMETER_VZLOGGER_CONFIG_FILE} || "$plugin_config_dir/vzlogger.conf";
my $mapping_file = $ENV{SMARTMETER_VZLOGGER_MAPPING_FILE} || "$plugin_config_dir/vzlogger_channels.json";
my $definitions_file = $ENV{SMARTMETER_VZLOGGER_DEFINITIONS_FILE} || "$plugin_config_dir/vzlogger_channel_definitions.json";

my (@errors, @warnings);
my $config = read_json_file($config_file, "vzLogger config");
my $mapping = read_json_file($mapping_file, "channel mapping");
my $definitions = read_json_file($definitions_file, "channel definitions");
my $native_channels = [];

$native_channels = validate_config($config, $mapping) if ($config);
push @errors, validate_document($definitions) if ($definitions);
validate_mapping($mapping, $native_channels, $definitions) if ($mapping);

if (@errors) {
	print "<FAIL> $_\n" foreach @errors;
	print "<WARNING> $_\n" foreach @warnings;
	exit 1;
}

print "<WARNING> $_\n" foreach @warnings;
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
	my ($config, $mapping) = @_;
	my @native;
	if (ref($config) ne "HASH") {
		push @errors, "Top-level config must be a JSON object.";
		return \@native;
	}
	validate_known_keys($config, "root", [qw(retry verbosity log local mqtt meters)]);
	validate_integer_range($config->{retry}, "retry", 0, undef);
	push @warnings, "retry is unusually large ($config->{retry} seconds)." if (is_integer($config->{retry}) && $config->{retry} > 86400);
	push @errors, "verbosity must be one of 0, 1, 3, 5, 10 or 15."
		if (!is_integer($config->{verbosity}) || $config->{verbosity} !~ /\A(?:0|1|3|5|10|15)\z/);
	push @errors, "log must be an absolute path or an empty string."
		if (defined($config->{log}) && (ref($config->{log}) || ($config->{log} ne "" && $config->{log} !~ m{\A/})));

	validate_local($config->{local});
	validate_mqtt($config->{mqtt});
	if (ref($config->{meters}) ne "ARRAY") {
		push @errors, "meters section must be an array.";
		return \@native;
	}

	my $mode_enabled = vzlogger_mode_enabled();
	my $active_meters = grep { ref($_) eq "HASH" && $_->{enabled} } @{$config->{meters}};
	if ($mode_enabled && !$active_meters) {
		push @errors, "No active meter is configured. Enable and configure at least one meter before starting vzLogger.";
	} elsif (!$mode_enabled && !@{$config->{meters}}) {
		push @warnings, "No meters are configured because the vzLogger implementation is disabled.";
	}

	my (%uuid_seen, %device_seen);
	my %custom_channel_indices = map {
		my $entry = $mapping->{$_};
		(ref($entry) eq "HASH" && !exists($entry->{managed_output}) && is_integer($entry->{channel_index})) ? ($entry->{channel_index} => 1) : ()
	} keys %{ref($mapping) eq "HASH" ? $mapping : {}};
	my $channel_index = 0;
	for (my $i = 0; $i < @{$config->{meters}}; $i++) {
		my $meter = $config->{meters}->[$i];
		my $prefix = "meters[$i]";
		if (ref($meter) ne "HASH") {
			push @errors, "$prefix must be a JSON object.";
			next;
		}
		my $channels = $meter->{channels};
		my $channel_count = ref($channels) eq "ARRAY" ? scalar(@$channels) : 0;
		my $custom_meter = grep { $custom_channel_indices{$_} } ($channel_index .. ($channel_index + $channel_count - 1));
		validate_meter($meter, $prefix, \%device_seen, $custom_meter ? 1 : 0);
		next if (ref($channels) ne "ARRAY");
		push @warnings, "$prefix is active but has no channels; this is valid for OBIS discovery only."
			if ($meter->{enabled} && !@$channels);
		for (my $j = 0; $j < @$channels; $j++) {
			my $channel = $channels->[$j];
			my $channel_prefix = "$prefix.channels[$j]";
			if (ref($channel) ne "HASH") {
				push @errors, "$channel_prefix must be a JSON object.";
				$channel_index++;
				next;
			}
			validate_native_channel($channel, $channel_prefix, $meter, $custom_meter ? 1 : 0);
			my $uuid = scalar_text($channel->{uuid});
			push @errors, "$channel_prefix.uuid is duplicated across the configuration."
				if ($uuid ne "" && $uuid_seen{lc($uuid)}++);
			push @native, {
				uuid => $uuid,
				identifier => scalar_text($channel->{identifier}),
				index => $channel_index,
			};
			$channel_index++;
		}
	}
	return \@native;
}

sub validate_local
{
	my ($local) = @_;
	if (ref($local) ne "HASH") {
		push @errors, "local section is missing or is not an object.";
		return;
	}
	validate_known_keys($local, "local", [qw(enabled port index timeout buffer)]);
	validate_boolean($local->{enabled}, "local.enabled");
	validate_boolean($local->{index}, "local.index");
	validate_port($local->{port}, "local.port");
	validate_integer_range($local->{timeout}, "local.timeout", 0, undef);
	push @errors, "local.buffer must be an integer." if (!is_integer($local->{buffer}));
}

sub validate_mqtt
{
	my ($mqtt) = @_;
	if (ref($mqtt) ne "HASH") {
		push @errors, "mqtt section is missing or is not an object.";
		return;
	}
	validate_known_keys($mqtt, "mqtt", [qw(enabled host port id cafile capath certfile keyfile keypass keepalive topic user pass retain rawAndAgg qos timestamp)]);
	validate_boolean($mqtt->{enabled}, "mqtt.enabled");
	foreach my $field (qw(retain rawAndAgg timestamp)) {
		validate_boolean($mqtt->{$field}, "mqtt.$field") if (exists($mqtt->{$field}));
	}
	validate_integer_range($mqtt->{keepalive}, "mqtt.keepalive", 0, undef) if (exists($mqtt->{keepalive}));
	push @errors, "mqtt.qos must be 0 or 1." if (exists($mqtt->{qos}) && (!is_integer($mqtt->{qos}) || $mqtt->{qos} < 0 || $mqtt->{qos} > 1));
	return if (!$mqtt->{enabled});

	push @errors, "mqtt.host is required when MQTT is enabled." if (!is_nonempty_scalar($mqtt->{host}));
	validate_port($mqtt->{port}, "mqtt.port");
	my $topic = scalar_text($mqtt->{topic});
	push @errors, "mqtt.topic is required when MQTT is enabled." if ($topic eq "");
	push @errors, "mqtt.topic must not start with \$." if ($topic =~ /\A\$/);
	push @errors, "mqtt.topic must not end with /." if ($topic =~ m{/\z});
	push @errors, "mqtt.topic must not contain MQTT wildcards + or #." if ($topic =~ /[+#]/);
	push @errors, "Use either mqtt.cafile or mqtt.capath, not both."
		if (is_nonempty_scalar($mqtt->{cafile}) && is_nonempty_scalar($mqtt->{capath}));
	push @errors, "mqtt.certfile and mqtt.keyfile must be configured together."
		if (!!is_nonempty_scalar($mqtt->{certfile}) != !!is_nonempty_scalar($mqtt->{keyfile}));
	push @errors, "mqtt.keypass requires mqtt.keyfile." if (is_nonempty_scalar($mqtt->{keypass}) && !is_nonempty_scalar($mqtt->{keyfile}));
	push @errors, "mqtt.pass requires mqtt.user." if (is_nonempty_scalar($mqtt->{pass}) && !is_nonempty_scalar($mqtt->{user}));
	foreach my $field (qw(cafile certfile keyfile)) {
		next if (!is_nonempty_scalar($mqtt->{$field}));
		push @errors, "mqtt.$field does not name a readable file: $mqtt->{$field}" if (!-f $mqtt->{$field} || !-r $mqtt->{$field});
	}
	if (is_nonempty_scalar($mqtt->{capath})) {
		push @errors, "mqtt.capath does not name a readable directory: $mqtt->{capath}" if (!-d $mqtt->{capath} || !-r $mqtt->{capath});
	}
}

sub validate_meter
{
	my ($meter, $prefix, $device_seen, $custom_meter) = @_;
	my $protocol = scalar_text($meter->{protocol});
	push @errors, "$prefix.protocol must be a non-empty string." if ($protocol eq "");
	validate_boolean($meter->{enabled}, "$prefix.enabled");
	validate_boolean($meter->{allowskip}, "$prefix.allowskip") if (exists($meter->{allowskip}));
	validate_boolean($meter->{aggfixedinterval}, "$prefix.aggfixedinterval") if (exists($meter->{aggfixedinterval}));
	validate_integer_range($meter->{aggtime}, "$prefix.aggtime", -1, undef) if (exists($meter->{aggtime}));
	validate_integer_range($meter->{interval}, "$prefix.interval", -1, undef) if (exists($meter->{interval}));
	if (is_integer($meter->{aggtime}) && is_integer($meter->{interval}) && $meter->{aggtime} > 0 && $meter->{interval} > 0 && $meter->{aggtime} < $meter->{interval}) {
		push @errors, "$prefix.aggtime ($meter->{aggtime}) must not be shorter than interval ($meter->{interval}).";
	}
	push @errors, "$prefix.aggfixedinterval requires aggtime greater than 0."
		if ($meter->{aggfixedinterval} && (!is_integer($meter->{aggtime}) || $meter->{aggtime} <= 0));

	if (!$custom_meter && $protocol =~ /\A(?:sml|d0|oms)\z/) {
		my %common = map { $_ => 1 } qw(enabled allowskip aggtime aggfixedinterval protocol device host channels);
		my %specific = (
			sml => { map { $_ => 1 } qw(interval pullseq baudrate parity use_local_time) },
			d0 => { map { $_ => 1 } qw(interval dump_file pullseq ackseq baudrate baudrate_read parity wait_sync read_timeout baudrate_change_delay) },
			oms => { map { $_ => 1 } qw(baudrate key mbus_debug use_local_time) },
		);
		my @allowed = (keys %common, keys %{$specific{$protocol}});
		validate_known_keys($meter, $prefix, \@allowed);
		my $device = scalar_text($meter->{device});
		my $host = scalar_text($meter->{host});
		if ($meter->{enabled}) {
			push @errors, "$prefix requires either device or host." if ($device eq "" && $host eq "");
			push @errors, "$prefix must not configure device and host together." if ($device ne "" && $host ne "");
			if ($device ne "") {
				push @errors, "$prefix.device does not exist: $device" if (!-e $device);
				push @errors, "$prefix.device is not readable and writable: $device" if (-e $device && (!-r $device || !-w $device));
				push @errors, "$prefix.device is already used by another active meter: $device" if ($device_seen->{$device}++);
			}
			push @errors, "$prefix.host must contain a host and port." if ($host ne "" && !valid_meter_host($host));
		}
		if (command_exists("vzlogger") && !vzlogger_supports_protocol($protocol)) {
			push @errors, "$prefix.protocol $protocol is not supported by the installed vzLogger.";
		}
	}

	foreach my $field (qw(baudrate baudrate_read)) {
		next if (!exists($meter->{$field}));
		push @errors, "$prefix.$field must be a positive integer no greater than 4000000."
			if (!is_integer($meter->{$field}) || $meter->{$field} <= 0 || $meter->{$field} > 4000000);
		push @warnings, "$prefix.$field uses the non-standard serial rate $meter->{$field}."
			if (is_integer($meter->{$field}) && $meter->{$field} > 0 && !grep { $_ == $meter->{$field} } qw(300 600 1200 1800 2400 4800 9600 19200 38400 57600 115200));
	}
	push @errors, "$prefix.parity must be 7e1, 8n1, 7o1 or 7n1."
		if (exists($meter->{parity}) && scalar_text($meter->{parity}) !~ /\A(?:7e1|8n1|7o1|7n1)\z/i);
	foreach my $field (qw(use_local_time mbus_debug)) {
		validate_boolean($meter->{$field}, "$prefix.$field") if (exists($meter->{$field}));
	}
	if ($protocol eq "sml" || $protocol eq "d0") {
		validate_hex_sequence($meter->{pullseq}, "$prefix.pullseq") if (exists($meter->{pullseq}));
	}
	if ($protocol eq "d0") {
		my $ack = scalar_text($meter->{ackseq});
		push @errors, "$prefix.ackseq must be empty, auto or an even-length hexadecimal sequence."
			if ($ack ne "" && $ack ne "auto" && ($ack !~ /\A[0-9a-f]+\z/i || length($ack) % 2));
		push @warnings, "$prefix configures ackseq/baudrate_read without a pullseq."
			if (scalar_text($meter->{pullseq}) eq "" && ($ack ne "" || exists($meter->{baudrate_read})));
		push @errors, "$prefix.wait_sync must be off or end."
			if (exists($meter->{wait_sync}) && scalar_text($meter->{wait_sync}) !~ /\A(?:off|end)\z/);
		validate_integer_range($meter->{read_timeout}, "$prefix.read_timeout", 1, undef) if (exists($meter->{read_timeout}));
		validate_integer_range($meter->{baudrate_change_delay}, "$prefix.baudrate_change_delay", 0, undef) if (exists($meter->{baudrate_change_delay}));
		validate_output_path($meter->{dump_file}, "$prefix.dump_file") if (is_nonempty_scalar($meter->{dump_file}) && $meter->{enabled});
	}
	if ($protocol eq "oms" && exists($meter->{key})) {
		push @errors, "$prefix.key must contain exactly 32 hexadecimal characters."
			if (scalar_text($meter->{key}) !~ /\A[0-9a-f]{32}\z/i);
	}
	push @errors, "$prefix.channels must be an array." if (ref($meter->{channels}) ne "ARRAY");
}

sub validate_native_channel
{
	my ($channel, $prefix, $meter, $custom_meter) = @_;
	my $api = scalar_text($channel->{api});
	my $protocol = scalar_text($meter->{protocol});
	my %base = map { $_ => 1 } qw(api uuid identifier aggmode);
	my %api_fields = (
		null => {},
		volkszaehler => { map { $_ => 1 } qw(middleware timeout duplicates) },
		influxdb => { map { $_ => 1 } qw(version host token organization username password database measurement_name tags timeout max_batch_inserts max_buffer_size send_uuid ssl_verifypeer duplicates) },
		mysmartgrid => { map { $_ => 1 } qw(middleware secretKey device type interval scaler timeout name) },
	);
	my @allowed = (keys %base, keys %{ $api_fields{$api} || {} });
	validate_known_keys($channel, $prefix, \@allowed) if (!$custom_meter);
	push @errors, "$prefix.api must be null, volkszaehler, influxdb or mysmartgrid."
		if (!exists($api_fields{$api}));
	my $uuid = scalar_text($channel->{uuid});
	push @errors, "$prefix.uuid is missing or malformed."
		if ($uuid !~ /\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/i);
	my $identifier = scalar_text($channel->{identifier});
	push @errors, "$prefix.identifier is required." if (!$custom_meter && $identifier eq "");
	if (!$custom_meter && $protocol =~ /\A(?:sml|d0|oms)\z/ && $identifier ne "") {
		my $parsed = parse_obis($identifier);
		push @errors, "$prefix.identifier is not a valid OBIS identifier." if (!$parsed);
		push @errors, "$prefix.identifier must not contain a storage index for OMS." if ($protocol eq "oms" && $parsed && defined($parsed->{f}));
	}
	my $agg = scalar_text($channel->{aggmode}) || "none";
	push @errors, "$prefix.aggmode must be none, avg, max or sum." if ($agg !~ /\A(?:none|avg|max|sum)\z/);
	push @errors, "$prefix.aggmode must be none while meter aggtime is disabled."
		if ($agg ne "none" && (!is_integer($meter->{aggtime}) || $meter->{aggtime} <= 0));
	if (exists($channel->{duplicates})) {
		push @errors, "$prefix.duplicates is only valid for volkszaehler and influxdb."
			if ($api ne "volkszaehler" && $api ne "influxdb");
		validate_integer_range($channel->{duplicates}, "$prefix.duplicates", 0, undef);
	}
	if ($api eq "volkszaehler") {
		push @errors, "$prefix.middleware must be a valid HTTP(S) URL." if (!is_http_url($channel->{middleware}));
	}
	if ($api eq "influxdb") {
		push @errors, "$prefix.host is required for InfluxDB." if (!is_nonempty_scalar($channel->{host}));
		push @errors, "$prefix.version must be 1 or 2." if (exists($channel->{version}) && scalar_text($channel->{version}) !~ /\A[12]\z/);
		foreach my $field (qw(timeout max_batch_inserts max_buffer_size)) {
			validate_integer_range($channel->{$field}, "$prefix.$field", 0, undef) if (exists($channel->{$field}));
		}
		foreach my $field (qw(send_uuid ssl_verifypeer)) {
			validate_boolean($channel->{$field}, "$prefix.$field") if (exists($channel->{$field}));
		}
		push @errors, "$prefix.tags must be a JSON object." if (exists($channel->{tags}) && ref($channel->{tags}) ne "HASH");
	}
	if ($api eq "mysmartgrid") {
		push @errors, "$prefix.middleware must be a valid HTTP(S) URL." if (!is_http_url($channel->{middleware}));
		push @errors, "$prefix.secretKey is required for MySmartGrid." if (!is_nonempty_scalar($channel->{secretKey}));
		push @errors, "$prefix.device is required for MySmartGrid." if (!is_nonempty_scalar($channel->{device}));
		push @errors, "$prefix.type must be device or sensor." if (scalar_text($channel->{type}) !~ /\A(?:device|sensor)\z/);
		validate_integer_range($channel->{interval}, "$prefix.interval", 0, undef) if (exists($channel->{interval}));
		validate_integer_range($channel->{timeout}, "$prefix.timeout", 0, undef) if (exists($channel->{timeout}));
		push @errors, "$prefix.scaler must be a number." if (exists($channel->{scaler}) && (ref($channel->{scaler}) || $channel->{scaler} !~ /\A-?\d+(?:\.\d+)?\z/));
	}
}

sub validate_mapping
{
	my ($mapping, $native, $definitions) = @_;
	if (ref($mapping) ne "HASH") {
		push @errors, "Channel mapping must be a JSON object.";
		return;
	}
	my (%native_by_uuid, %mapping_indices, %output_keys);
	foreach my $entry (@$native) {
		$native_by_uuid{lc($entry->{uuid})} = $entry if ($entry->{uuid} ne "");
	}
	foreach my $uuid (keys %$mapping) {
		my $entry = $mapping->{$uuid};
		push @errors, "Mapping key $uuid is not a UUID." if ($uuid !~ /\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/i);
		if (ref($entry) ne "HASH") {
			push @errors, "Mapping entry $uuid must be a JSON object.";
			next;
		}
		push @errors, "Mapping entry $uuid has no serial." if (!is_nonempty_scalar($entry->{serial}));
		push @errors, "Mapping entry $uuid has no name." if (!is_nonempty_scalar($entry->{name}));
		validate_boolean($entry->{managed_output}, "Mapping entry $uuid managed_output") if (exists($entry->{managed_output}));
		push @errors, "Mapping entry $uuid has an invalid output key (required format: " . output_key_format() . ")."
			if ($entry->{managed_output} && !valid_output_key(scalar_text($entry->{name})));
		push @errors, "Mapping output key $entry->{name} is duplicated for meter $entry->{serial}."
			if ($entry->{managed_output} && is_nonempty_scalar($entry->{name}) && is_nonempty_scalar($entry->{serial}) && $output_keys{lc("$entry->{serial}\0$entry->{name}")}++);
		my $native_entry = $native_by_uuid{lc($uuid)};
		push @errors, "Mapping entry $uuid does not reference a generated channel." if (!$native_entry);
		next if (!$native_entry);
		push @errors, "Mapping entry $uuid identifier does not match the generated channel."
			if (scalar_text($entry->{identifier}) ne $native_entry->{identifier});
		push @errors, "Mapping entry $uuid channel_index must be $native_entry->{index}."
			if (!is_integer($entry->{channel_index}) || $entry->{channel_index} != $native_entry->{index});
		push @errors, "Mapping entry $uuid channel must be chn$native_entry->{index}."
			if (scalar_text($entry->{channel}) ne "chn$native_entry->{index}");
		push @errors, "Mapping channel index $entry->{channel_index} is duplicated."
			if (is_integer($entry->{channel_index}) && $mapping_indices{$entry->{channel_index}}++);
	}

	return if (ref($definitions) ne "HASH" || ref($definitions->{meters}) ne "HASH");
	foreach my $serial (keys %{$definitions->{meters}}) {
		foreach my $definition (@{$definitions->{meters}->{$serial} || []}) {
			next if (ref($definition) ne "HASH" || !$definition->{enabled});
			my $uuid = scalar_text($definition->{uuid});
			my $native_entry = $native_by_uuid{lc($uuid)};
			push @errors, "$serial/$uuid: active definition has no generated channel." if (!$native_entry);
			if ($native_entry) {
				my $expected_identifier = compose_obis($definition->{obis}, $definition->{storage});
				push @errors, "$serial/$uuid: generated identifier does not match its definition."
					if ($native_entry->{identifier} ne $expected_identifier);
			}
			my $output = ref($definition->{plugin_output}) eq "HASH" ? $definition->{plugin_output} : {};
			my $mapped = $mapping->{$uuid};
			if ($output->{enabled}) {
				push @errors, "$serial/$uuid: active plugin output has no mapping entry." if (ref($mapped) ne "HASH");
				if (ref($mapped) eq "HASH") {
					push @errors, "$serial/$uuid: mapping is not marked as a managed output." if (!$mapped->{managed_output});
					push @errors, "$serial/$uuid: mapping serial does not match its definition." if (scalar_text($mapped->{serial}) ne $serial);
					push @errors, "$serial/$uuid: mapping output key does not match its definition." if (scalar_text($mapped->{name}) ne scalar_text($output->{key}));
				}
			} elsif (ref($mapped) eq "HASH" && $mapped->{managed_output}) {
				push @errors, "$serial/$uuid: disabled plugin output must not have a managed mapping entry.";
			}
		}
	}
	if (bridge_enabled()) {
		my $managed_count = grep { ref($_) eq "HASH" && $_->{managed_output} } values %$mapping;
		push @errors, "The SmartMeter bridge is enabled but no active plugin output channel is configured." if (!$managed_count);
	}
}

sub validate_known_keys
{
	my ($hash, $prefix, $allowed) = @_;
	my %allowed = map { $_ => 1 } @$allowed;
	push @errors, "$prefix contains unsupported parameter $_." foreach grep { !$allowed{$_} } sort keys %$hash;
}

sub validate_integer_range
{
	my ($value, $label, $minimum, $maximum) = @_;
	if (!is_integer($value)) {
		push @errors, "$label must be an integer.";
		return;
	}
	push @errors, "$label must be at least $minimum." if (defined($minimum) && $value < $minimum);
	push @errors, "$label must not exceed $maximum." if (defined($maximum) && $value > $maximum);
}

sub validate_port
{
	my ($value, $label) = @_;
	push @errors, "$label must be an integer between 1 and 65535."
		if (!is_integer($value) || $value < 1 || $value > 65535);
}

sub validate_boolean
{
	my ($value, $label) = @_;
	push @errors, "$label must be a JSON boolean." if (!defined($value) || !JSON::PP::is_bool($value));
}

sub validate_hex_sequence
{
	my ($value, $label) = @_;
	my $text = scalar_text($value);
	push @errors, "$label must be empty or an even-length hexadecimal sequence."
		if ($text ne "" && ($text !~ /\A[0-9a-f]+\z/i || length($text) % 2));
}

sub validate_output_path
{
	my ($file, $label) = @_;
	my $directory = dirname($file);
	push @errors, "$label parent directory does not exist: $directory" if (!-d $directory);
	push @errors, "$label parent directory is not writable: $directory" if (-d $directory && !-w $directory);
}

sub is_integer
{
	my ($value) = @_;
	return defined($value) && !ref($value) && "$value" =~ /\A-?\d+\z/;
}

sub is_nonempty_scalar
{
	my ($value) = @_;
	return defined($value) && !ref($value) && $value ne "";
}

sub scalar_text
{
	my ($value) = @_;
	return defined($value) && !ref($value) ? "$value" : "";
}

sub is_http_url
{
	my ($value) = @_;
	return is_nonempty_scalar($value) && $value =~ m{\Ahttps?://[^\s/]+(?:/[^\s]*)?\z}i;
}

sub valid_meter_host
{
	my ($value) = @_;
	return $value =~ m{\A(?:tcp://)?[^\s:]+:\d{1,5}\z} && do {
		my ($port) = $value =~ /:(\d+)\z/;
		$port > 0 && $port <= 65535;
	};
}

my %protocol_support;
sub vzlogger_supports_protocol
{
	my ($protocol) = @_;
	return $protocol_support{$protocol} if (exists($protocol_support{$protocol}));
	my $help = `vzlogger -h 2>&1`;
	return $protocol_support{$protocol} = ($help =~ /^\s*\Q$protocol\E\s+/mi ? 1 : 0);
}

sub command_exists
{
	my ($command) = @_;
	foreach my $dir (split(/:/, $ENV{PATH} || "")) {
		return 1 if (-x "$dir/$command");
	}
	return 0;
}

sub read_plugin_config
{
	my %plugin_config;
	return \%plugin_config if (!-e $plugin_config_file);
	Config::Simple->import_from($plugin_config_file, \%plugin_config);
	return \%plugin_config;
}

sub vzlogger_mode_enabled
{
	my $config = read_plugin_config();
	return (($config->{"MAIN.IMPLEMENTATION"} || "") eq "vzlogger") ? 1 : 0;
}

sub bridge_enabled
{
	my $config = read_plugin_config();
	return (($config->{"MAIN.IMPLEMENTATION"} || "") eq "vzlogger" && ($config->{"MAIN.READ"} || "0") eq "1") ? 1 : 0;
}
