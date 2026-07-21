#!/usr/bin/perl
use strict;
use warnings;
use CGI;
use Config::Simple;
use FindBin;
use JSON::PP;
use LoxBerry::System;
use lib $lbpbindir;
use lib "$FindBin::Bin/../../bin";
use SmartMeterVZLoggerChannels qw(read_json write_json_atomic);
use SmartMeterVZLoggerExpert qw(read_text write_text_atomic validate_expert_text format_expert_validation build_expert_mapping);

my $maximum_size = 1024 * 1024;
my $content_length = $ENV{CONTENT_LENGTH} || 0;
if ($content_length =~ /\A\d+\z/ && $content_length > $maximum_size + 65536) {
	print "Status: 413 Payload Too Large\r\nContent-Type: text/plain; charset=utf-8\r\nCache-Control: no-store\r\n\r\nExpert configuration is too large.\n";
	exit 0;
}

my $cgi = CGI->new;
my $runtime_file = "$lbpconfigdir/vzlogger.conf";
my $expert_file = "$lbpconfigdir/vzlogger_expert.conf";
my $mapping_file = "$lbpconfigdir/vzlogger_channels.json";
my $plugin_cfg = Config::Simple->new("$lbpconfigdir/smartmeter.cfg");
my $expert_mode = $plugin_cfg && ($plugin_cfg->param("VZLOGGER.EXPERTMODE") || "0") eq "1";
my $german = ($ENV{HTTP_ACCEPT_LANGUAGE} || "") =~ /(?:\A|,)\s*de(?:-|;|,|\z)/i;
my $lang = $german ? "de" : "en";

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
	fail_plain("403 Forbidden", "Expert Mode is not active.") if (!$expert_mode);
	my $text = $cgi->param("config");
	$text = "" if (!defined($text));
	# HTML form encoding serializes textarea line endings as CRLF. Normalize them
	# back to the LF representation shown in the editor before storing the file.
	$text =~ s/\r\n?/\n/g;
	fail_plain("413 Payload Too Large", "Expert configuration exceeds 1 MiB.") if (length($text) > $maximum_size);
	fail_plain("500 Internal Server Error", "Could not save the expert configuration.") if (!write_text_atomic($expert_file, $text));

	my $result = validate_expert_text($text);
	if ($result->{valid}) {
		my $existing = read_json($mapping_file) || {};
		my ($mapping, $mapping_warnings) = build_expert_mapping($result->{config}, $existing);
		push @{$result->{warnings}}, @$mapping_warnings;
		my $previous_runtime = read_text($runtime_file);
		my $previous_mapping = read_json($mapping_file);
		my $runtime_ok = write_text_atomic($runtime_file, $text);
		my $mapping_ok = $runtime_ok ? eval { write_json_atomic($mapping_file, $mapping); 1 } : 0;
		if (!$runtime_ok || !$mapping_ok) {
			write_text_atomic($runtime_file, $previous_runtime) if (defined($previous_runtime));
			eval { write_json_atomic($mapping_file, $previous_mapping) } if (ref($previous_mapping) eq "HASH");
			push @{$result->{errors}}, "The expert draft was saved, but the runtime configuration could not be updated.";
			$result->{valid} = 0;
		}
	}
	my $message = format_expert_validation($result);
	my $payload = JSON::PP->new->ascii->encode({
		type => "smartmeter-vzlogger-expert",
		valid => $result->{valid} ? JSON::PP::true : JSON::PP::false,
		message => $message,
	});
	header_html();
	my $title = $result->{valid} ? ($german ? "Konfiguration gespeichert" : "Configuration saved") : ($german ? "Mit Fehlern gespeichert" : "Saved with errors");
	my $close = $german ? "Fenster schließen" : "Close window";
	print <<"HTML";
