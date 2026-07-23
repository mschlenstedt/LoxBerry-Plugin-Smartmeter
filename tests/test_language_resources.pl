#!/usr/bin/perl

use strict;
use warnings;
use utf8;
use Encode qw(decode FB_CROAK);
use File::Find qw(find);
use FindBin;
use JSON::PP;
use Test::More;

my $repo = "$FindBin::Bin/..";
my @sections = qw(COMMON VZLOGGER);

sub slurp_utf8
{
	my ($path) = @_;
	open(my $fh, "<:raw", $path) or die "Cannot read $path: $!";
	local $/;
	my $bytes = <$fh>;
	close($fh);
	return decode("UTF-8", $bytes, FB_CROAK);
}

sub parse_language_content
{
	my ($content, $phrases, $label) = @_;
	my $section = "default";
	my %seen;
	foreach my $line (split(/\n/, $content)) {
		$line =~ s/\r\z//;
		$line =~ s/^\s+|\s+$//g;
		next if $line eq "" || $line =~ m{^[#/;]};
		if ($line =~ /^\[([^]]+)\]$/) {
			$section = $1;
			next;
		}
		my ($key, $value) = split(/=/, $line, 2);
		die "$label contains an invalid line: $line\n" if !defined($value);
		$key =~ s/^\s+|\s+$//g;
		$value =~ s/^\s+|\s+$//g;
		my $full_key = "$section.$key";
		die "$label contains duplicate key $full_key\n" if $seen{$full_key}++;
		if ($value =~ /^"(.*)"$/s) {
			$value = $1;
		}
		$phrases->{$full_key} = $value if !exists($phrases->{$full_key});
	}
}

sub parse_language_file
{
	my ($path) = @_;
	my %phrases;
	parse_language_content(slurp_utf8($path), \%phrases, $path);
	return \%phrases;
}

my $english_path = "$repo/templates/lang/language_en.ini";
my $german_path = "$repo/templates/lang/language_de.ini";
my $english = parse_language_file($english_path);
my $german = parse_language_file($german_path);

is_deeply([sort keys %$german], [sort keys %$english], "German and English resources have identical keys");
ok(!grep(!/^(?:COMMON|VZLOGGER)\.[A-Z][A-Z0-9_]*$/, keys %$english), "only the two documented sections and non-empty keys are used");
is_deeply([sort grep { $german->{$_} eq "" } keys %$german], [], "German resources contain no empty values");
is_deeply([sort grep { $english->{$_} eq "" } keys %$english], [], "English resources contain no empty values");
my @placeholder_mismatches;
foreach my $key (sort keys %$english) {
	my @english_placeholders = sort($english->{$key} =~ /\{([a-z][a-z0-9_]*)\}/g);
	my @german_placeholders = sort($german->{$key} =~ /\{([a-z][a-z0-9_]*)\}/g);
	push @placeholder_mismatches, $key if (join("\0", @german_placeholders) ne join("\0", @english_placeholders));
}
is_deeply(\@placeholder_mismatches, [], "German and English resources use identical placeholders");

my %referenced;
my @template_paths;
find(
	{
		no_chdir => 1,
		wanted => sub {
			push @template_paths, $File::Find::name if -f $_ && /\.html\z/;
		},
	},
	"$repo/templates",
);
foreach my $path (@template_paths) {
	my $source = slurp_utf8($path);
	unlike($source, qr/T::/, "$path contains no legacy T:: translation aliases");
	$referenced{$1} = 1 while $source =~ /<TMPL_(?:VAR|IF|UNLESS)\b[^>]*?\b((?:COMMON|VZLOGGER)\.[A-Z][A-Z0-9_]*)\b/gi;
}

my @runtime_paths;
foreach my $runtime_root (qw(bin webfrontend)) {
	find(
		{
			no_chdir => 1,
			wanted => sub {
				push @runtime_paths, $File::Find::name if -f $_ && /\.(?:cgi|pl|pm|php)\z/;
			},
		},
		"$repo/$runtime_root",
	);
}

my $loader_count = 0;
foreach my $path (@runtime_paths) {
	my $source = slurp_utf8($path);
	unlike($source, qr{load_plugin_language|T::|(?:en|de)/language\.txt|language\.dat}, "$path contains no obsolete language loader or alias");
	$referenced{$3} = 1 while $source =~ /\$([A-Za-z_]\w*)\s*->\s*\{\s*(["'])((?:COMMON|VZLOGGER)\.[A-Z][A-Z0-9_]*)\2\s*\}/g;
	$referenced{$2} = 1 while $source =~ /(["'])(VZLOGGER\.(?:EXPERT|CHANNEL)_VALID_[A-Z0-9_]+)\1/g;

	my $readlanguage_count = () = $source =~ /LoxBerry::System::readlanguage\s*\(/g;
	next if !$readlanguage_count;
	$loader_count += $readlanguage_count;
	my $native_loader_count = () = $source =~ /LoxBerry::System::readlanguage\s*\([^;]*?,\s*["']language\.ini["']\s*\)/g;
	is($native_loader_count, $readlanguage_count, "$path uses language.ini for every readlanguage call");

	my @language_hashes = $source =~ /%([A-Za-z_]\w*)\s*=\s*LoxBerry::System::readlanguage\s*\(/g;
	foreach my $hash (@language_hashes) {
		my $literal_accesses = 0;
		while ($source =~ /\$\Q$hash\E\s*\{\s*(["'])((?:COMMON|VZLOGGER)\.[A-Z][A-Z0-9_]*)\1\s*\}/g) {
			$referenced{$2} = 1;
			$literal_accesses++;
		}
		my $all_accesses = () = $source =~ /\$\Q$hash\E\s*\{/g;
		is($literal_accesses, $all_accesses, "$path uses only literal canonical keys through %$hash");
	}
}
ok($loader_count > 0, "runtime contains native readlanguage calls");

my @missing = sort grep { !exists($english->{$_}) } keys %referenced;
my @unused = sort grep { !$referenced{$_} } keys %$english;
is_deeply(\@missing, [], "all referenced translation keys exist");
is_deeply(\@unused, [], "all translation keys are referenced");

foreach my $old_path (
	"$repo/templates/en/language.txt",
	"$repo/templates/de/language.txt",
	"$repo/templates/multi/en/language.txt",
	"$repo/templates/multi/de/language.txt",
) {
	ok(!-e $old_path, "$old_path was removed");
}

like($german->{'COMMON.PLEASE_SELECT'}, qr/auswählen/, "German resources retain UTF-8 umlauts");
like($german->{'VZLOGGER.IR_HEADS'}, qr/Zähler/, "German vzLogger text retains UTF-8 umlauts");
is(
	$english->{'VZLOGGER.CHANNEL_API_TAGS_HELP'},
	'Optional InfluxDB tags as a JSON object, for example {"meter":"main"}.',
	"embedded JSON quotes are parsed without visible escape backslashes",
);
like($english->{'VZLOGGER.MQTT_BASE_TOPIC_HELP'}, qr/&lt;base&gt;/, "HTML entities remain intact");

my $live_cgi = slurp_utf8("$repo/webfrontend/htmlauth/vzlogger_live.cgi");
unlike($live_cgi, qr/vzLogger Live-Daten|Daten werden geladen|Kanal-Metadaten konnten/, "live-data CGI contains no embedded German UI phrases");
my $config_cgi = slurp_utf8("$repo/webfrontend/htmlauth/vzlogger_config.cgi");
unlike($config_cgi, qr/HTTP_ACCEPT_LANGUAGE|\$german\b|Configuration saved|Konfiguration gespeichert/, "configuration CGI uses native resources instead of manual bilingual text");
my $settings_template = slurp_utf8("$repo/templates/settings.html");
unlike($settings_template, qr/>None<|>Odd<|>Even<|-Protocol\)/, "visible choices and protocol suffix are localized");

my $meter_templates = JSON::PP->new->decode(slurp_utf8("$repo/templates/meter_templates.json"));
my ($generic_sml) = grep { ($_->{id} || "") eq "genericsml" } @$meter_templates;
is($generic_sml->{label_de}, "Allgemeines SML", "generic SML template has a German display label");
is($generic_sml->{label_en}, "Generic SML", "generic SML template has an English display label");

my $expert_source = slurp_utf8("$repo/bin/SmartMeterVZLoggerExpert.pm");
like($expert_source, qr/Expert vzLogger configuration validation passed\./, "default technical validator output remains English");

my %fallback;
parse_language_content("[TEST]\nSHARED=Deutsch\n", \%fallback, "foreign fixture");
parse_language_content("[TEST]\nSHARED=English\nFALLBACK=English fallback\n", \%fallback, "English fixture");
is($fallback{'TEST.SHARED'}, "Deutsch", "selected language overrides English");
is($fallback{'TEST.FALLBACK'}, "English fallback", "English fills a missing selected-language key");

done_testing();
