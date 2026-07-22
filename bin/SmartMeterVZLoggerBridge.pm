package SmartMeterVZLoggerBridge;

use strict;
use warnings;
use Exporter qw(import);
use JSON::PP;

our @EXPORT_OK = qw(parse_reading channel_mapping identifier_mapping clean_scalar_payload normalize_mapping_keys);

sub normalize_mapping_keys
{
	my ($mapping) = @_;
	return ({}, "") if (ref($mapping) ne "HASH");
	my %normalized;
	foreach my $uuid (keys %$mapping) {
		my $canonical = lc($uuid);
		return (undef, "Duplicate channel mapping UUID after case normalization: $uuid")
			if (exists($normalized{$canonical}));
		$normalized{$canonical} = $mapping->{$uuid};
	}
	return (\%normalized, "");
}

sub parse_reading
{
	my ($topic, $payload, $mapping, $uuid_by_channel, $debug) = @_;
	$debug ||= sub {};
	my $json = eval { JSON::PP->new->utf8->decode($payload) };
	my $uuid = "";
	my ($value, $timestamp);
	if (!$@ && ref($json) eq "HASH") {
		$uuid = $json->{uuid} || $json->{channel} || "";
		$value = defined($json->{value}) ? $json->{value} : $json->{data};
		$timestamp = $json->{timestamp} if (defined($json->{timestamp}));
	}
	$uuid = lc($uuid) if ($uuid);
	$uuid = $uuid_by_channel->{$uuid} if ($uuid && !exists($mapping->{$uuid}) && $uuid_by_channel->{$uuid});
	$uuid = $uuid_by_channel->{$1} if (!$uuid && $topic =~ m{/([^/]+)/raw\z} && $uuid_by_channel->{$1});
	if (!$uuid) {
		foreach my $candidate (keys %$mapping) {
			if ($topic =~ /\Q$candidate\E/) { $uuid = $candidate; last; }
		}
	}
	if (!$uuid) { $debug->("MQTT parse failed: no uuid found in topic or payload."); return undef; }
	if (!exists($mapping->{$uuid})) { $debug->("MQTT parse failed: uuid $uuid is not present in channel mapping."); return undef; }
	$value = $payload if (!defined($value) && $payload =~ /\A-?\d+(?:\.\d+)?\z/);
	if (!defined($value)) { $debug->("MQTT parse failed: no value found for uuid $uuid."); return undef; }
	return {
		serial => $mapping->{$uuid}->{serial}, name => $mapping->{$uuid}->{name},
		identifier => $mapping->{$uuid}->{identifier} || "", uuid => $uuid,
		value => $value, timestamp => $timestamp,
	};
}

sub channel_mapping
{
	my ($mapping) = @_;
	my %channels;
	foreach my $uuid (keys %{ref($mapping) eq "HASH" ? $mapping : {}}) {
		my $entry = $mapping->{$uuid};
		next if (ref($entry) ne "HASH");
		my $channel = $entry->{channel} || "";
		$channel = "chn$entry->{channel_index}" if (!$channel && defined($entry->{channel_index}) && $entry->{channel_index} =~ /\A\d+\z/);
		$channels{$channel} = $uuid if ($channel =~ /\Achn\d+\z/);
	}
	return %channels;
}

sub identifier_mapping
{
	my ($mapping) = @_;
	my (%identifiers, %ambiguous);
	foreach my $uuid (keys %{ref($mapping) eq "HASH" ? $mapping : {}}) {
		my $entry = $mapping->{$uuid};
		next if (ref($entry) ne "HASH" || !$entry->{identifier} || $entry->{identifier_ambiguous});
		if (exists($identifiers{$entry->{identifier}})) { $ambiguous{$entry->{identifier}} = 1; }
		else { $identifiers{$entry->{identifier}} = $uuid; }
	}
	delete $identifiers{$_} foreach keys %ambiguous;
	return %identifiers;
}

sub clean_scalar_payload
{
	my ($payload) = @_;
	my $json = eval { JSON::PP->new->utf8->decode($payload) };
	$payload = $json if (!$@ && defined($json) && !ref($json));
	$payload =~ s/\A\s+|\s+\z//g;
	return $payload;
}

1;