<!doctype html><html lang="$lang"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>$title</title>
<style>body{margin:0;background:#f3f5f7;color:#202428;font:15px/1.5 system-ui,sans-serif}.box{max-width:60rem;margin:3rem auto;padding:1.5rem}pre{padding:1rem;border:1px solid #c8ced5;border-radius:6px;background:#fff;white-space:pre-wrap}button{padding:.65rem 1rem}</style></head>
<body><main class="box"><h1>$title</h1><pre>@{[CGI::escapeHTML($message)]}</pre><button type="button" onclick="window.close()">$close</button></main>
<script>var payload=$payload;try{if(window.opener)window.opener.postMessage(payload,window.location.origin)}catch(ignore){}window.setTimeout(function(){window.close()},250);</script></body></html>
HTML
	exit 0;
}

if (!$expert_mode) {
	my $config = read_text($runtime_file);
	fail_plain("404 Not Found", "The generated vzLogger configuration does not exist yet.") if (!defined($config));
	$config =~ s/("(?:key)?pass(?:word)?"\s*:\s*")((?:\\.|[^"\\])*)(")/$1***REDACTED***$3/ig;
	$config =~ s/("(?:token|secretKey)"\s*:\s*")((?:\\.|[^"\\])*)(")/$1***REDACTED***$3/ig;
	my @lines = split(/\n/, $config, -1);
	my $rendered = join("\n", map { "<li><code>" . CGI::escapeHTML($_) . "</code></li>" } @lines);
	my $note = $german ? "Schreibgeschützt · Zugangsdaten sind maskiert" : "Read-only · credentials are masked";
	header_html();
	print <<"HTML";
<!doctype html><html lang="$lang"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>vzlogger.conf</title>
<style>body{margin:0;background:#f3f5f7;color:#202428;font:15px/1.5 system-ui,sans-serif}header{position:sticky;top:0;padding:.8rem 1.2rem;border-bottom:1px solid #c8ced5;background:#fff}h1{margin:0;font-size:1.1rem}p{margin:.2rem 0 0;color:#59636e;font-size:.85rem}main{padding:1rem;overflow:auto}ol{min-width:max-content;margin:0;padding:1rem 1rem 1rem 4.5rem;border:1px solid #c8ced5;border-radius:7px;background:#fff;color:#7a8490}li{min-height:1.5em;padding-left:.8rem;border-left:1px solid #e1e5e9}code{color:#202428;font:14px/1.5 ui-monospace,Consolas,monospace;white-space:pre}</style></head><body><header><h1>vzlogger.conf</h1><p>$note</p></header><main><ol>$rendered</ol></main></body></html>
HTML
	exit 0;
}

my $config = read_text($expert_file);
$config = read_text($runtime_file) if (!defined($config));
$config = "" if (!defined($config));
my $escaped = CGI::escapeHTML($config);
my $note = $german ? "Expert Mode · Die Konfiguration enthält unmaskierte Zugangsdaten." : "Expert Mode · the configuration contains unmasked credentials.";
my $cancel = $german ? "Abbrechen" : "Cancel";
my $save = $german ? "Speichern & Schließen" : "Save & close";
header_html();
print <<"HTML";
<!doctype html><html lang="$lang"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>vzlogger.conf Expert Mode</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f3f5f7;color:#202428;font:15px/1.5 system-ui,sans-serif}form{display:flex;flex-direction:column;height:100vh}header{padding:.75rem 1rem;border-bottom:1px solid #c8ced5;background:#fff}h1{margin:0;font-size:1.1rem}p{margin:.2rem 0 0;color:#8a5a00;font-size:.85rem}textarea{flex:1;width:calc(100% - 2rem);margin:1rem;padding:1rem;border:1px solid #9da7b1;border-radius:6px;resize:none;background:#fff;color:#202428;font:14px/1.5 ui-monospace,Consolas,monospace;tab-size:2;white-space:pre}.actions{display:flex;justify-content:flex-end;gap:.6rem;padding:.75rem 1rem;border-top:1px solid #c8ced5;background:#fff}.actions button{padding:.65rem 1rem}</style></head>
<body><form method="post" action="./vzlogger_config.cgi" accept-charset="utf-8" data-ajax="false"><header><h1>vzlogger.conf</h1><p>$note</p></header><textarea name="config" maxlength="$maximum_size" spellcheck="false" required>$escaped</textarea><div class="actions"><button type="button" onclick="window.close()">$cancel</button><button type="submit">$save</button></div></form></body></html>
HTML
