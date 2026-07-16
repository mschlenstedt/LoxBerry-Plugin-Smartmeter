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
$config =~ s/("(?:key)?pass"\s*:\s*")((?:\\.|[^"\\])*)(")/$1***REDACTED***$3/ig;

print $cgi->header(
	-type => "text/plain",
	-charset => "utf-8",
	-expires => "now",
	-X_Content_Type_Options => "nosniff",
);
print $config;
