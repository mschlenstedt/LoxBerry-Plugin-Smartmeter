#!/usr/bin/perl

use strict;
use warnings;

use Config::Simple;
use File::Path qw(make_path);
use FindBin;
use IO::Socket;
use JSON::PP;
use LoxBerry::System;
use lib $FindBin::Bin;
use SmartMeterVZLoggerChannels qw(output_order_mapping ordered_output_names);

my $home = $lbhomedir;
my $psubfolder = $lbpplugindir;
my $config_file = "$home/config/plugins/$psubfolder/smartmeter.cfg";
my $mapping_file = "$home/config/plugins/$psubfolder/vzlogger_channels.json";
my $vzlogger_config_file = "$home/config/plugins/$psubfolder/vzlogger.conf";
my $runtime_dir = "/var/run/shm/$psubfolder";
my $plugin_log_dir = "$home/log/plugins/$psubfolder";
my $log_file = "$plugin_log_dir/vzlogger_mqtt_bridge.log";
my $pid_file = "$runtime_dir/vzlogger_mqtt_bridge.pid";
my $foreground = grep { $_ eq "--foreground" } @ARGV;

make_path($runtime_dir) if (!-d $runtime_dir);
make_path($plugin_log_dir) if (!-d $plugin_log_dir);

if (grep { $_ eq "--stop" } @ARGV) {
	stop_bridge();
	exit 0;
}

if (grep { $_ eq "--status" } @ARGV) {
	exit(bridge_running() ? 0 : 1);
}

if (!$foreground && bridge_running()) {
	log_line("Bridge already running.");
	exit 0;
}

open(my $pid_fh, ">", $pid_file) or die "Could not write $pid_file: $!\n";
print $pid_fh "$$\n";
close($pid_fh);

$SIG{TERM} = sub {
	unlink($pid_file);
	exit 0;
};
$SIG{INT} = sub {
	unlink($pid_file);
	exit 0;
};

my $plugin_cfg = Config::Simple->new($config_file) or die "Could not read $config_file: " . Config::Simple->error() . "\n";
my $mapping = read_json($mapping_file) || {};
my $expert_config = (($plugin_cfg->param("VZLOGGER.EXPERTMODE") || "0") eq "1") ? read_json($vzlogger_config_file) : undef;
my $expert_mqtt = ref($expert_config) eq "HASH" && ref($expert_config->{mqtt}) eq "HASH" ? $expert_config->{mqtt} : undef;
my $base_topic = sanitize_topic(ref($expert_mqtt) eq "HASH" ? ($expert_mqtt->{topic} || "smartmeter") : ($plugin_cfg->param("MAIN.MQTTTOPIC") || "smartmeter"));
my $subscribe_topic = "$base_topic/vzlogger/#";
my $update_interval = clean_number($plugin_cfg->param("VZLOGGER.UDPINTERVAL"), 5);
my $send_udp = $plugin_cfg->param("MAIN.SENDUDP") ? 1 : 0;
my $debug_enabled = ($plugin_cfg->param("VZLOGGER.DEBUG") || "0") eq "1";
my $udp_port = clean_number($plugin_cfg->param("MAIN.UDPPORT"), 7000);
my $mqtt = read_mqtt_settings();
my %uuid_by_channel = channel_mapping($mapping);
my %uuid_by_identifier = identifier_mapping($mapping);
my $output_order_by_serial = output_order_mapping($mapping);

log_line("Starting MQTT bridge. Topic=$subscribe_topic Host=$mqtt->{host}:$mqtt->{port}");
log_line("Debug logging is enabled.") if ($debug_enabled);
debug_line("UDP output is disabled in plugin config.") if (!$send_udp);

my @command = (
	"mosquitto_sub",
	"-h", $mqtt->{host},
	"-p", $mqtt->{port},
	"-t", $subscribe_topic,
	"-F", "%t %p",
	"-q", $mqtt->{qos},
);
push @command, ("-k", $mqtt->{keepalive}) if ($mqtt->{keepalive} > 0);
push @command, ("--cafile", $mqtt->{cafile}) if ($mqtt->{cafile});
push @command, ("--capath", $mqtt->{capath}) if ($mqtt->{capath});
push @command, ("--cert", $mqtt->{certfile}) if ($mqtt->{certfile});
push @command, ("--key", $mqtt->{keyfile}) if ($mqtt->{keyfile});
push @command, ("-u", $mqtt->{user}) if ($mqtt->{user});
push @command, ("-P", $mqtt->{pass}) if ($mqtt->{pass});

