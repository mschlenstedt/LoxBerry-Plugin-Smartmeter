#!/usr/bin/perl

use strict;
use warnings;

use Config::Simple;
use File::Path qw(make_path);
use IO::Socket;
use JSON::PP;
use LoxBerry::System;

my $home = $lbhomedir;
my $psubfolder = $lbpplugindir;
my $config_file = "$home/config/plugins/$psubfolder/smartmeter.cfg";
my $mapping_file = "$home/config/plugins/$psubfolder/vzlogger_channels.json";
my $runtime_dir = "/var/run/shm/$psubfolder";
my $log_file = "$runtime_dir/vzlogger_mqtt_bridge.log";
my $pid_file = "$runtime_dir/vzlogger_mqtt_bridge.pid";
my $foreground = grep { $_ eq "--foreground" } @ARGV;

make_path($runtime_dir) if (!-d $runtime_dir);

if (grep { $_ eq "--stop" } @ARGV) {
	stop_bridge();
	exit 0;
}

if (grep { $_ eq "--status" } @ARGV) {
	exit bridge_running() ? 0 : 1;
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
my $base_topic = sanitize_topic($plugin_cfg->param("MAIN.MQTTTOPIC") || "smartmeter");
my $subscribe_topic = "$base_topic/vzlogger/#";
my $udp_interval = cron_to_seconds($plugin_cfg->param("VZLOGGER.UDPINTERVAL") || $plugin_cfg->param("MAIN.CRON") || "5");
my $send_udp = $plugin_cfg->param("MAIN.SENDUDP") ? 1 : 0;
my $debug_enabled = ($plugin_cfg->param("VZLOGGER.DEBUG") || "0") eq "1";
my $udp_port = clean_number($plugin_cfg->param("MAIN.UDPPORT"), 7000);
my $mqtt = read_mqtt_settings();

log_line("Starting MQTT bridge. Topic=$subscribe_topic Host=$mqtt->{host}:$mqtt->{port}");
log_line("Debug logging is enabled.") if ($debug_enabled);

my @command = (
	"mosquitto_sub",
	"-h", $mqtt->{host},
	"-p", $mqtt->{port},
	"-t", $subscribe_topic,
	"-F", "%t %p",
);
push @command, ("-u", $mqtt->{user}) if ($mqtt->{user});
push @command, ("-P", $mqtt->{pass}) if ($mqtt->{pass});

open(my $mqtt_fh, "-|", @command) or die "Could not start mosquitto_sub: $!\n";

my %values_by_serial;
my $last_udp = 0;

while (my $line = <$mqtt_fh>) {
	chomp($line);
	next if ($line eq "");

	my ($topic, $payload) = split(/\s+/, $line, 2);
	next if (!defined($payload));
	debug_line("MQTT raw topic=$topic payload=$payload");

	my $reading = parse_reading($topic, $payload, $mapping);
	if (!$reading) {
		debug_line("MQTT ignored topic=$topic payload=$payload");
		next;
	}
	debug_line("MQTT parsed serial=$reading->{serial} name=$reading->{name} uuid=$reading->{uuid} value=$reading->{value}");

	$values_by_serial{$reading->{serial}}->{$reading->{name}} = $reading->{value};
	write_cache($reading->{serial}, $values_by_serial{$reading->{serial}});

	if ($send_udp && time() - $last_udp >= $udp_interval) {
		send_udp(\%values_by_serial, $udp_port);
		$last_udp = time();
	}
}

log_line("mosquitto_sub ended.");
unlink($pid_file);
exit 0;

sub parse_reading
{
	my ($topic, $payload, $mapping) = @_;
	my $json = eval { JSON::PP->new->utf8->decode($payload) };

	my $uuid = "";
	my $value;
	if (!$@ && ref($json)) {
		$uuid = $json->{uuid} || $json->{channel} || "";
		$value = defined($json->{value}) ? $json->{value} : $json->{data};
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
		uuid => $uuid,
		value => $value,
	};
}

sub write_cache
{
	my ($serial, $values) = @_;
	my $target = "$runtime_dir/$serial.data";
	my $tmp = "$target.$$";

	open(my $fh, ">", $tmp) or do {
		log_line("Could not write $tmp: $!");
		return;
	};
	foreach my $name (sort keys %$values) {
		print $fh "$serial:$name:$values->{$name}\n";
	}
	close($fh);
	rename($tmp, $target) or log_line("Could not replace $target: $!");
}

sub send_udp
{
	my ($values, $port) = @_;
	my @targets = miniserver_targets();

	foreach my $serial (sort keys %$values) {
		my $payload = join("; ", map { "$serial:$_:$values->{$serial}->{$_}" } sort keys %{$values->{$serial}});
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
	);

	my $general = read_json($general_json);
	return \%settings if (!ref($general) || !ref($general->{Mqtt}));

	my $mqtt = $general->{Mqtt};
	$settings{host} = first_value($mqtt, qw(Host Hostname Broker Brokerhost Server IpAddress Ipaddress)) || $settings{host};
	$settings{port} = clean_number(first_value($mqtt, qw(Port Brokerport Mqttport)), $settings{port});
	$settings{user} = first_value($mqtt, qw(User Username Login)) || "";
	$settings{pass} = first_value($mqtt, qw(Pass Password)) || "";
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
	open(my $fh, ">>", $log_file) or return;
	my ($sec, $min, $hour, $mday, $mon, $year) = localtime();
	printf $fh "%04d-%02d-%02d %02d:%02d:%02d %s\n", $year + 1900, $mon + 1, $mday, $hour, $min, $sec, $message;
	close($fh);
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
