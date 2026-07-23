#!/usr/bin/perl

use strict;
use warnings;
use File::Path qw(make_path);
use File::Temp qw(tempdir);
use FindBin;
use Test::More;
use lib "$FindBin::Bin/../bin";
use SmartMeterLegacyRuntime qw(
	initialize_legacy_heads acquire_legacy_fetch_lock remove_legacy_cronjobs
	apply_legacy_runtime clear_legacy_cache vzlogger_service_running
	synchronize_legacy_runtime
);

{
	package TestLegacyConfig;
	sub new { my $class = shift; return bless { @_ }, $class; }
	sub param {
		my ($self, $key, $value) = @_;
		$self->{$key} = $value if (@_ == 3);
		return $self->{$key};
	}
}

my $cfg = TestLegacyConfig->new(
	"reader.METER" => "genericsml", "reader.PROTOCOL" => "sml",
	"reader.BAUDRATE" => "9600", "MAIN.READ" => "1", "MAIN.CRON" => "5",
);
ok(initialize_legacy_heads($cfg, "/dev/serial/smartmeter/reader"), "new Legacy head is initialized");
is($cfg->param("reader.DEVICE"), "/dev/serial/smartmeter/reader", "shared device identity is initialized");
is($cfg->param("reader.LEGACY_METER"), "genericsml", "old meter value is migrated to Legacy namespace");
is($cfg->param("reader.LEGACY_BAUDRATE"), "9600", "old serial value is migrated to Legacy namespace");
is($cfg->param("reader.METER"), "genericsml", "vzLogger meter value is not overwritten");
ok(!initialize_legacy_heads($cfg, "/dev/serial/smartmeter/reader"), "completed migration is idempotent");

my $runtime = tempdir(CLEANUP => 1);
my ($first_lock, $first_error) = acquire_legacy_fetch_lock($runtime);
ok($first_lock, "first Legacy polling lock succeeds");
my ($second_lock, $second_error) = acquire_legacy_fetch_lock($runtime);
ok(!$second_lock, "second Legacy polling lock is rejected");
like($second_error, qr/currently active/, "Legacy polling lock failure is actionable");
undef $first_lock;
ok(vzlogger_service_running(sub { 1 }), "active vzLogger service is detected");
ok(!vzlogger_service_running(sub { 0 }), "stopped vzLogger service is detected");

foreach my $name (qw(reader.data reader.dump reader.log fetch.log fetch_manually.log vzlogger_config.lock vzlogger_obis_watchdog.pid vzlogger_obis_status.json)) {
	open(my $fh, ">", "$runtime/$name") or die $!;
	print $fh "test\n";
	close($fh);
}
my ($removed, $cache_error) = clear_legacy_cache($runtime);
is($cache_error, "", "Legacy cache cleanup succeeds");
is($removed, 5, "only Legacy data and logs are removed");
ok(-e "$runtime/vzlogger_config.lock", "configuration lock survives cache cleanup");
ok(-e "$runtime/vzlogger_obis_watchdog.pid", "watchdog PID survives cache cleanup");
ok(-e "$runtime/vzlogger_obis_status.json", "OBIS status survives cache cleanup");

my $home = tempdir(CLEANUP => 1);
foreach my $folder (qw(cron.01min cron.03min cron.05min cron.10min cron.15min cron.30min cron.hourly cron.reboot)) {
	make_path("$home/system/cron/$folder");
}
make_path("$home/bin/plugins/plugin");
open(my $fetch_fh, ">", "$home/bin/plugins/plugin/fetch.pl") or die $!;
close($fetch_fh);
my ($message, $ok) = apply_legacy_runtime($home, "plugin", $cfg);
ok($ok, "Legacy runtime applies a valid polling interval");
like($message, qr/5 minutes/, "Legacy runtime reports the restored interval");
ok(-l "$home/system/cron/cron.05min/plugin", "Legacy runtime creates the expected cron link");
remove_legacy_cronjobs($home, "plugin");
ok(!-e "$home/system/cron/cron.05min/plugin", "Legacy cron removal removes the link");

$cfg->param("MAIN.CRON", "2");
($message, $ok) = apply_legacy_runtime($home, "plugin", $cfg);
ok(!$ok, "invalid Legacy interval is rejected");
like($message, qr/Unknown cron interval/, "invalid Legacy interval is explained");

$cfg->param("MAIN.CRON", "5");
$cfg->param("MAIN.IMPLEMENTATION", "legacy");
make_path("$home/bin/plugins/folder");
open(my $folder_fetch_fh, ">", "$home/bin/plugins/folder/fetch.pl") or die $!;
close($folder_fetch_fh);
($message, $ok) = synchronize_legacy_runtime($home, "cron-name", $cfg, plugin_folder => "folder");
ok($ok, "lifecycle synchronization applies active Legacy runtime");
my $lifecycle_target = readlink("$home/system/cron/cron.05min/cron-name");
$lifecycle_target =~ tr{\\}{/};
my $expected_lifecycle_target = "$home/bin/plugins/folder/fetch.pl";
$expected_lifecycle_target =~ tr{\\}{/};
is($lifecycle_target, $expected_lifecycle_target, "cron name and installed plugin folder remain distinct");
$cfg->param("MAIN.IMPLEMENTATION", "none");
($message, $ok) = synchronize_legacy_runtime($home, "cron-name", $cfg, plugin_folder => "folder");
ok($ok, "lifecycle synchronization accepts inactive mode");
ok(!-e "$home/system/cron/cron.05min/cron-name", "inactive mode removes lifecycle cronjob");

open(my $upgrade_fh, "<", "$FindBin::Bin/../postupgrade.sh") or die $!;
local $/;
my $upgrade_source = <$upgrade_fh>;
close($upgrade_fh);
like($upgrade_source, qr/smartmeter_legacy_runtime\.pl" synchronize/, "upgrade lifecycle uses the shared Legacy runtime entry point");
unlike($upgrade_source, qr/case "\$cron_interval"/, "upgrade lifecycle contains no duplicate cron interval matrix");

done_testing();
