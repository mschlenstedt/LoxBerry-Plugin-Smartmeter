#!/usr/bin/perl

use strict;
use warnings;
use File::Temp qw(tempdir);
use FindBin;
use JSON::PP;
use Test::More;
use lib "$FindBin::Bin/../bin";
use SmartMeterConfig;

my $dir = tempdir(CLEANUP => 1);

sub slurp_json
{
	my ($file) = @_;
	open(my $fh, "<", $file) or die "cannot read $file: $!";
	local $/;
	my $content = <$fh>;
	close($fh);
	return JSON::PP->new->utf8->decode($content);
}

# A missing file is an error, matching the previous Config::Simple behaviour
# that the "or die" call sites rely on.
is(SmartMeterConfig->new("$dir/does-not-exist.json"), undef, "missing configuration reports an error");
ok(SmartMeterConfig->error(), "an error message is available");

my $file = "$dir/smartmeter.json";
my $cfg = SmartMeterConfig->create($file);
ok($cfg, "create() starts a new configuration");

# Global sections and meter sections use the same flat accessor.
$cfg->param("MAIN.IMPLEMENTATION", "vzlogger");
$cfg->param("MAIN.READ", "1");
$cfg->param("VZLOGGER.LOCALPORT", "18080");
$cfg->param("reader1.SERIAL", "reader1");
$cfg->param("reader1.METER", "sml");
$cfg->save;

is($cfg->param("MAIN.IMPLEMENTATION"), "vzlogger", "global value round-trips");
is($cfg->param("reader1.METER"), "sml", "meter value round-trips");
is($cfg->param("MAIN.MISSING"), undef, "unknown key is undef");
is($cfg->param("nosuchreader.METER"), undef, "unknown meter is undef");

my $stored = slurp_json($file);
is($stored->{MAIN}->{IMPLEMENTATION}, "vzlogger", "global sections stay top level");
is($stored->{METERS}->{reader1}->{METER}, "sml", "meters are nested below METERS");
ok(!exists($stored->{reader1}), "meters do not leak into the top level");

# Reopening reads the same values back.
my $reopened = SmartMeterConfig->new($file);
ok($reopened, "existing configuration opens");
is($reopened->param("VZLOGGER.LOCALPORT"), "18080", "value survives a reopen");
is_deeply([sort $reopened->param()],
	[sort qw(MAIN.IMPLEMENTATION MAIN.READ VZLOGGER.LOCALPORT reader1.SERIAL reader1.METER)],
	"param() lists global and meter keys as SECTION.KEY");

# delete() removes the key and drops the meter once it is empty.
$reopened->delete("reader1.METER");
is($reopened->param("reader1.METER"), undef, "deleted key is gone");
is($reopened->param("reader1.SERIAL"), "reader1", "sibling key is retained");
$reopened->delete("reader1.SERIAL");
$reopened->save;
ok(!exists(slurp_json($file)->{METERS}->{reader1}), "empty meter section is removed");

# import_from fills the flat hash the generator uses to find readers.
my $flat_file = "$dir/flat.json";
my $flat_cfg = SmartMeterConfig->create($flat_file);
$flat_cfg->param("MAIN.READ", "1");
$flat_cfg->param("readerA.SERIAL", "readerA");
$flat_cfg->save;
my %flat;
ok(SmartMeterConfig->import_from($flat_file, \%flat), "import_from succeeds");
is($flat{"MAIN.READ"}, "1", "flat hash contains global keys");
is($flat{"readerA.SERIAL"}, "readerA", "flat hash contains meter keys as <serial>.KEY");

# The INI migration converts the old layout, including meter sections.
my $migrate_dir = tempdir(CLEANUP => 1);
open(my $ini, ">", "$migrate_dir/smartmeter.cfg") or die $!;
print $ini <<'INI';
[MAIN]
IMPLEMENTATION=legacy
READ=1
CRON=5
SENDMQTT=0
[VZLOGGER]
LOCALPORT=18080
DEBUG=1
[1ISK0001]
SERIAL=1ISK0001
METER=sml
LEGACY_METER=sml
INI
close($ini);

my $migrate = "$FindBin::Bin/../bin/migrate_config.pl";
my $path_separator = $^O eq "MSWin32" ? ";" : ":";
local $ENV{PERL5LIB} = "$FindBin::Bin/../.github/ci/perl-lib" . ($ENV{PERL5LIB} ? "$path_separator$ENV{PERL5LIB}" : "");
my $rc = system($^X, $migrate, $migrate_dir);
is($rc, 0, "migration runs successfully");

my $migrated = SmartMeterConfig->new("$migrate_dir/smartmeter.json");
ok($migrated, "migration produced a JSON configuration");
is($migrated->param("MAIN.IMPLEMENTATION"), "none", "a stored Legacy mode becomes inactive");
is($migrated->param("MAIN.CRON"), undef, "obsolete CRON is dropped");
is($migrated->param("MAIN.SENDMQTT"), undef, "obsolete SENDMQTT is dropped");
is($migrated->param("VZLOGGER.DEBUG"), undef, "obsolete bridge debug switch is dropped");
is($migrated->param("1ISK0001.METER"), "sml", "meter settings survive the migration");
is($migrated->param("1ISK0001.LEGACY_METER"), undef, "Legacy meter settings are dropped");
is($migrated->param("VZLOGGER.LOCALPORT"), "18080", "existing vzLogger settings are kept");
ok(-e "$migrate_dir/smartmeter.cfg.pre-json", "the original INI file is kept as a fallback");

# Running the migration again must not change anything.
is(system($^X, $migrate, $migrate_dir), 0, "migration is repeatable");
is(SmartMeterConfig->new("$migrate_dir/smartmeter.json")->param("MAIN.IMPLEMENTATION"), "none",
	"a second migration run keeps the result stable");

done_testing();
