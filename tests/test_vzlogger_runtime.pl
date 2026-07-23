#!/usr/bin/perl

use strict;
use warnings;
use File::Temp qw(tempdir);
use FindBin;
use Test::More;
use lib "$FindBin::Bin/../bin";
use SmartMeterVZLoggerRuntime qw(acquire_config_lock promote_files_atomic);

my $dir = tempdir(CLEANUP => 1);
my ($lock, $error) = acquire_config_lock($dir);
ok($lock, "first configuration lock succeeds") or diag($error);
my $code = 'use SmartMeterVZLoggerRuntime qw(acquire_config_lock); my ($l)=acquire_config_lock($ARGV[0]); exit($l ? 1 : 0);';
my $status = system($^X, "-I$FindBin::Bin/../bin", "-MSmartMeterVZLoggerRuntime", "-e", $code, $dir);
is($status >> 8, 0, "second process is rejected while lock is held");
undef $lock;
($lock, $error) = acquire_config_lock($dir);
ok($lock, "configuration lock is reusable after release") or diag($error);
undef $lock;

sub write_file {
	my ($file, $text) = @_;
	open(my $fh, ">", $file) or die $!;
	print $fh $text;
	close($fh);
}
sub read_file {
	my ($file) = @_;
	open(my $fh, "<", $file) or die $!;
	local $/;
	my $text = <$fh>;
	close($fh);
	return $text;
}

write_file("$dir/source-one", "new-one");
write_file("$dir/target-one", "old-one");
write_file("$dir/target-two", "old-two");
my ($ok, $promotion_error) = promote_files_atomic([
	["$dir/source-one", "$dir/target-one", 0600],
	["$dir/missing-source", "$dir/target-two", 0600],
]);
ok(!$ok, "promotion fails when a staged artifact is missing");
like($promotion_error, qr/missing/i, "promotion failure is actionable");
is(read_file("$dir/target-one"), "old-one", "earlier promoted file is rolled back");
is(read_file("$dir/target-two"), "old-two", "unreached target remains unchanged");

write_file("$dir/source-two", "new-two");
($ok, $promotion_error) = promote_files_atomic([
	["$dir/source-one", "$dir/target-one", 0600],
	["$dir/source-two", "$dir/target-two", 0600],
]);
ok($ok, "complete staged set is promoted") or diag($promotion_error);
is(read_file("$dir/target-one"), "new-one", "first artifact promoted");
is(read_file("$dir/target-two"), "new-two", "second artifact promoted");

SKIP: {
	skip "POSIX ownership test is not available on Windows", 3 if ($^O eq "MSWin32");
	my @source_stat = stat("$dir/source-one");
	($ok, $promotion_error) = promote_files_atomic([
		["$dir/source-one", "$dir/owned-target", 0640, $source_stat[4], $source_stat[5]],
	]);
	ok($ok, "promotion accepts explicit target ownership") or diag($promotion_error);
	my @target_stat = stat("$dir/owned-target");
	is($target_stat[4], $source_stat[4], "promoted target has requested user ownership");
	is($target_stat[5], $source_stat[5], "promoted target has requested group ownership");
}

done_testing();