open(my $mqtt_fh, "-|", @command) or die "Could not start mosquitto_sub: $!\n";

my %values_by_serial;
my %dirty_serials;
my $last_update_cycle = 0;

while (my $line = <$mqtt_fh>) {
	chomp($line);
	next if ($line eq "");

	my ($topic, $payload) = split(/\s+/, $line, 2);
	next if (!defined($payload));
	debug_line("MQTT raw topic=$topic payload=$payload");

	if ($topic =~ m{/([^/]+)/uuid\z}) {
		my $channel = $1;
		if ($payload =~ /\A[0-9a-fA-F-]{36}\z/) {
			$uuid_by_channel{$channel} = lc($payload);
			debug_line("MQTT channel mapping channel=$channel uuid=$payload");
		}
		next;
	}
	if ($topic =~ m{/([^/]+)/id\z}) {
		my $channel = $1;
		my $identifier = clean_scalar_payload($payload);
		if ($identifier && $uuid_by_identifier{$identifier}) {
			$uuid_by_channel{$channel} = $uuid_by_identifier{$identifier};
			debug_line("MQTT channel mapping channel=$channel identifier=$identifier uuid=$uuid_by_identifier{$identifier}");
		}
		next;
	}

	my $reading = parse_reading($topic, $payload, $mapping, \%uuid_by_channel);
	if (!$reading) {
		debug_line("MQTT ignored topic=$topic payload=$payload");
		next;
	}
	debug_line("MQTT parsed serial=$reading->{serial} name=$reading->{name} uuid=$reading->{uuid} value=$reading->{value}");

	update_timestamp($reading, $values_by_serial{$reading->{serial}});
	my $cache_value = normalize_cache_value($reading);
	$values_by_serial{$reading->{serial}}->{$reading->{name}} = $cache_value;
	update_calculated_power($reading, $values_by_serial{$reading->{serial}});
	$dirty_serials{$reading->{serial}} = 1;

	if (time() - $last_update_cycle >= $update_interval) {
		flush_cache(\%values_by_serial, \%dirty_serials, $output_order_by_serial);
		send_udp(\%values_by_serial, $udp_port, $output_order_by_serial) if ($send_udp);
		$last_update_cycle = time();
	}
}

log_line("mosquitto_sub ended.");
unlink($pid_file);
exit 0;

sub parse_reading
{
	my ($topic, $payload, $mapping, $uuid_by_channel) = @_;
	my $json = eval { JSON::PP->new->utf8->decode($payload) };

	my $uuid = "";
	my ($value, $timestamp);
	if (!$@ && ref($json)) {
		$uuid = $json->{uuid} || $json->{channel} || "";
		$value = defined($json->{value}) ? $json->{value} : $json->{data};
		$timestamp = $json->{timestamp} if (defined($json->{timestamp}));
	}

	if ($uuid && !exists($mapping->{$uuid}) && $uuid_by_channel->{$uuid}) {
		$uuid = $uuid_by_channel->{$uuid};
	}

	if (!$uuid) {
		if ($topic =~ m{/([^/]+)/raw\z} && $uuid_by_channel->{$1}) {
			$uuid = $uuid_by_channel->{$1};
		}
	}

	if (!$uuid) {
		foreach my $candidate (keys %$mapping) {
			if ($topic =~ /\Q$candidate\E/) {
				$uuid = $candidate;
				last;
			}
		}
	}

	if (!$uuid) {
		debug_line("MQTT parse failed: no uuid found in topic or payload.");
		return undef;
	}
	if (!exists($mapping->{$uuid})) {
		debug_line("MQTT parse failed: uuid $uuid is not present in channel mapping.");
		return undef;
	}
	$value = $payload if (!defined($value) && $payload =~ /\A-?\d+(?:\.\d+)?\z/);
	if (!defined($value)) {
		debug_line("MQTT parse failed: no value found for uuid $uuid.");
		return undef;
	}

	return {
		serial => $mapping->{$uuid}->{serial},
		name => $mapping->{$uuid}->{name},
		identifier => $mapping->{$uuid}->{identifier} || "",
		uuid => $uuid,
		value => $value,
		timestamp => $timestamp,
	};
}

