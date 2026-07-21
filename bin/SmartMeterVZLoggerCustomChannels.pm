package SmartMeterVZLoggerCustomChannels;

use strict;
use warnings;
use Digest::SHA qw(sha256_hex);
use Exporter qw(import);
use JSON::PP;
use SmartMeterVZLoggerChannels qw(read_json stable_uuid write_json_atomic);

our @EXPORT_OK = qw(assign_custom_channel_uuids registry_file channel_fingerprint);

sub registry_file
{
	my ($directory, $serial) = @_;
	$serial = "unknown" if (!defined($serial) || $serial eq "");
	$serial =~ s/[^A-Za-z0-9_.:-]/_/g;
	return "$directory/vzlogger_user_channel_uuids_$serial.json";
}

sub channel_fingerprint
{
	my ($channel) = @_;
	return "" if (ref($channel) ne "HASH");
	my %copy = %$channel;
	delete $copy{uuid};
	my $json = JSON::PP->new->utf8->canonical->encode(\%copy);
	return sha256_hex($json);
}

sub assign_custom_channel_uuids
{
	my ($meter, $serial, $plugin_id, $directory) = @_;
	return (0, "") if (ref($meter) ne "HASH" || ref($meter->{channels}) ne "ARRAY");
	my $file = registry_file($directory, $serial);
	my $registry = read_json($file);
	my $new_registry = ref($registry) eq "HASH" && ($registry->{version} || 0) == 1 &&
		ref($registry->{channels}) eq "HASH" ? $registry : { version => 1, serial => $serial, channels => {} };
	$new_registry->{version} = 1;
	$new_registry->{serial} = $serial;
	my %used;
	my %occurrence;
	my $changed = !-e $file;
	for (my $index = 0; $index < @{$meter->{channels}}; $index++) {
		my $channel = $meter->{channels}->[$index];
		my $fingerprint = channel_fingerprint($channel);
		my $position = $occurrence{$fingerprint}++;
		my $uuid = defined($channel->{uuid}) && !ref($channel->{uuid}) ? "$channel->{uuid}" : "";
		my $known = $new_registry->{channels}->{$fingerprint};
		$known = [] if (ref($known) ne "ARRAY");
		if ($uuid eq "") {
			$uuid = $known->[$position] || stable_uuid("$plugin_id:$serial:$index:" .
				(defined($channel->{identifier}) && !ref($channel->{identifier}) ? $channel->{identifier} : ""));
			$channel->{uuid} = $uuid;
		}
		return (0, "Duplicate custom channel UUID $uuid for reader $serial.") if ($used{lc($uuid)}++);
		if (!defined($known->[$position]) || $known->[$position] ne $uuid) {
			$known->[$position] = $uuid;
			$changed = 1;
		}
		$new_registry->{channels}->{$fingerprint} = $known;
	}
	if ($changed) {
		write_json_atomic($file, $new_registry);
		chmod(0600, $file);
	}
	return (1, "");
}

1;
