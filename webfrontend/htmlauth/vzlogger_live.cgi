#!/usr/bin/perl
use strict;
use warnings;
use CGI;
use Config::Simple;
use IO::Socket::INET;
use JSON::PP;
use LoxBerry::System;
use lib $lbpbindir;
use SmartMeterVZLoggerChannels qw(load_catalog lookup_obis);

require LoxBerry::Web;

my $cgi = CGI->new;
my $template = HTML::Template->new(
	filename => "$lbptemplatedir/vzlogger_live.html",
	global_vars => 1,
	die_on_bad_params => 0,
);
my %L = LoxBerry::System::readlanguage($template, "language.ini");
my $cfg = Config::Simple->new("$lbpconfigdir/smartmeter.cfg");
my $port = $cfg ? ($cfg->param("VZLOGGER.LOCALPORT") || 18080) : 18080;
my $mapping_file = "$lbpconfigdir/vzlogger_channels.json";
my $catalog = load_catalog("$lbptemplatedir/obis_catalog.json");
my $metadata_version = metadata_version($mapping_file, "$lbpconfigdir/smartmeter.cfg", "$lbptemplatedir/obis_catalog.json");
if ($cgi->param("meta")) {
	print $cgi->header(-type => "application/json", -charset => "utf-8", -expires => "now");
	print JSON::PP->new->utf8->canonical->encode(read_channel_metadata($mapping_file, $cfg, $metadata_version, $catalog));
	exit 0;
}
if ($cgi->param("json")) {
	my $json = read_live_json($port);
	print $cgi->header(
		-type => "application/json",
		-charset => "utf-8",
		-expires => "now",
		-X_Smartmeter_Metadata_Version => $metadata_version,
	);
	print $json;
	exit 0;
}
print $cgi->header(-type => "text/html", -charset => "utf-8", -expires => "now");
print $template->output();

sub metadata_version {
	my (@files) = @_;
	return join("-", map {
		my @stat = stat($_);
		@stat ? "$stat[9]:$stat[7]" : "0:0";
	} @files);
}

sub read_channel_metadata {
	my ($file, $plugin_cfg, $version, $obis_catalog) = @_;
	my %channels;
	if (-e $file && open(my $fh, "<", $file)) {
		local $/;
		my $text = <$fh> || "";
		close($fh);
		my $mapping = eval { JSON::PP->new->utf8->decode($text) };
		if (!$@ && ref($mapping) eq "HASH") {
			foreach my $uuid (keys %$mapping) {
				my $entry = $mapping->{$uuid};
				next if (ref($entry) ne "HASH");
				my $serial = $entry->{serial} || "unknown";
				my $catalog_entry = lookup_obis($obis_catalog, $entry->{identifier} || "", "en");
				$channels{lc($uuid)} = {
					serial => $serial,
					head_name => $plugin_cfg ? ($plugin_cfg->param("$serial.NAME") || $serial) : $serial,
					name => $entry->{name} || "",
					display_name => $entry->{display_name} || "",
					catalog_name_de => $entry->{catalog_name_de} || "",
					catalog_name_en => $entry->{catalog_name_en} || "",
					unit => $entry->{unit} || "",
					category => $catalog_entry->{category} || $entry->{category} || "unknown",
					display_factor => defined($entry->{display_factor}) ? 0 + $entry->{display_factor} : 1,
					identifier => $entry->{identifier} || "",
					channel => $entry->{channel} || "",
					channel_index => defined($entry->{channel_index}) ? int($entry->{channel_index}) : 0,
				};
			}
		}
	}
	return {
		version => $version,
		channels => \%channels,
	};
}

sub read_live_json {
	my ($port) = @_;
	my $socket = IO::Socket::INET->new(PeerHost => "127.0.0.1", PeerPort => $port, Proto => "tcp", Timeout => 3);
	return JSON::PP->new->encode({ error => $L{'VZLOGGER.LIVE_HTTP_UNAVAILABLE'} }) if (!$socket);
	print $socket "GET / HTTP/1.0\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n";
	local $/;
	my $response = <$socket> || "";
	close($socket);
	$response =~ s/\A.*?\r?\n\r?\n//s;
	return $response =~ /^\s*[\[{]/ ? $response : JSON::PP->new->encode({ error => $L{'VZLOGGER.LIVE_INVALID_RESPONSE'} });
}