sub write_cache
{
	my ($serial, $values, $order) = @_;
	my $target = "$runtime_dir/$serial.data";
	my $tmp = "$target.$$";

	open(my $fh, ">", $tmp) or do {
		log_line("Could not write $tmp: $!");
		return;
	};
	foreach my $name (ordered_output_names($values, $order)) {
		print $fh "$serial:$name:$values->{$name}\n";
	}
	close($fh);
	rename($tmp, $target) or log_line("Could not replace $target: $!");
}

sub flush_cache
{
	my ($values_by_serial, $dirty_serials, $output_order_by_serial) = @_;
	foreach my $serial (sort keys %$dirty_serials) {
		next if (!exists($values_by_serial->{$serial}));
		write_cache($serial, $values_by_serial->{$serial}, $output_order_by_serial->{$serial});
	}
	%$dirty_serials = ();
}

sub channel_mapping
{
	my ($mapping) = @_;
	my %channels;
	foreach my $uuid (keys %$mapping) {
		my $entry = $mapping->{$uuid};
		next if (!ref($entry));
		my $channel = $entry->{channel} || "";
		if (!$channel && defined($entry->{channel_index}) && $entry->{channel_index} =~ /\A\d+\z/) {
			$channel = "chn$entry->{channel_index}";
		}
		$channels{$channel} = lc($uuid) if ($channel =~ /\Achn\d+\z/);
	}
	return %channels;
}

sub identifier_mapping
{
	my ($mapping) = @_;
	my %identifiers;
	my %ambiguous;
	foreach my $uuid (keys %$mapping) {
		my $entry = $mapping->{$uuid};
		next if (!ref($entry) || !$entry->{identifier} || $entry->{identifier_ambiguous});
		if (exists($identifiers{$entry->{identifier}})) {
			$ambiguous{$entry->{identifier}} = 1;
		} else {
			$identifiers{$entry->{identifier}} = lc($uuid);
		}
	}
	delete $identifiers{$_} foreach keys %ambiguous;
	return %identifiers;
}

sub clean_scalar_payload
{
	my ($payload) = @_;
	my $json = eval { JSON::PP->new->utf8->decode($payload) };
	if (!$@ && defined($json) && !ref($json)) {
		$payload = $json;
	}
	$payload =~ s/\A\s+|\s+\z//g;
	return $payload;
}

sub update_timestamp
{
	my ($reading, $values) = @_;
	my $epoch = timestamp_epoch($reading->{timestamp});
	$epoch = time() if (!defined($epoch));

	my ($sec, $min, $hour, $mday, $mon, $year) = localtime($epoch);
	$values->{Last_Update} = sprintf("%04d-%02d-%02d %02d:%02d:%02d", $year + 1900, $mon + 1, $mday, $hour, $min, $sec);
	$values->{Last_UpdateLoxEpoche} = $epoch - 1230764400;
}

sub timestamp_epoch
{
	my ($timestamp) = @_;
	return undef if (!defined($timestamp) || $timestamp !~ /\A\d+(?:\.\d+)?\z/);
	$timestamp = int($timestamp);
	$timestamp = int($timestamp / 1000) if ($timestamp > 9999999999);
	return $timestamp;
}

sub normalize_cache_value
{
	my ($reading) = @_;
	my $value = $reading->{value};
	return $value if (!defined($value) || $value !~ /\A-?\d+(?:\.\d+)?\z/);

	if (is_energy_counter($reading->{identifier})) {
		return format_number($value / 1000);
	}
	return format_number($value);
}

sub is_energy_counter
{
	my ($identifier) = @_;
	return defined($identifier) && $identifier =~ /\A1-0:(?:1|2)\.8\.\d+(?:\*\d+)?\z/;
}

sub format_number
{
	my ($value) = @_;
	return int($value) if ($value == int($value));
	$value = sprintf("%.6f", $value);
	$value =~ s/0+\z//;
	$value =~ s/\.\z//;
	return $value;
}

