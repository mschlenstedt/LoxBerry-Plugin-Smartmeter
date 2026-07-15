#!/usr/bin/perl

use strict;
use warnings;

use Config::Simple;
use Digest::MD5 qw(md5_hex);
use File::Path qw(make_path);
use JSON::PP;
use LoxBerry::System;

my $home = $lbhomedir;
my $psubfolder = $lbpplugindir;
my $config_file = "$home/config/plugins/$psubfolder/smartmeter.cfg";
my $target_file = "$home/config/plugins/$psubfolder/vzlogger.conf";
my $mapping_file = "$home/config/plugins/$psubfolder/vzlogger_channels.json";
my $plugin_config_dir = "$home/config/plugins/$psubfolder";
my $plugin_cfg = Config::Simple->new($config_file) or die "Could not read $config_file\n";
my $debug_enabled = ($plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG") || "0") eq "1";
my $log_level = int(clean_log_level($plugin_cfg->param("VZLOGGER.LOGLEVEL"), 0));
my $log_file = $debug_enabled ? "$home/log/plugins/$psubfolder/vzlogger.log" : "/dev/null";

my %flat_config;
Config::Simple->import_from($config_file, \%flat_config);

my $mqtt = read_mqtt_settings();
my $base_topic = sanitize_topic($plugin_cfg->param("MAIN.MQTTTOPIC") || "smartmeter");
my $local_enabled = clean_boolean($plugin_cfg->param("VZLOGGER.LOCALENABLED"), 1);
my $local_port = clean_number($plugin_cfg->param("VZLOGGER.LOCALPORT"), 18080);
my $local_index = clean_boolean($plugin_cfg->param("VZLOGGER.LOCALINDEX"), 1);
my $local_timeout = clean_number($plugin_cfg->param("VZLOGGER.LOCALTIMEOUT"), 30);
my $local_buffer = clean_integer($plugin_cfg->param("VZLOGGER.LOCALBUFFER"), -1);
my $retry = clean_number($plugin_cfg->param("VZLOGGER.RETRY"), 30);
my $vzlogger_mode = ($plugin_cfg->param("MAIN.IMPLEMENTATION") || "") eq "vzlogger";

my @meters;
my %channel_mapping;
my $channel_index = 0;

foreach my $config_key (sort keys %flat_config) {
	next if ($config_key !~ /\.SERIAL\z/);

	my $section = $flat_config{$config_key};
	my $device = $plugin_cfg->param("$section.DEVICE") || next;
	my $meter = $plugin_cfg->param("$section.METER") || "0";
	next if ($meter eq "0");

	my $protocol_name = $meter eq "manual" ? ($plugin_cfg->param("$section.PROTOCOL") || "") : $meter;
	my $protocol = protocol_for_meter($protocol_name);
	next if (!$protocol);

	my $serial = $plugin_cfg->param("$section.SERIAL") || $section;
	my $meter_config = {
		enabled => $vzlogger_mode ? JSON::PP::true : JSON::PP::false,
		allowskip => JSON::PP::true,
		aggtime => -1,
		protocol => $protocol,
		device => $device,
	};

	if ($protocol eq "sml") {
		$meter_config->{interval} = -1;
	} else {
		$meter_config->{interval} = -1;
		$meter_config->{read_timeout} = clean_number($plugin_cfg->param("$section.TIMEOUT"), 10);
		$meter_config->{baudrate} = clean_number($plugin_cfg->param("$section.BAUDRATE"), default_baudrate($protocol_name));
		$meter_config->{baudrate_read} = clean_number($plugin_cfg->param("$section.STARTBAUDRATE"), 300);
		$meter_config->{parity} = serial_mode(
			$plugin_cfg->param("$section.DATABITS"),
			$plugin_cfg->param("$section.PARITY"),
			$plugin_cfg->param("$section.STOPBITS")
		);
	}

	my @channels;
	foreach my $channel (configured_channels($section)) {
		my $uuid = stable_uuid("$psubfolder:$serial:$channel->{identifier}");
		push @channels, {
			api => "null",
			uuid => $uuid,
			identifier => $channel->{identifier},
		};
		$channel_mapping{$uuid} = {
			serial => $serial,
			name => $channel->{name},
			identifier => $channel->{identifier},
			channel => "chn$channel_index",
			channel_index => $channel_index,
		};
		$channel_index++;
	}
	$meter_config->{channels} = \@channels;
	push @meters, $meter_config;
}

my $mqtt_config = {
	enabled => clean_boolean($plugin_cfg->param("VZLOGGER.MQTTENABLED"), 1) ? JSON::PP::true : JSON::PP::false,
	host => $mqtt->{host},
	port => $mqtt->{port},
	keepalive => clean_number($plugin_cfg->param("VZLOGGER.MQTTKEEPALIVE"), 30),
	topic => "$base_topic/vzlogger",
	retain => clean_boolean($plugin_cfg->param("VZLOGGER.MQTTRETAIN"), 1) ? JSON::PP::true : JSON::PP::false,
	rawAndAgg => clean_boolean($plugin_cfg->param("VZLOGGER.MQTTRAWANDAGG"), 0) ? JSON::PP::true : JSON::PP::false,
	qos => clean_qos($plugin_cfg->param("VZLOGGER.MQTTQOS"), 0),
	timestamp => clean_boolean($plugin_cfg->param("VZLOGGER.MQTTTIMESTAMP"), 1) ? JSON::PP::true : JSON::PP::false,
};
my %optional_mqtt_values = (
	id => clean_text($plugin_cfg->param("VZLOGGER.MQTTID"), ""),
	user => $mqtt->{user},
	pass => $mqtt->{pass},
	cafile => $mqtt->{cafile},
	capath => $mqtt->{capath},
	certfile => $mqtt->{certfile},
	keyfile => $mqtt->{keyfile},
	keypass => $mqtt->{keypass},
);
foreach my $key (keys %optional_mqtt_values) {
	$mqtt_config->{$key} = $optional_mqtt_values{$key} if ($optional_mqtt_values{$key} ne "");
}

my $config = {
	retry => $retry,
	verbosity => $debug_enabled ? $log_level : 0,
	log => $log_file,
	local => {
		enabled => $local_enabled ? JSON::PP::true : JSON::PP::false,
		port => $local_port,
		index => $local_index ? JSON::PP::true : JSON::PP::false,
		timeout => $local_timeout,
		buffer => $local_buffer,
	},
	mqtt => $mqtt_config,
	meters => \@meters,
};

write_ordered_vzlogger_json($target_file, $config);
write_json($mapping_file, \%channel_mapping);

print "Generated $target_file with " . scalar(@meters) . " enabled meter(s).\n";
exit 0;

sub read_mqtt_settings
{
	my $general_json = "$home/config/system/general.json";
	my %settings = (
		host => "127.0.0.1",
		port => 1883,
		user => "",
		pass => "",
		cafile => "",
		capath => "",
		certfile => "",
		keyfile => "",
		keypass => "",
	);

	if (-e $general_json && open(my $fh, "<", $general_json)) {
		local $/;
		my $json_text = <$fh>;
		close($fh);
		my $general = eval { JSON::PP->new->utf8->decode($json_text) };
		if (!$@ && ref($general) && ref($general->{Mqtt})) {
			my $mqtt = $general->{Mqtt};
			$settings{host} = first_value($mqtt, qw(Host Hostname Broker Brokerhost Server IpAddress Ipaddress)) || $settings{host};
			$settings{port} = clean_number(first_value($mqtt, qw(Port Brokerport Mqttport)), $settings{port});
			$settings{user} = first_value($mqtt, qw(Brokeruser Brokerusername User Username Login)) || "";
			$settings{pass} = first_value($mqtt, qw(Brokerpass Brokerpassword Pass Password)) || "";
		}
	}

	$settings{host} = clean_text($plugin_cfg->param("VZLOGGER.MQTTHOST"), $settings{host});
	$settings{port} = clean_number($plugin_cfg->param("VZLOGGER.MQTTPORT"), $settings{port});
	$settings{cafile} = clean_text($plugin_cfg->param("VZLOGGER.MQTTCAFILE"), "");
	$settings{capath} = clean_text($plugin_cfg->param("VZLOGGER.MQTTCAPATH"), "");
	$settings{certfile} = clean_text($plugin_cfg->param("VZLOGGER.MQTTCERTFILE"), "");
	$settings{keyfile} = clean_text($plugin_cfg->param("VZLOGGER.MQTTKEYFILE"), "");
	$settings{keypass} = clean_text($plugin_cfg->param("VZLOGGER.MQTTKEYPASS"), "");
	$settings{user} = clean_text($plugin_cfg->param("VZLOGGER.MQTTUSER"), $settings{user});
	$settings{pass} = clean_text($plugin_cfg->param("VZLOGGER.MQTTPASS"), $settings{pass});

	return \%settings;
}

sub first_value
{
	my ($hash, @keys) = @_;
	foreach my $key (@keys) {
		return $hash->{$key} if (defined($hash->{$key}) && $hash->{$key} ne "");
	}
	return undef;
}

sub write_json
{
	my ($file, $data) = @_;
	my ($dir) = $file =~ m{\A(.*)/[^/]+\z};
	make_path($dir) if ($dir && !-d $dir);

	open(my $fh, ">", $file) or die "Could not write $file: $!\n";
	print $fh JSON::PP->new->utf8->pretty->canonical->encode($data);
	close($fh);
}

sub protocol_for_meter
{
	my ($meter) = @_;
	return "sml" if ($meter =~ /sml\z/i);
	return "d0" if ($meter =~ /d0\z/i || $meter =~ /do\z/i);
	return "";
}

sub default_baudrate
{
	my ($meter) = @_;
	return 115200 if ($meter =~ /sagemcom/i);
	return 4800 if ($meter =~ /landisgyr[e]?(320|350)/i);
	return 2400 if ($meter =~ /(t550|uh50)/i);
	return 9600 if ($meter =~ /(iskra|pafal|siemens)/i);
	return 300;
}

sub serial_mode
{
	my ($databits, $parity, $stopbits) = @_;
	$databits ||= 7;
	$parity ||= "even";
	$stopbits ||= 1;

	my $parity_char = "N";
	$parity_char = "E" if (lc($parity) eq "even");
	$parity_char = "O" if (lc($parity) eq "odd");

	return "$databits$parity_char$stopbits";
}

sub cron_to_seconds
{
	my ($cron) = @_;
	return 5 if (!defined($cron) || $cron eq "" || $cron eq "M");
	return int($cron) * 60 if ($cron =~ /\A\d+\z/ && int($cron) > 0);
	return 300;
}

sub clean_number
{
	my ($value, $default) = @_;
	return int($value) if (defined($value) && $value =~ /\A\d+\z/);
	return $default;
}

sub sanitize_topic
{
	my ($topic) = @_;
	$topic ||= "smartmeter";
	$topic =~ s/^\s+|\s+$//g;
	$topic =~ s/^\/+|\/+$//g;
	$topic =~ s/[#+]//g;
	return $topic || "smartmeter";
}

sub stable_uuid
{
	my ($seed) = @_;
	my $hex = md5_hex($seed);
	return substr($hex, 0, 8) . "-" .
		substr($hex, 8, 4) . "-" .
		substr($hex, 12, 4) . "-" .
		substr($hex, 16, 4) . "-" .
		substr($hex, 20, 12);
}

sub default_channels
{
	return (
		{ identifier => "1-0:1.8.0", name => "Consumption_Total_OBIS_1.8.0" },
		{ identifier => "1-0:1.8.1", name => "Consumption_Tarif1_OBIS_1.8.1" },
		{ identifier => "1-0:1.8.2", name => "Consumption_Tarif2_OBIS_1.8.2" },
		{ identifier => "1-0:1.7.0", name => "Consumption_Power_OBIS_1.7.0" },
		{ identifier => "1-0:21.7.0", name => "Consumption_Power_L1_OBIS_21.7.0" },
		{ identifier => "1-0:41.7.0", name => "Consumption_Power_L2_OBIS_41.7.0" },
		{ identifier => "1-0:61.7.0", name => "Consumption_Power_L3_OBIS_61.7.0" },
		{ identifier => "1-0:2.8.0", name => "Delivery_Total_OBIS_2.8.0" },
		{ identifier => "1-0:2.8.1", name => "Delivery_Tarif1_OBIS_2.8.1" },
		{ identifier => "1-0:2.8.2", name => "Delivery_Tarif2_OBIS_2.8.2" },
		{ identifier => "1-0:2.7.0", name => "Delivery_Power_OBIS_2.7.0" },
		{ identifier => "1-0:15.7.0", name => "Total_Power_OBIS_15.7.0" },
		{ identifier => "1-0:16.7.0", name => "Total_Power_OBIS_16.7.0" },
		{ identifier => "1-0:96.50.1", name => "Manufacturer_ID_OBIS_96.50.1" },
		{ identifier => "1-0:96.1.0", name => "Server_ID_OBIS_96.1.0" },
	);
}

sub write_ordered_vzlogger_json
{
	my ($file, $data) = @_;
	my ($dir) = $file =~ m{\A(.*)/[^/]+\z};
	make_path($dir) if ($dir && !-d $dir);

	open(my $fh, ">", $file) or die "Could not write $file: $!\n";
	print $fh encode_ordered_json($data, "root", 0), "\n";
	close($fh);
}

sub encode_ordered_json
{
	my ($value, $context, $level) = @_;
	my $ref = ref($value);

	if ($ref eq "HASH") {
		my @keys = ordered_keys($context, $value);
		return "{}" if (!@keys);

		my @lines;
		foreach my $key (@keys) {
			my $key_json = JSON::PP->new->utf8->allow_nonref->encode($key);
			my $child_context = child_context($context, $key);
			push @lines, ("  " x ($level + 1)) . $key_json . ": " .
				encode_ordered_json($value->{$key}, $child_context, $level + 1);
		}
		return "{\n" . join(",\n", @lines) . "\n" . ("  " x $level) . "}";
	}

	if ($ref eq "ARRAY") {
		return "[]" if (!@{$value});
		my $item_context = $context eq "meters" ? "meter" :
			$context eq "channels" ? "channel" : "default";
		my @items = map {
			("  " x ($level + 1)) . encode_ordered_json($_, $item_context, $level + 1)
		} @{$value};
		return "[\n" . join(",\n", @items) . "\n" . ("  " x $level) . "]";
	}

	return JSON::PP->new->utf8->allow_nonref->encode($value);
}

sub ordered_keys
{
	my ($context, $data) = @_;
	my %orders = (
		root => [qw(retry verbosity log local mqtt meters)],
		local => [qw(enabled port index timeout buffer)],
		mqtt => [qw(enabled host port keepalive topic id user pass retain rawAndAgg qos timestamp cafile capath certfile keyfile keypass)],
		meter => [qw(enabled allowskip protocol device aggtime interval read_timeout baudrate baudrate_read parity channels)],
		channel => [qw(api uuid identifier)],
	);
	my @preferred = @{$orders{$context} || []};
	my %seen;
	my @keys = grep { exists($data->{$_}) && !$seen{$_}++ } @preferred;
	push @keys, grep { !$seen{$_}++ } sort keys %{$data};
	return @keys;
}

sub child_context
{
	my ($context, $key) = @_;
	return "local" if ($context eq "root" && $key eq "local");
	return "mqtt" if ($context eq "root" && $key eq "mqtt");
	return "meters" if ($context eq "root" && $key eq "meters");
	return "channels" if ($context eq "meter" && $key eq "channels");
	return "default";
}

sub clean_integer
{
	my ($value, $default) = @_;
	return int($value) if (defined($value) && $value =~ /\A-?\d+\z/);
	return $default;
}

sub clean_boolean
{
	my ($value, $default) = @_;
	return int($value) if (defined($value) && $value =~ /\A[01]\z/);
	return $default;
}

sub clean_qos
{
	my ($value, $default) = @_;
	return int($value) if (defined($value) && $value =~ /\A[01]\z/);
	return $default;
}

sub clean_text
{
	my ($value, $default) = @_;
	return $default if (!defined($value) || $value eq "");
	$value =~ s/[\r\n]//g;
	return $value;
}

sub clean_log_level
{
	my ($value, $default) = @_;
	return $value if (defined($value) && $value =~ /\A(?:0|1|3|5|10|15)\z/);
	return $default;
}

sub configured_channels
{
	my ($section) = @_;
	my $has_configured_channels = defined($plugin_cfg->param("$section.OBISCHANNELS"));
	my %enabled = map { $_ => 1 } config_list_values("$section.OBISCHANNELS");

	my @channels;
	foreach my $channel (available_channels($section)) {
		push @channels, $channel if (!$has_configured_channels || $enabled{$channel->{identifier}});
	}

	my %seen = map { $_->{identifier} => 1 } @channels;
	foreach my $identifier (custom_channels($section)) {
		next if ($seen{$identifier});
		push @channels, {
			identifier => $identifier,
			name => obis_cache_name($identifier),
		};
		$seen{$identifier} = 1;
	}
	return @channels;
}

sub available_channels
{
	my ($section) = @_;
	my $serial = $plugin_cfg->param("$section.SERIAL") || $section;
	my @channels = read_obis_discovery_cache($serial);
	return sort_obis_channels(@channels) if (obis_discovery_cache_exists($serial));

	my %seen;
	foreach my $identifier (config_list_values("$section.OBISCHANNELS")) {
		$identifier = normalize_obis_identifier($identifier);
		next if (!$identifier || $seen{$identifier});
		push @channels, {
			identifier => $identifier,
			name => obis_cache_name($identifier),
		};
		$seen{$identifier} = 1;
	}

	return sort_obis_channels(@channels);
}

sub config_list_values
{
	my ($key) = @_;
	my $value = $plugin_cfg->param($key);
	return () if (!defined($value));
	return grep { defined($_) && $_ ne "" } @{$value} if (ref($value) eq "ARRAY");
	return grep { $_ ne "" } split(/\s*,\s*/, $value);
}

sub custom_channels
{
	my ($section) = @_;
	my $value = $plugin_cfg->param("$section.OBISCUSTOM") || "";
	my @channels;
	foreach my $line (split(/\\n|\r?\n|,|;/, $value)) {
		my $identifier = normalize_obis_identifier($line);
		push @channels, $identifier if ($identifier);
	}
	return sort_obis_channels(@channels);
}

sub normalize_obis_identifier
{
	my ($value) = @_;
	return "" if (!defined($value));
	$value =~ s/^\s+|\s+$//g;
	$value =~ s/\*\d+\z//;
	return $value if ($value =~ /\A\d+-\d+:[A-Za-z0-9]+\.\d+\.\d+\z/);
	return "";
}

sub obis_cache_name
{
	my ($identifier) = @_;
	my %known = map { $_->{identifier} => $_->{name} } default_channels();
	return $known{$identifier} if ($known{$identifier});

	my $name = $identifier;
	$name =~ s/\A\d+-\d+://;
	$name =~ s/[^0-9A-Za-z]+/_/g;
	$name =~ s/^_+|_+$//g;
	return "Custom_OBIS_$name";
}

sub read_obis_discovery_cache
{
	my ($serial) = @_;
	my $file = obis_discovery_cache_file($serial);
	return () if (!-e $file);

	my @channels;
	my %seen;
	if (open(my $fh, "<", $file)) {
		while (my $line = <$fh>) {
			chomp($line);
			my ($identifier, $name) = split(/\t/, $line, 2);
			$identifier = normalize_obis_identifier($identifier);
			next if (!$identifier || $seen{$identifier});
			push @channels, {
				identifier => $identifier,
				name => $name || obis_cache_name($identifier),
			};
			$seen{$identifier} = 1;
		}
		close($fh);
	}
	return @channels;
}

sub obis_discovery_cache_file
{
	my ($serial) = @_;
	$serial =~ s/[^A-Za-z0-9_.:-]/_/g;
	return "$plugin_config_dir/obis_channels_$serial.cache";
}

sub obis_discovery_cache_exists
{
	my ($serial) = @_;
	return -e obis_discovery_cache_file($serial);
}

sub sort_obis_channels
{
	return sort { compare_obis_identifier($a->{identifier}, $b->{identifier}) } @_;
}

sub compare_obis_identifier
{
	my ($left, $right) = @_;
	my @left_parts = obis_sort_parts($left);
	my @right_parts = obis_sort_parts($right);
	for (my $i = 0; $i < @left_parts && $i < @right_parts; $i++) {
		my $cmp = $left_parts[$i] <=> $right_parts[$i];
		return $cmp if ($cmp);
	}
	return ($left || "") cmp ($right || "");
}

sub obis_sort_parts
{
	my ($identifier) = @_;
	return (999, 999, 999, 999, 999) if (!defined($identifier));
	if ($identifier =~ /\A(\d+)-(\d+):([A-Za-z0-9]+)\.(\d+)\.(\d+)\z/) {
		my ($a, $b, $c_part, $d, $e) = ($1, $2, $3, $4, $5);
		my $c = ($c_part =~ /\A\d+\z/) ? int($c_part) : 900 + ord(uc(substr($c_part, 0, 1)));
		return (int($a), int($b), $c, int($d), int($e));
	}
	return (999, 999, 999, 999, 999);
}
