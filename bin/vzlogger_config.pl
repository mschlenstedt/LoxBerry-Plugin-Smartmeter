#!/usr/bin/perl

use strict;
use warnings;

use Config::Simple;
use Digest::MD5 qw(md5_hex);
use File::Path qw(make_path);
use FindBin;
use JSON::PP;
use LoxBerry::System;
use lib $FindBin::Bin;
use SmartMeterVZLoggerChannels qw(read_json write_json_atomic load_catalog lookup_obis new_document migrate_legacy_meter validate_document native_channel);

my $home = $lbhomedir;
my $psubfolder = $lbpplugindir;
my $plugin_config_dir = $ENV{SMARTMETER_CONFIG_DIR} || "$home/config/plugins/$psubfolder";
my $config_file = $ENV{SMARTMETER_CONFIG_FILE} || "$plugin_config_dir/smartmeter.cfg";
my $target_file = $ENV{SMARTMETER_VZLOGGER_CONFIG_FILE} || "$plugin_config_dir/vzlogger.conf";
my $mapping_file = $ENV{SMARTMETER_VZLOGGER_MAPPING_FILE} || "$plugin_config_dir/vzlogger_channels.json";
my $definitions_file = $ENV{SMARTMETER_VZLOGGER_DEFINITIONS_FILE} || "$plugin_config_dir/vzlogger_channel_definitions.json";
my $catalog_file = $ENV{SMARTMETER_OBIS_CATALOG_FILE} || "$home/templates/plugins/$psubfolder/obis_catalog.json";
my $plugin_cfg = Config::Simple->new($config_file) or die "Could not read $config_file\n";
my $obis_catalog = load_catalog($catalog_file);
my $debug_enabled = ($plugin_cfg->param("VZLOGGER.VZLOGGERDEBUG") || "0") eq "1";
my $log_level = int(clean_log_level($plugin_cfg->param("VZLOGGER.LOGLEVEL"), 0));
my $log_file = $debug_enabled ? "$home/log/plugins/$psubfolder/vzlogger.log" : "/dev/null";

my %flat_config;
Config::Simple->import_from($config_file, \%flat_config);
my $channel_document = read_json($definitions_file);
die "Invalid channel definitions JSON: $definitions_file\n" if (-e $definitions_file && !defined($channel_document));
$channel_document ||= new_document();
$channel_document->{meters} ||= {};
my $channel_document_changed = !-e $definitions_file;

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
	my $meter = $plugin_cfg->param("$section.METER") || "0";
	my $serial = $plugin_cfg->param("$section.SERIAL") || $section;
	my $mode = normalized_meter_mode($meter, $plugin_cfg->param("$section.PROTOCOL"));
	next if ($mode eq "0");

	my $meter_config;
	if ($mode eq "user") {
		my ($custom_meter, $error) = read_user_meter_json($serial);
		if ($error) {
			warn "Skipped invalid custom meter '$serial': $error\n";
			next;
		}
		$meter_config = $custom_meter;
		enrich_user_channels($meter_config, $serial, \%channel_mapping, \$channel_index);
	} else {
		my $device = $plugin_cfg->param("$section.DEVICE") || next;
		$meter_config = standard_meter_config($section, $mode, $device, $vzlogger_mode);

		my $definitions = $channel_document->{meters}->{$serial};
		if (ref($definitions) ne "ARRAY") {
			my @available = available_channels($section);
			my @selected = config_list_values("$section.OBISCHANNELS");
			my @custom = custom_channels($section);
			my $selected_ref = defined($plugin_cfg->param("$section.OBISCHANNELS")) ? \@selected : undef;
			$definitions = migrate_legacy_meter($channel_document, $serial, $psubfolder, \@available, $selected_ref, \@custom, $obis_catalog);
			$channel_document_changed = 1;
		}
		my @channels;
		my $aggtime = clean_integer(config_scalar_value("$section.AGGTIME"), 0);
		foreach my $definition (@$definitions) {
			next if (ref($definition->{plugin_output}) ne "HASH");
			if (exists($definition->{plugin_output}->{legacy_keys})) {
				delete $definition->{plugin_output}->{legacy_keys};
				$channel_document_changed = 1;
			}
		}
		my %identifier_counts;
		foreach my $definition (@$definitions) {
			next if (!$definition->{enabled});
			$identifier_counts{native_channel($definition, $aggtime)->{identifier}}++;
		}
		foreach my $definition (@$definitions) {
			next if (!$definition->{enabled});
			my $channel = native_channel($definition, $aggtime);
			push @channels, $channel;
			my $uuid = $definition->{uuid};
			if ($definition->{plugin_output}->{enabled}) {
				my $catalog_de = lookup_obis($obis_catalog, $channel->{identifier}, "de");
				my $catalog_en = lookup_obis($obis_catalog, $channel->{identifier}, "en");
				my $mapping_entry = {
				serial => $serial,
				name => $definition->{plugin_output}->{key},
				managed_output => JSON::PP::true,
				display_name => $definition->{display_name} || "",
				catalog_name_de => $catalog_de->{known} ? ($catalog_de->{short} || "") : "",
				catalog_name_en => $catalog_en->{known} ? ($catalog_en->{short} || "") : "",
				unit => $catalog_de->{unit} || $catalog_en->{unit} || "",
				display_factor => live_display_factor($channel->{identifier}),
				identifier => $channel->{identifier},
				identifier_ambiguous => $identifier_counts{$channel->{identifier}} > 1 ? JSON::PP::true : JSON::PP::false,
				channel => "chn$channel_index",
				channel_index => $channel_index,
			};
				$channel_mapping{$uuid} = $mapping_entry;
			}
			$channel_index++;
		}
		$meter_config->{channels} = \@channels;
	}
	push @meters, $meter_config;
}