sub update_calculated_power
{
	my ($reading, $values) = @_;
	my $direction = "";
	my $target_name = "";
	if (($reading->{identifier} || "") =~ /\A1-0:1\.8\.0(?:\*\d+)?\z/) {
		$direction = "cons";
		$target_name = "Consumption_CalculatedPower_OBIS_1.99.0";
	} elsif (($reading->{identifier} || "") =~ /\A1-0:2\.8\.0(?:\*\d+)?\z/) {
		$direction = "del";
		$target_name = "Delivery_CalculatedPower_OBIS_2.99.0";
	} else {
		return;
	}

	my $power = calculate_power($reading->{serial}, $direction, $reading->{value});
	$values->{$target_name} = $power if (defined($power));
}

sub calculate_power
{
	my ($serial, $direction, $reading) = @_;
	return undef if (!defined($reading) || $reading !~ /\A-?\d+(?:\.\d+)?\z/);

	my $state_file = "$runtime_dir/$serial.last$direction";
	my $now = time();
	my ($last_time, $last_reading);
	if (-e $state_file && open(my $fh, "<", $state_file)) {
		my $line = <$fh> || "";
		close($fh);
		chomp($line);
		($last_time, $last_reading) = split(/\|/, $line, 2);
	}

	if (!defined($last_time) || !defined($last_reading) || $last_time !~ /\A\d+\z/ || $last_reading !~ /\A-?\d+(?:\.\d+)?\z/ || $reading < $last_reading) {
		write_power_state($state_file, $now, $reading);
		return 0;
	}

	return 0 if ($reading == $last_reading);
	my $hours = ($now - $last_time) / 3600;
	if ($hours <= 0) {
		write_power_state($state_file, $now, $reading);
		return 0;
	}

	my $power = ($reading - $last_reading) / $hours;
	write_power_state($state_file, $now, $reading);
	return sprintf("%.3f", $power);
}

sub write_power_state
{
	my ($state_file, $time, $reading) = @_;
	if (open(my $fh, ">", $state_file)) {
		print $fh "$time|$reading\n";
		close($fh);
	}
}

sub send_udp
{
	my ($values, $port, $output_order_by_serial) = @_;
	my @targets = miniserver_targets();

	foreach my $serial (sort keys %$values) {
		my $payload = join("; ", map { "$serial:$_:$values->{$serial}->{$_}" }
			ordered_output_names($values->{$serial}, $output_order_by_serial->{$serial}));
		next if ($payload eq "");

		foreach my $target (@targets) {
			my $sock = IO::Socket::INET->new(
				Proto => "udp",
				PeerAddr => $target->{ip},
				PeerPort => $port,
			);
			if (!$sock) {
				log_line("$serial: Could not create UDP socket for $target->{name}: $!");
				next;
			}
			$sock->send($payload);
			log_line("$serial: UDP sent to $target->{name} at $target->{ip}:$port");
		}
	}
}

