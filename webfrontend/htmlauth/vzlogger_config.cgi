#!/usr/bin/perl
use strict;
use warnings;
use CGI;
use FindBin;
use File::Temp qw(tempdir);
use JSON::PP;
use LoxBerry::System;
use lib $lbpbindir;
use lib "$FindBin::Bin/../../bin";
use SmartMeterConfig;
use SmartMeterVZLoggerChannels qw(read_json write_json_atomic);
use SmartMeterVZLoggerExpert qw(read_text write_text_atomic validate_expert_text format_expert_validation localize_expert_validation build_expert_mapping);
use SmartMeterVZLoggerRuntime qw(acquire_config_lock promote_files_atomic);

require LoxBerry::Web;

sub localized_template
{
	my ($name) = @_;
	my $template = HTML::Template->new(
		filename => "$lbptemplatedir/$name",
		global_vars => 1,
		die_on_bad_params => 0,
	);
	my %phrases = LoxBerry::System::readlanguage($template, "language.ini");
	return ($template, \%phrases);
}

my $maximum_size = 1024 * 1024;
my ($language_template, $phrases) = localized_template("vzlogger_config_editor.html");
my $content_length = $ENV{CONTENT_LENGTH} || 0;
if ($content_length =~ /\A\d+\z/ && $content_length > $maximum_size + 65536) {
	print "Status: 413 Payload Too Large\r\nContent-Type: text/plain; charset=utf-8\r\nCache-Control: no-store\r\n\r\n$phrases->{'VZLOGGER.CONFIG_TOO_LARGE'}\n";
	exit 0;
}

my $cgi = CGI->new;
my $runtime_file = "$lbpconfigdir/vzlogger.conf";
my $expert_file = "$lbpconfigdir/vzlogger_expert.conf";
my $mapping_file = "$lbpconfigdir/vzlogger_channels.json";
my $plugin_cfg = SmartMeterConfig->new("$lbpconfigdir/smartmeter.json");
my $expert_mode = $plugin_cfg && ($plugin_cfg->param("VZLOGGER.EXPERTMODE") || "0") eq "1";

sub header_html
{
	print $cgi->header(
		-type => "text/html",
		-charset => "utf-8",
		-expires => "now",
		-Cache_Control => "no-store, no-cache, must-revalidate",
		-Pragma => "no-cache",
		-X_Content_Type_Options => "nosniff",
		-X_Frame_Options => "SAMEORIGIN",
		-Referrer_Policy => "no-referrer",
	);
}

sub fail_plain
{
	my ($status, $message) = @_;
	print $cgi->header(-status => $status, -type => "text/plain", -charset => "utf-8", -Cache_Control => "no-store", -X_Content_Type_Options => "nosniff");
	print "$message\n";
	exit 0;
}

if (($ENV{REQUEST_METHOD} || "GET") eq "POST") {
	fail_plain("403 Forbidden", $phrases->{'VZLOGGER.CONFIG_EXPERT_INACTIVE'}) if (!$expert_mode);
	my ($config_lock, $lock_error) = acquire_config_lock("/var/run/shm/$lbpplugindir");
	fail_plain("409 Conflict", $lock_error) if (!$config_lock);
	my $text = $cgi->param("config");
	$text = "" if (!defined($text));
	# HTML form encoding serializes textarea line endings as CRLF. Normalize them
	# back to the LF representation shown in the editor before storing the file.
	$text =~ s/\r\n?/\n/g;
	fail_plain("413 Payload Too Large", $phrases->{'VZLOGGER.CONFIG_EXCEEDS_LIMIT'}) if (length($text) > $maximum_size);
	fail_plain("500 Internal Server Error", $phrases->{'VZLOGGER.CONFIG_SAVE_FAILED'}) if (!write_text_atomic($expert_file, $text));

	my $result = validate_expert_text($text);
	if ($result->{valid}) {
		my $existing = read_json($mapping_file) || {};
		my ($mapping, $mapping_warnings) = build_expert_mapping($result->{config}, $existing);
		push @{$result->{warnings}}, @$mapping_warnings;
		my $stage = tempdir(".vzlogger-expert-stage-XXXXXX", DIR => $lbpconfigdir, CLEANUP => 1);
		my $stage_runtime = "$stage/vzlogger.conf";
		my $stage_mapping = "$stage/vzlogger_channels.json";
		my $runtime_ok = write_text_atomic($stage_runtime, $text);
		my $mapping_ok = $runtime_ok ? eval { write_json_atomic($stage_mapping, $mapping); 1 } : 0;
		my ($promoted, $promotion_error) = $mapping_ok
			? promote_files_atomic([[$stage_runtime, $runtime_file, 0600], [$stage_mapping, $mapping_file, 0600]])
			: (0, $phrases->{'VZLOGGER.CONFIG_STAGE_MAPPING_FAILED'});
		if (!$runtime_ok || !$mapping_ok || !$promoted) {
			push @{$result->{errors}}, $phrases->{'VZLOGGER.CONFIG_RUNTIME_UPDATE_FAILED'};
			push @{$result->{errors}}, $promotion_error if ($promotion_error);
			$result->{valid} = 0;
		}
	}
	my $message = format_expert_validation(localize_expert_validation($result, $phrases));
	my $payload = JSON::PP->new->ascii->encode({
		type => "smartmeter-vzlogger-expert",
		valid => $result->{valid} ? JSON::PP::true : JSON::PP::false,
		message => $message,
	});
	header_html();
	my ($result_template, $result_phrases) = localized_template("vzlogger_config_result.html");
	$result_template->param(
		RESULT_TITLE => $result->{valid} ? $result_phrases->{'VZLOGGER.CONFIG_SAVED_TITLE'} : $result_phrases->{'VZLOGGER.CONFIG_SAVED_ERRORS_TITLE'},
		RESULT_MESSAGE => $message,
		RESULT_PAYLOAD => $payload,
	);
	print $result_template->output();
	exit 0;
}

if (!$expert_mode) {
	my $config = read_text($runtime_file);
	fail_plain("404 Not Found", $phrases->{'VZLOGGER.CONFIG_GENERATED_MISSING'}) if (!defined($config));
	$config =~ s/("(?:key)?pass(?:word)?"\s*:\s*")((?:\\.|[^"\\])*)(")/$1***REDACTED***$3/ig;
	$config =~ s/("(?:token|secretKey)"\s*:\s*")((?:\\.|[^"\\])*)(")/$1***REDACTED***$3/ig;
	my @lines = split(/\n/, $config, -1);
	my $rendered = join("\n", map { "<li><code>" . CGI::escapeHTML($_) . "</code></li>" } @lines);
	header_html();
	my ($readonly_template) = localized_template("vzlogger_config_readonly.html");
	$readonly_template->param(CONFIG_LINES => $rendered);
	print $readonly_template->output();
	exit 0;
}

my $config = read_text($expert_file);
$config = read_text($runtime_file) if (!defined($config));
$config = "" if (!defined($config));
header_html();
$language_template->param(MAXIMUM_SIZE => $maximum_size, CONFIG_TEXT => $config);
print $language_template->output();