sub live_display_factor
{
	my ($identifier) = @_;
	# vzLogger exposes SML electricity counters in Wh; the catalog and plugin cache use kWh.
	return 0.001 if (defined($identifier) && $identifier =~ /\A1-0:(?:1|2)\.8\.\d+(?:\*\d+)?\z/);
	return 1;
}

my @definition_errors = validate_document($channel_document);
die "Invalid vzLogger channel definitions:\n - " . join("\n - ", @definition_errors) . "\n" if (@definition_errors);

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
	my $value = $optional_mqtt_values{$key};
	$mqtt_config->{$key} = $value if (defined($value) && $value ne "");
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
write_json_atomic($definitions_file, $channel_document) if ($channel_document_changed && !($ENV{SMARTMETER_VALIDATION_DRAFT} || ""));

if (($ENV{SMARTMETER_VALIDATION_DRAFT} || "") eq "1") {
	print "Generated temporary vzLogger configuration with " . scalar(@meters) . " configured meter(s). No saved configuration files were changed.\n";
} else {
	print "Generated $target_file with " . scalar(@meters) . " configured meter(s).\n";
}
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

sub normalized_meter_mode
{
	my ($meter, $manual_protocol) = @_;
	$meter ||= "0";
	return $meter if ($meter =~ /\A(?:0|sml|d0|oms|user)\z/);
	if ($meter eq "manual") {
		my $mapped = protocol_for_meter($manual_protocol);
		return $mapped || "user";
	}
	return "sml" if ($meter =~ /sml\z/i);
	return "d0" if ($meter =~ /(?:d0|do)\z/i);
	return "oms" if ($meter =~ /oms\z/i);
	return "user";
}

sub standard_meter_config
{
	my ($section, $protocol, $device, $implementation_enabled) = @_;
	my $meter_enabled = clean_boolean(config_scalar_value("$section.ENABLED"), 1);
	my $allowskip = clean_boolean(config_scalar_value("$section.ALLOWSKIP"), 1);
	my $meter = {
		enabled => ($implementation_enabled && $meter_enabled) ? JSON::PP::true : JSON::PP::false,
		allowskip => $allowskip ? JSON::PP::true : JSON::PP::false,
		protocol => $protocol,
		device => $device,
	};
	set_optional_integer($meter, "aggtime", config_scalar_value("$section.AGGTIME"), 1);

	if ($protocol eq "sml") {
		set_optional_integer($meter, "interval", config_scalar_value("$section.INTERVAL"), 1);
		set_optional_text($meter, "pullseq", config_scalar_value("$section.PULLSEQ"));
		my $legacy_manual = config_scalar_value("$section.METER") eq "manual";
		set_optional_integer($meter, "baudrate", config_scalar_value("$section.BAUDRATE"), 0) if ($legacy_manual || config_scalar_value("$section.BAUDRATESET") eq "1");
		set_optional_enum($meter, "parity", configured_parity_optional($section), qr/\A(?:8n1|7e1|7o1|7n1)\z/i) if ($legacy_manual || config_scalar_value("$section.PARITYSET") eq "1");
		set_optional_boolean($meter, "use_local_time", config_scalar_value("$section.USELOCALTIME"));
	} elsif ($protocol eq "d0") {
		set_optional_integer($meter, "interval", config_scalar_value("$section.INTERVAL"), 1);
		set_optional_text($meter, "dump_file", config_scalar_value("$section.DUMPFILE"));
		set_optional_text($meter, "pullseq", config_scalar_value("$section.PULLSEQ"));
		set_optional_text($meter, "ackseq", config_scalar_value("$section.ACKSEQ"));
		set_optional_integer($meter, "baudrate", config_scalar_value("$section.BAUDRATE"), 0);
		set_optional_integer($meter, "baudrate_read", config_scalar_value("$section.BAUDRATEREAD"), 0);
		set_optional_enum($meter, "parity", configured_parity_optional($section), qr/\A(?:8n1|7e1|7o1|7n1)\z/i);
		set_optional_enum($meter, "wait_sync", config_scalar_value("$section.WAITSYNC"), qr/\A(?:off|end)\z/);
		set_optional_integer($meter, "read_timeout", first_config_value($section, "READTIMEOUT", "TIMEOUT"), 0);
		set_optional_integer($meter, "baudrate_change_delay", config_scalar_value("$section.BAUDRATECHANGEDELAY"), 0);
	} elsif ($protocol eq "oms") {
		set_optional_integer($meter, "baudrate", config_scalar_value("$section.BAUDRATE"), 0);
		set_optional_enum($meter, "key", config_scalar_value("$section.OMSKEY"), qr/\A[A-Fa-f0-9]{32}\z/);
		set_optional_boolean($meter, "mbus_debug", config_scalar_value("$section.MBUSDEBUG"));
		set_optional_boolean($meter, "use_local_time", config_scalar_value("$section.USELOCALTIME"));
	}
	return $meter;
}

