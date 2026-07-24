#!/usr/bin/perl

# Starts, stops and supervises the vzlogger process.
#
# vzlogger runs in the foreground (-f) as a child of this script instead of as a
# systemd service, so the plugin owns its lifecycle. The packaged systemd unit
# is disabled by bin/vzlogger_pkg.sh.
#
# Usage: watchdog.pl --action=start|stop|restart|check|status [--verbose]
#
#   start    start vzlogger unless it is already running
#   stop     stop vzlogger and remember that this was intentional
#   restart  stop, then start
#   check    restart vzlogger if it died unexpectedly (called from cron)
#   status   exit 0 if vzlogger is running, 1 otherwise
#
# A manual stop writes a marker file so the periodic check does not start the
# process again behind the user's back.

use strict;
use warnings;
use Getopt::Long;
use File::Path qw(make_path);
use POSIX qw(setsid);
use FindBin;
use lib $FindBin::Bin;
use LoxBerry::System;
use LoxBerry::Log;
use SmartMeterConfig;

my $psubfolder = $lbpplugindir;
my $config_dir = "$lbhomedir/config/plugins/$psubfolder";
my $plugin_config_file = "$config_dir/smartmeter.json";
my $vzlogger_config = "$config_dir/vzlogger.conf";
my $runtime_dir = "/var/run/shm/$psubfolder";
my $pid_file = "$runtime_dir/vzlogger.pid";
my $stopped_marker = "$config_dir/vzlogger_stopped.cfg";
my $failure_file = "$runtime_dir/vzlogger_watchdog_failures";
my $max_failures = 5;

my ($verbose, $action);
GetOptions("verbose=s" => \$verbose, "action=s" => \$action);
$action = "" if (!defined($action));

my $log = LoxBerry::Log->new(name => "watchdog", package => $psubfolder);
if ($verbose) {
	$log->stdout(1);
	$log->loglevel(7);
}
LOGSTART("watchdog action=$action");

make_path($runtime_dir) if (!-d $runtime_dir);

# Serialize against a parallel run, for example cron firing while the web
# interface triggers a restart.
my $lockstate = LoxBerry::System::lock(lockfile => "smartmeter-watchdog", wait => 120);
if ($lockstate) {
	LOGWARN("Another watchdog run is active: $lockstate");
	print "$lockstate currently running - Quitting.\n";
	LOGEND();
	exit 1;
}

my $exit = 0;
if ($action eq "start") { $exit = do_start(); }
elsif ($action eq "stop") { $exit = do_stop(1); }
elsif ($action eq "restart") { $exit = do_restart(); }
elsif ($action eq "check") { $exit = do_check(); }
elsif ($action eq "status") { $exit = vzlogger_running() ? 0 : 1; }
else {
	LOGERR("No valid action. --action=start|stop|restart|check|status is required.");
	print "No valid action specified. --action=start|stop|restart|check|status is required.\n";
	$exit = 2;
}

LoxBerry::System::unlock(lockfile => "smartmeter-watchdog");
LOGEND();
exit $exit;

sub do_start
{
	unlink($stopped_marker) if (-e $stopped_marker);

	if (vzlogger_running()) {
		LOGOK("vzlogger is already running.");
		print "vzlogger is already running.\n";
		return 0;
	}
	if (!vzlogger_mode_enabled()) {
		LOGINF("vzLogger mode is not active. Not starting vzlogger.");
		print "vzLogger mode is not active. Did not start vzlogger.\n";
		return 0;
	}
	my $binary = vzlogger_binary();
	if (!$binary) {
		LOGERR("vzlogger binary not found. Install it from the plugin page.");
		print "vzlogger binary not found.\n";
		return 1;
	}
	if (!-e $vzlogger_config) {
		LOGERR("Generated configuration is missing: $vzlogger_config");
		print "Generated vzLogger configuration is missing. Use Save and apply first.\n";
		return 1;
	}

	my $logfile = vzlogger_logfile();
	LOGINF("Starting $binary with $vzlogger_config");
	my $pid = fork();
	if (!defined($pid)) {
		LOGERR("Could not fork: $!");
		return 1;
	}
	if ($pid == 0) {
		# Detach so vzlogger survives the watchdog and its caller.
		setsid();
		open(STDIN, "<", "/dev/null");
		open(STDOUT, ">>", $logfile) or open(STDOUT, ">", "/dev/null");
		open(STDERR, ">&", \*STDOUT);
		exec($binary, "-f", "-c", $vzlogger_config, "-o", $logfile);
		exit 1;
	}

	write_pid($pid);
	# Give it a moment so an immediate failure is reported instead of a
	# success that is already gone.
	sleep 2;
	if (!vzlogger_running()) {
		LOGERR("vzlogger exited right after the start. See $logfile.");
		print "vzlogger did not stay running. Check the vzLogger log.\n";
		return 1;
	}
	reset_failures();
	LOGOK("vzlogger started (PID $pid).");
	print "Started vzlogger (PID $pid).\n";
	return 0;
}

