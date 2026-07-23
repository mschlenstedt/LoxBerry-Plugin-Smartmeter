package SmartMeterVZLoggerConfig;

use strict;
use warnings;
use Exporter qw(import);
use JSON::PP;

our @EXPORT_OK = qw(read_mqtt_settings clean_number clean_qos sanitize_topic protocol_for_meter normalized_meter_mode serial_mode implementation_mode set_implementation_mode);

sub implementation_mode
{
	my ($plugin_cfg) = @_;
	return "none" if (!$plugin_cfg);
	my $mode = $plugin_cfg->param("MAIN.IMPLEMENTATION") || "";
	return $mode if ($mode =~ /\A(?:none|vzlogger)\z/);
	# Configurations written before the Legacy implementation was removed may
	# still carry MAIN.IMPLEMENTATION=legacy. Treat them as inactive so the
	# user has to activate vzLogger explicitly.
	return "none";
}

sub set_implementation_mode
{
	my ($plugin_cfg, $mode) = @_;
	die "Invalid SmartMeter implementation mode.\n" if (!$plugin_cfg || !defined($mode) || $mode !~ /\A(?:vzlogger|none)\z/);
	$plugin_cfg->param("MAIN.IMPLEMENTATION", $mode);
	return $mode;
}

sub protocol_for_meter
{
	my ($meter) = @_;
	return "" if (!defined($meter));
	return "sml" if ($meter =~ /sml\z/i);
	return "d0" if ($meter =~ /(?:d0|do)\z/i);
	return "oms" if ($meter =~ /oms\z/i);
	return "";
}

sub normalized_meter_mode
{
	my ($meter, $manual_protocol) = @_;
	$meter ||= "0";
	return $meter if ($meter =~ /\A(?:0|sml|d0|oms|user)\z/);
	return protocol_for_meter($manual_protocol) || "user" if ($meter eq "manual");
	return protocol_for_meter($meter) || "user";
}

sub serial_mode
{
	my ($databits, $parity, $stopbits) = @_;
	$databits ||= 7;
	$parity ||= "even";
	$stopbits ||= 1;
	my $parity_char = lc($parity) eq "even" ? "E" : lc($parity) eq "odd" ? "O" : "N";
	return "$databits$parity_char$stopbits";
}

sub read_mqtt_settings
{
	my ($home, $plugin_cfg) = @_;
	my %settings = (host => "127.0.0.1", port => 1883, user => "", pass => "", cafile => "", capath => "", certfile => "", keyfile => "", keypass => "");
	my $general_json = "$home/config/system/general.json";
	if (-e $general_json && open(my $fh, "<", $general_json)) {
		local $/;
		my $general = eval { JSON::PP->new->utf8->decode(<$fh> || "") };
		close($fh);
		if (!$@ && ref($general) eq "HASH" && ref($general->{Mqtt}) eq "HASH") {
			my $mqtt = $general->{Mqtt};
			$settings{host} = _first_value($mqtt, qw(Host Hostname Broker Brokerhost Server IpAddress Ipaddress)) || $settings{host};
			$settings{port} = clean_number(_first_value($mqtt, qw(Port Brokerport Mqttport)), $settings{port});
			$settings{user} = _first_value($mqtt, qw(Brokeruser Brokerusername User Username Login)) || "";
			$settings{pass} = _first_value($mqtt, qw(Brokerpass Brokerpassword Pass Password)) || "";
		}
	}
	if ($plugin_cfg) {
		my %keys = (host=>"MQTTHOST",port=>"MQTTPORT",cafile=>"MQTTCAFILE",capath=>"MQTTCAPATH",certfile=>"MQTTCERTFILE",keyfile=>"MQTTKEYFILE",keypass=>"MQTTKEYPASS",user=>"MQTTUSER",pass=>"MQTTPASS");
		foreach my $key (keys %keys) {
			my $value = $plugin_cfg->param("VZLOGGER.$keys{$key}");
			next if (!defined($value) || ref($value) || $value eq "");
			$value =~ s/[\r\n]//g if ($key ne "port");
			$settings{$key} = $key eq "port" ? clean_number($value, $settings{$key}) : "$value";
		}
	}
	return \%settings;
}

sub _first_value
{
	my ($hash, @keys) = @_;
	foreach my $key (@keys) { return $hash->{$key} if (defined($hash->{$key}) && $hash->{$key} ne ""); }
	return undef;
}

sub clean_number
{
	my ($value, $default) = @_;
	return int($value) if (defined($value) && !ref($value) && $value =~ /\A\d+\z/);
	return $default;
}

sub clean_qos
{
	my ($value, $default) = @_;
	$default = 0 if (!defined($default) || ref($default) || $default !~ /\A[012]\z/);
	return defined($value) && !ref($value) && $value =~ /\A[012]\z/ ? int($value) : int($default);
}

sub sanitize_topic
{
	my ($topic) = @_;
	$topic ||= "smartmeter";
	$topic =~ s/^\s+|\s+$//g;
	$topic =~ s{^/+|/+$}{}g;
	$topic =~ s/[#+]//g;
	return $topic || "smartmeter";
}

1;
