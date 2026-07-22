#!/usr/bin/perl

use strict;
use warnings;
use Config::Simple;
use FindBin;
use lib $FindBin::Bin;
use SmartMeterLegacyRuntime qw(synchronize_legacy_runtime);

my ($action, $home, $plugin_name, $plugin_folder, $config_file) = @ARGV;
if (($action || "") ne "synchronize" || !$home || !$plugin_name || !$plugin_folder || !$config_file) {
	die "Usage: $0 synchronize HOME PLUGIN_NAME PLUGIN_FOLDER CONFIG_FILE\n";
}

my $plugin_cfg = Config::Simple->new($config_file) or die "Could not read $config_file\n";
my ($message, $ok) = synchronize_legacy_runtime(
	$home,
	$plugin_name,
	$plugin_cfg,
	plugin_folder => $plugin_folder,
);
print $message;
exit($ok ? 0 : 1);