sub do_stop
{
	my ($manual) = @_;
	if ($manual) {
		my $fh;
		if (open($fh, ">", $stopped_marker)) {
			print $fh "1\n";
			close($fh);
		}
	}
	my $pid = read_pid();
	if (!$pid || !process_is_vzlogger($pid)) {
		$pid = find_vzlogger_pid();
	}
	if (!$pid) {
		LOGOK("vzlogger is not running.");
		print "vzlogger is not running.\n";
		unlink($pid_file);
		return 0;
	}

	LOGINF("Stopping vzlogger (PID $pid).");
	kill("TERM", $pid);
	for (1 .. 20) {
		last if (!process_is_vzlogger($pid));
		select(undef, undef, undef, 0.25);
	}
	if (process_is_vzlogger($pid)) {
		LOGWARN("vzlogger did not stop on TERM, sending KILL.");
		kill("KILL", $pid);
		select(undef, undef, undef, 0.5);
	}
	unlink($pid_file);
	if (process_is_vzlogger($pid)) {
		LOGERR("Could not stop vzlogger (PID $pid).");
		print "Could not stop vzlogger.\n";
		return 1;
	}
	LOGOK("vzlogger stopped.");
	print "Stopped vzlogger.\n";
	return 0;
}

sub do_restart
{
	my $rc = do_stop(0);
	return $rc if ($rc != 0);
	sleep 1;
	return do_start();
}

# Called periodically. Restarts vzlogger only if it should be running and was
# not stopped on purpose, and gives up after repeated failures so a broken
# configuration is not restarted forever.
sub do_check
{
	if (-e $stopped_marker) {
		LOGOK("vzlogger was stopped manually. Nothing to do.");
		return 0;
	}
	if (!vzlogger_mode_enabled()) {
		LOGOK("vzLogger mode is not active. Nothing to do.");
		return 0;
	}
	if (vzlogger_running()) {
		reset_failures();
		LOGOK("vzlogger is running.");
		return 0;
	}

	my $failures = read_failures() + 1;
	write_failures($failures);
	if ($failures > $max_failures) {
		LOGERR("vzlogger failed $failures times in a row. Not restarting again until it is started manually.");
		return 1;
	}
	LOGWARN("vzlogger is not running (failure $failures of $max_failures). Restarting.");
	return do_start();
}

sub vzlogger_mode_enabled
{
	my $cfg = SmartMeterConfig->new($plugin_config_file);
	return 0 if (!$cfg);
	return (($cfg->param("MAIN.IMPLEMENTATION") || "") eq "vzlogger") ? 1 : 0;
}

sub vzlogger_binary
{
	foreach my $candidate ("/usr/bin/vzlogger", "/usr/local/bin/vzlogger") {
		return $candidate if (-x $candidate);
	}
	foreach my $dir (split(/:/, $ENV{PATH} || "")) {
		return "$dir/vzlogger" if (-x "$dir/vzlogger");
	}
	return undef;
}

sub vzlogger_logfile
{
	my $dir = "$lbhomedir/log/plugins/$psubfolder";
	make_path($dir) if (!-d $dir);
	# A LoxBerry log session gives the file a timestamped name and registers it
	# in the log manager; vzlogger writes into it directly through -o.
	my $vzlog = LoxBerry::Log->new(name => "vzlogger", package => $psubfolder);
	$vzlog->LOGSTART("vzlogger process log");
	return $vzlog->filename();
}

sub vzlogger_running
{
	my $pid = read_pid();
	return 1 if ($pid && process_is_vzlogger($pid));
	my $found = find_vzlogger_pid();
	write_pid($found) if ($found);
	return $found ? 1 : 0;
}

sub process_is_vzlogger
{
	my ($pid) = @_;
	return 0 if (!$pid || $pid !~ /\A\d+\z/ || !-d "/proc/$pid");
	open(my $fh, "<", "/proc/$pid/cmdline") or return 0;
	local $/;
	my $cmdline = <$fh> || "";
	close($fh);
	my @args = grep { defined($_) && $_ ne "" } split(/\0/, $cmdline);
	return 0 if (!@args);
	return 0 if ($args[0] !~ m{(?:\A|/)vzlogger\z});
	# Only our own instance, identified by the generated configuration.
	return (grep { $_ eq $vzlogger_config } @args) ? 1 : 0;
}

sub find_vzlogger_pid
{
	opendir(my $proc, "/proc") or return undef;
	my @pids = sort { $a <=> $b } grep { /\A\d+\z/ } readdir($proc);
	closedir($proc);
	foreach my $pid (@pids) {
		return $pid if (process_is_vzlogger($pid));
	}
	return undef;
}

sub read_pid
{
	return undef if (!-e $pid_file);
	open(my $fh, "<", $pid_file) or return undef;
	my $pid = <$fh>;
	close($fh);
	chomp($pid) if (defined($pid));
	return (defined($pid) && $pid =~ /\A\d+\z/) ? $pid : undef;
}

sub write_pid
{
	my ($pid) = @_;
	open(my $fh, ">", $pid_file) or return;
	print $fh "$pid\n";
	close($fh);
}

sub read_failures
{
	return 0 if (!-e $failure_file);
	open(my $fh, "<", $failure_file) or return 0;
	my $count = <$fh>;
	close($fh);
	chomp($count) if (defined($count));
	return (defined($count) && $count =~ /\A\d+\z/) ? $count : 0;
}

sub write_failures
{
	my ($count) = @_;
	open(my $fh, ">", $failure_file) or return;
	print $fh "$count\n";
	close($fh);
}

sub reset_failures { unlink($failure_file) if (-e $failure_file); }