sub config_scalar_value
{
	my ($key) = @_;
	my @values = $plugin_cfg->param($key);
	return "" if (!@values);
	return "" if (!defined($values[0]) || ref($values[0]));
	return "$values[0]";
}

sub set_optional_text
{
	my ($target, $key, $value) = @_;
	return if (!defined($value) || ref($value) || $value eq "");
	$value =~ s/[\r\n]//g;
	$target->{$key} = $value if ($value ne "");
}

sub set_optional_integer
{
	my ($target, $key, $value, $allow_negative) = @_;
	return if (!defined($value) || ref($value) || $value eq "");
	my $pattern = $allow_negative ? qr/\A-?\d+\z/ : qr/\A\d+\z/;
	$target->{$key} = int($value) if ($value =~ $pattern);
}

sub set_optional_enum
{
	my ($target, $key, $value, $pattern) = @_;
	return if (!defined($value) || ref($value) || $value eq "");
	$target->{$key} = lc($value) if ($value =~ $pattern);
}

sub set_optional_boolean
{
	my ($target, $key, $value) = @_;
	return if (!defined($value) || ref($value) || $value !~ /\A[01]\z/);
	$target->{$key} = $value eq "1" ? JSON::PP::true : JSON::PP::false;
}

sub user_meter_file
{
	my ($serial) = @_;
	$serial =~ s/[^A-Za-z0-9_.:-]/_/g;
	return "$plugin_config_dir/vzlogger_meter_" . ($serial || "unknown") . ".jsonc";
}

sub read_user_meter_json
{
	my ($serial) = @_;
	my $file = user_meter_file($serial);
	return (undef, "JSONC source file does not exist") if (!-e $file);
	return (undef, "JSONC source exceeds 64 KiB") if (-s $file > 65536);
	open(my $fh, "<", $file) or return (undef, "Could not read JSONC source: $!");
	local $/;
	my $source = <$fh>;
	close($fh);
	my $meter = eval { JSON::PP->new->utf8->relaxed(1)->decode($source) };
	if ($@) {
		my $error = $@;
		$error =~ s/\s+at\s+\S+\s+line\s+\d+\.?\s*\z//;
		return (undef, $error || "Invalid JSONC");
	}
	return (undef, "The JSONC source must contain one meter object") if (ref($meter) ne "HASH");
	return (undef, "Root sections such as meters, mqtt, local, push or retry are not allowed") if (grep { exists($meter->{$_}) } qw(meters mqtt local push retry verbosity log));
	return (undef, "The meter object requires a non-empty protocol string") if (!defined($meter->{protocol}) || ref($meter->{protocol}) || $meter->{protocol} eq "");
	if (exists($meter->{channels})) {
		return (undef, "channels must be an array") if (ref($meter->{channels}) ne "ARRAY");
		foreach my $channel (@{$meter->{channels}}) {
			return (undef, "Every channels entry must be an object") if (ref($channel) ne "HASH");
		}
	}
	return ($meter, "");
}

