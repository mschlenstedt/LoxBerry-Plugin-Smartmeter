#!/usr/bin/perl
use strict;
use warnings;
use CGI;
use LoxBerry::System;

my $cgi = CGI->new;
my $config_file = "$lbpconfigdir/vzlogger.conf";

if (!-e $config_file) {
	print $cgi->header(
		-status => "404 Not Found",
		-type => "text/plain",
		-charset => "utf-8",
		-expires => "now",
		-X_Content_Type_Options => "nosniff",
	);
	print "The generated vzLogger configuration does not exist yet.\n";
	exit 0;
}

open(my $fh, "<", $config_file) or do {
	print $cgi->header(
		-status => "500 Internal Server Error",
		-type => "text/plain",
		-charset => "utf-8",
		-expires => "now",
		-X_Content_Type_Options => "nosniff",
	);
	print "The generated vzLogger configuration could not be read.\n";
	exit 0;
};

local $/;
my $config = <$fh>;
close($fh);

# Keep the generated formatting visible, but never return stored secrets.
$config =~ s/("(?:key)?pass(?:word)?"\s*:\s*")((?:\\.|[^"\\])*)(")/$1***REDACTED***$3/ig;
$config =~ s/("(?:token|secretKey)"\s*:\s*")((?:\\.|[^"\\])*)(")/$1***REDACTED***$3/ig;

my @lines = split(/\n/, $config, -1);
my $rendered = join("\n", map { "<li><code>" . CGI::escapeHTML($_) . "</code></li>" } @lines);
my $german = ($ENV{HTTP_ACCEPT_LANGUAGE} || "") =~ /(?:\A|,)\s*de(?:-|;|,|\z)/i;
my $html_language = $german ? "de" : "en";
my $read_only_note = $german ? "Schreibgeschützt · Zugangsdaten sind maskiert" : "Read-only · credentials are masked";

print $cgi->header(
	-type => "text/html",
	-charset => "utf-8",
	-expires => "now",
	-X_Content_Type_Options => "nosniff",
);
print <<"HTML";
<!doctype html>
<html lang="$html_language">
<head>
	<meta charset="utf-8">
	<meta name="viewport" content="width=device-width, initial-scale=1">
	<title>vzlogger.conf</title>
	<style>
		:root { color-scheme: light dark; }
		body { margin: 0; background: #f3f5f7; color: #202428; font: 15px/1.5 system-ui, sans-serif; }
		header { position: sticky; top: 0; z-index: 1; padding: .8rem 1.2rem; border-bottom: 1px solid #c8ced5; background: rgba(255,255,255,.96); box-shadow: 0 2px 8px rgba(0,0,0,.08); }
		h1 { margin: 0; font-size: 1.1rem; }
		p { margin: .2rem 0 0; color: #59636e; font-size: .85rem; }
		main { padding: 1rem; overflow: auto; }
		ol { min-width: max-content; margin: 0; padding: 1rem 1rem 1rem 4.5rem; border: 1px solid #c8ced5; border-radius: 7px; background: #fff; box-shadow: 0 3px 14px rgba(0,0,0,.06); color: #7a8490; }
		li { min-height: 1.5em; padding-left: .8rem; border-left: 1px solid #e1e5e9; }
		code { color: #202428; font: 14px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre; }
		\@media (prefers-color-scheme: dark) {
			body { background: #171a1d; color: #e8ebee; }
			header { border-color: #444b52; background: rgba(31,35,39,.96); }
			p { color: #adb5bd; }
			ol { border-color: #444b52; background: #202428; color: #929ba4; }
			li { border-color: #3a4148; }
			code { color: #e8ebee; }
		}
	</style>
</head>
<body>
	<header><h1>vzlogger.conf</h1><p>$read_only_note</p></header>
	<main><ol>$rendered</ol></main>
</body>
</html>
HTML