sub miniserver_targets
{
	my $general_cfg = Config::Simple->new("$home/config/system/general.cfg");
	return ({ name => "localhost", ip => "127.0.0.1" }) if (!$general_cfg);

	my $count = clean_number($general_cfg->param("BASE.MINISERVERS"), 0);
	my @targets;
	for (my $i = 1; $i <= $count; $i++) {
		my $name = $general_cfg->param("MINISERVER$i.NAME") || "Miniserver $i";
		my $ip = $general_cfg->param("MINISERVER$i.IPADDRESS") || "127.0.0.1";
		push @targets, { name => $name, ip => $ip };
	}
	return @targets ? @targets : ({ name => "localhost", ip => "127.0.0.1" });
}

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
		qos => clean_qos($plugin_cfg->param("VZLOGGER.MQTTQOS"), 0),
		keepalive => clean_number($plugin_cfg->param("VZLOGGER.MQTTKEEPALIVE"), 30),
	);
	if (ref($expert_mqtt) eq "HASH") {
		foreach my $key (qw(host user pass cafile capath certfile keyfile)) {
			$settings{$key} = "$expert_mqtt->{$key}" if (defined($expert_mqtt->{$key}) && !ref($expert_mqtt->{$key}));
		}
		$settings{port} = clean_number($expert_mqtt->{port}, $settings{port});
		$settings{qos} = clean_qos($expert_mqtt->{qos}, $settings{qos});
		$settings{keepalive} = clean_number($expert_mqtt->{keepalive}, $settings{keepalive});
		return \%settings;
	}

	my $general = read_json($general_json);
	if (ref($general) && ref($general->{Mqtt})) {
		my $mqtt = $general->{Mqtt};
		$settings{host} = first_value($mqtt, qw(Host Hostname Broker Brokerhost Server IpAddress Ipaddress)) || $settings{host};
		$settings{port} = clean_number(first_value($mqtt, qw(Port Brokerport Mqttport)), $settings{port});
		$settings{user} = first_value($mqtt, qw(Brokeruser Brokerusername User Username Login)) || "";
		$settings{pass} = first_value($mqtt, qw(Brokerpass Brokerpassword Pass Password)) || "";
	}
	$settings{host} = plugin_mqtt_text("MQTTHOST", $settings{host});
	$settings{port} = clean_number($plugin_cfg->param("VZLOGGER.MQTTPORT"), $settings{port});
	$settings{cafile} = plugin_mqtt_text("MQTTCAFILE", "");
	$settings{capath} = plugin_mqtt_text("MQTTCAPATH", "");
	$settings{certfile} = plugin_mqtt_text("MQTTCERTFILE", "");
	$settings{keyfile} = plugin_mqtt_text("MQTTKEYFILE", "");
	$settings{user} = plugin_mqtt_text("MQTTUSER", $settings{user});
	$settings{pass} = plugin_mqtt_text("MQTTPASS", $settings{pass});
	return \%settings;
}

sub plugin_mqtt_text
{
	my ($name, $default) = @_;
	my $value = $plugin_cfg->param("VZLOGGER.$name");
	return $default if (!defined($value) || $value eq "");
	$value =~ s/[\r\n]//g;
	return $value;
}

sub clean_qos
{
	my ($value, $default) = @_;
	return int($value) if (defined($value) && $value =~ /\A[01]\z/);
	return $default;
}

sub first_value
{
	my ($hash, @keys) = @_;
	foreach my $key (@keys) {
		return $hash->{$key} if (defined($hash->{$key}) && $hash->{$key} ne "");
	}
	return undef;
}

sub read_json
{
	my ($file) = @_;
	return undef if (!-e $file);
	open(my $fh, "<", $file) or return undef;
	local $/;
	my $text = <$fh>;
	close($fh);
	my $data = eval { JSON::PP->new->utf8->decode($text) };
	return $@ ? undef : $data;
}

sub bridge_running
{
	return 0 if (!-e $pid_file);
	open(my $fh, "<", $pid_file) or return 0;
	my $pid = <$fh>;
	close($fh);
	chomp($pid);
	return 0 if (!$pid || $pid !~ /\A\d+\z/);
	return kill(0, $pid) ? 1 : 0;
}

sub stop_bridge
{
	if (!bridge_running()) {
		unlink($pid_file);
		print "Bridge is not running.\n";
		return;
	}
	open(my $fh, "<", $pid_file) or die "Could not read $pid_file: $!\n";
	my $pid = <$fh>;
	close($fh);
	chomp($pid);
	kill("TERM", $pid);
	print "Stopped bridge process $pid.\n";
}

sub log_line
{
	my ($message) = @_;
	bound_log_file($log_file, 2 * 1024 * 1024);
	open(my $fh, ">>", $log_file) or return;
	my ($sec, $min, $hour, $mday, $mon, $year) = localtime();
	printf $fh "%04d-%02d-%02d %02d:%02d:%02d %s\n", $year + 1900, $mon + 1, $mday, $hour, $min, $sec, $message;
	close($fh);
}

sub bound_log_file
{
	my ($file, $max_bytes) = @_;
	return if (!-e $file || -s $file < $max_bytes);
	unlink("$file.1") if (-e "$file.1");
	rename($file, "$file.1");
}

sub debug_line
{
	my ($message) = @_;
	return if (!$debug_enabled);
	log_line("DEBUG $message");
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