sub enrich_user_channels
{
	my ($meter, $serial, $mapping, $index_ref) = @_;
	return if (!exists($meter->{channels}));
	my $meter_channel_index = 0;
	foreach my $channel (@{$meter->{channels}}) {
		my $identifier = defined($channel->{identifier}) && !ref($channel->{identifier}) ? "$channel->{identifier}" : "";
		my $index = ${$index_ref};
		$channel->{uuid} = stable_uuid("$psubfolder:$serial:$meter_channel_index:$identifier") if (!defined($channel->{uuid}) || ref($channel->{uuid}) || $channel->{uuid} eq "");
		$channel->{api} = "null" if (!exists($channel->{api}));
		my $uuid = defined($channel->{uuid}) && !ref($channel->{uuid}) ? "$channel->{uuid}" : "";
		if ($uuid ne "") {
			$mapping->{$uuid} = {
				serial => $serial,
				name => user_channel_name($channel, $identifier, $meter_channel_index),
				identifier => $identifier,
				channel => "chn$index",
				channel_index => $index,
			};
		}
		${$index_ref}++;
		$meter_channel_index++;
	}
}

sub user_channel_name
{
	my ($channel, $identifier, $index) = @_;
	return "$channel->{name}" if (defined($channel->{name}) && !ref($channel->{name}) && $channel->{name} ne "");
	return obis_cache_name($identifier) if (normalize_obis_identifier($identifier));
	return "Channel_$index" if (!defined($identifier) || $identifier eq "");
	my $name = $identifier;
	$name =~ s/[^A-Za-z0-9]+/_/g;
	$name =~ s/^_+|_+$//g;
	return $name || "Channel_$index";
}

sub first_config_value
{
	my ($section, @keys) = @_;
	foreach my $key (@keys) {
		my $value = config_scalar_value("$section.$key");
		return $value if (defined($value) && $value ne "");
	}
	return undef;
}

sub configured_parity_optional
{
	my ($section) = @_;
	my $mode = config_scalar_value("$section.PARITYMODE");
	return lc($mode) if (defined($mode) && $mode =~ /\A(?:8n1|7e1|7o1|7n1)\z/i);
	my $legacy = serial_mode(
		$plugin_cfg->param("$section.DATABITS"),
		$plugin_cfg->param("$section.PARITY"),
		$plugin_cfg->param("$section.STOPBITS")
	);
	return lc($legacy) if ($legacy && first_config_value($section, "DATABITS", "PARITY", "STOPBITS"));
	return "";
}

sub clean_text_allow_empty
{
	my ($value) = @_;
	return "" if (!defined($value));
	$value =~ s/[\r\n]//g;
	return $value;
}

sub protocol_for_meter
{
	my ($meter) = @_;
	return "" if (!defined($meter));
	return "sml" if ($meter =~ /sml\z/i);
	return "d0" if ($meter =~ /d0\z/i || $meter =~ /do\z/i);
	return "oms" if ($meter =~ /oms\z/i);
	return "";
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
		meter => [qw(enabled allowskip aggtime protocol device interval host dump_file pullseq ackseq baudrate baudrate_read parity wait_sync read_timeout baudrate_change_delay key mbus_debug use_local_time channels)],
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
	return $value if ($value =~ /\A(?:\d+-\d+:)?[A-Za-z0-9]+\.\d+\.\d+(?:\*(?:[0-9]|[1-9][0-9]|255))?\z/);
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
	return (999, 999, 999, 999, 999, 999) if (!defined($identifier));
	if ($identifier =~ /\A(\d+)-(\d+):([A-Za-z0-9]+)\.(\d+)\.(\d+)(?:\*(\d+))?\z/) {
		my ($a, $b, $c_part, $d, $e, $f) = ($1, $2, $3, $4, $5, $6);
		my $c = ($c_part =~ /\A\d+\z/) ? int($c_part) : 900 + ord(uc(substr($c_part, 0, 1)));
		return (int($a), int($b), $c, int($d), int($e), defined($f) ? int($f) : 255);
	}
	if ($identifier =~ /\A([A-Za-z0-9]+)\.(\d+)\.(\d+)(?:\*(\d+))?\z/) {
		my ($a_part, $b, $c, $f) = ($1, $2, $3, $4);
		my $a = ($a_part =~ /\A\d+\z/) ? int($a_part) : 900 + ord(uc(substr($a_part, 0, 1)));
		return (0, 0, $a, int($b), int($c), defined($f) ? int($f) : 255);
	}
	return (999, 999, 999, 999, 999, 999);
}
