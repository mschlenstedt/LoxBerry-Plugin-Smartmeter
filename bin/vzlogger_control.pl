#!/usr/bin/perl

use strict;
use warnings;
umask(0027);

use File::Copy qw(copy);
use File::Path qw(make_path);
use File::Temp qw(tempdir);
use JSON::PP;
use LoxBerry::System;
use LoxBerry::Log;
use FindBin;
use lib $FindBin::Bin;
use SmartMeterConfig;
use SmartMeterVZLoggerExpert qw(read_text write_text_atomic update_expert_log_settings format_expert_validation);
use SmartMeterVZLoggerRuntime qw(acquire_config_lock promote_files_atomic);
use SmartMeterVZLoggerConfig qw(clean_number clean_qos sanitize_topic implementation_mode);

my $home = $lbhomedir;
my $psubfolder = $lbpplugindir;
my $bindir = "$home/bin/plugins/$psubfolder";
my $plugin_config_file = "$home/config/plugins/$psubfolder/smartmeter.json";
my $config_file = "$home/config/plugins/$psubfolder/vzlogger.conf";
my $expert_file = "$home/config/plugins/$psubfolder/vzlogger_expert.conf";
my $mapping_file = "$home/config/plugins/$psubfolder/vzlogger_channels.json";
my $runtime_dir = "/var/run/shm/$psubfolder";
my $obis_watchdog_pid_file = "$runtime_dir/vzlogger_obis_watchdog.pid";
my $obis_status_file = "$runtime_dir/vzlogger_obis_status.json";
my $plugin_log_dir = "$home/log/plugins/$psubfolder";
my $vzlogger_log_file = "$plugin_log_dir/vzlogger.log";
my $bridge_service = "smartmeter-ng-vzlogger-bridge";
my $vzlogger_override_file = "/etc/systemd/system/vzlogger.service.d/smartmeter-ng.conf";
my $action = shift @ARGV || "status";

make_path($runtime_dir) if (!-d $runtime_dir);
make_path($plugin_log_dir) if (!-d $plugin_log_dir);
chmod(0750, $runtime_dir);

# Each control invocation opens a fresh LoxBerry log session (timestamped file,
# rotated by log_maint.pl). The log level comes from PLUGINDB_LOGLEVEL, i.e. the
# plugin management widget. LOG* functions act on this session.
my $log = LoxBerry::Log->new(
	name    => "control",
	package => $psubfolder,
);
LOGSTART("control action=$action");

my %mutating_action = map { $_ => 1 } qw(
	generate apply apply-expert activate-vzlogger restart-vzlogger start-vzlogger stop-vzlogger
	restart-bridge start-bridge stop-bridge disable-vzlogger
);
my $config_lock;
if ($mutating_action{$action}) {
	my ($lock, $error) = acquire_config_lock($runtime_dir);
	if (!$lock) {
		print "$error\n";
		exit 2;
	}
	$config_lock = $lock;
}
log_control("action=$action user=" . ($ENV{USER} || $ENV{LOGNAME} || "unknown"));

if ($action eq "generate") {
	exit generate_and_validate();
}

if ($action eq "apply") {
	exit apply_generated_configuration();
	}

if ($action eq "activate-vzlogger") {
	exit activate_or_migrate_vzlogger();
}

if ($action eq "restart-vzlogger") {
	my $rc = update_vzlogger_log_config();
	exit $rc if ($rc != 0);
	if (!vzlogger_mode_enabled()) {
		print "vzLogger mode is disabled. Did not restart vzLogger.\n";
		exit 0;
	}
	exit restart_vzlogger();
}

if ($action eq "start-vzlogger") {
	my $rc = update_vzlogger_log_config();
	exit $rc if ($rc != 0);
	if (!vzlogger_mode_enabled()) {
		print "vzLogger mode is disabled. Did not start vzLogger.\n";
		exit 0;
	}
	exit start_vzlogger();
}

if ($action eq "stop-vzlogger") {
	my $rc = update_vzlogger_log_config();
	print "Warning: vzLogger log settings could not be written to the current configuration.\n" if ($rc != 0);
	exit stop_vzlogger();
}

if ($action eq "restart-bridge") {
	if (!bridge_enabled()) {
		print "MQTT bridge is disabled. Did not restart the MQTT bridge.\n";
		exit 0;
	}
	my $rc = run_perl("$bindir/vzlogger_validate.pl");
	exit $rc if ($rc != 0);
	if (!generated_mqtt_enabled()) {
		print "MQTT is disabled in the generated vzLogger configuration. Use Save and apply first.\n";
		exit 1;
	}
	exit restart_bridge();
}

if ($action eq "validate") {
	exit run_perl("$bindir/vzlogger_validate.pl");
}

if ($action eq "apply-expert") {
	my $rc = run_perl("$bindir/vzlogger_validate.pl");
	exit $rc if ($rc != 0);
	exit activate_current_vzlogger_configuration();
}

if ($action eq "start-bridge") {
	if (!bridge_enabled()) {
		print "MQTT bridge is disabled. Did not start the MQTT bridge.\n";
		exit 0;
	}
	my $rc = run_perl("$bindir/vzlogger_validate.pl");
	exit $rc if ($rc != 0);
	if (!generated_mqtt_enabled()) {
		print "MQTT is disabled in the generated vzLogger configuration. Use Save and apply first.\n";
		exit 1;
	}
	exit start_bridge();
}

if ($action eq "stop-bridge") {
	exit stop_bridge();
}

if ($action eq "disable-vzlogger") {
	my $rc = stop_bridge();
	my $vzlogger_rc = stop_vzlogger(1);
	$rc = $vzlogger_rc if ($rc == 0 && $vzlogger_rc != 0);
	my $override_rc = install_vzlogger_service_override("remove");
	$rc = $override_rc if ($rc == 0 && $override_rc != 0);
	print "Stopped vzLogger and bridge.\n";
	exit $rc;
}

if ($action eq "status") {
	print "implementation: " . implementation_mode(SmartMeterConfig->new($plugin_config_file)) . "\n";
	print "vzlogger binary: " . (command_exists("vzlogger") ? "available" : "missing") . "\n";
	print "vzlogger package: " . package_state("vzlogger") . "\n";
	print "Volkszaehler apt source: " . (-e "/etc/apt/sources.list.d/volkszaehler-volkszaehler-org-project.list" ? "configured" : "missing") . "\n";
	print "vzlogger config: " . (-e $config_file ? $config_file : "missing") . "\n";
	print "vzlogger service config: " . (-e $vzlogger_override_file ? $config_file : "system default") . "\n";
	print "config validation: " . validation_state() . "\n";
	print "vzlogger service: " . service_summary("vzlogger") . "\n";
	print "MQTT bridge service: " . service_summary($bridge_service) . "\n";
	print "MQTT bridge process: " . (bridge_running() ? "running" : "stopped") . "\n";
	exit 0;
}

if ($action eq "debug-log") {
	exit create_debug_log();
}

print "Usage: $0 generate|validate|apply|apply-expert|activate-vzlogger|restart-vzlogger|start-vzlogger|stop-vzlogger|restart-bridge|start-bridge|stop-bridge|disable-vzlogger|status|debug-log\n";
exit 1;

sub run_perl
{
	my @args = @_;
	log_control("run: $^X " . join(" ", @args));
	system($^X, @args);
	my $exit = $? >> 8;
	log_control("exit=$exit: $^X " . join(" ", @args));
	return $exit;
}

sub generate_and_validate
{
	return generate_validate_and_promote();
}

sub apply_generated_configuration
{
	my $rc = generate_validate_and_promote();
	return $rc if ($rc != 0);
	if (vzlogger_mode_enabled() && generated_meter_count() == 0) {
		my $stop_rc = stop_bridge();
		my $vzlogger_rc = stop_vzlogger(1);
		$stop_rc = $vzlogger_rc if ($stop_rc == 0 && $vzlogger_rc != 0);
		my $override_rc = install_vzlogger_service_override("remove");
		$stop_rc = $override_rc if ($stop_rc == 0 && $override_rc != 0);
		print "No meter is configured. Stopped vzLogger and bridge.\n";
		return $stop_rc;
	}
	return activate_current_vzlogger_configuration();
}

sub generate_validate_and_promote
{
	my $config_dir = "$home/config/plugins/$psubfolder";
	my $stage = tempdir(".vzlogger-stage-XXXXXX", DIR => $config_dir, CLEANUP => 1);
	my $stage_config = "$stage/vzlogger.conf";
	my $stage_mapping = "$stage/vzlogger_channels.json";
	my $stage_definitions = "$stage/vzlogger_channel_definitions.json";
	copy("$config_dir/vzlogger_channel_definitions.json", $stage_definitions)
		if (-e "$config_dir/vzlogger_channel_definitions.json");
	foreach my $registry (glob("$config_dir/vzlogger_user_channel_uuids_*.json")) {
		my ($name) = $registry =~ m{([^/\\]+)\z};
		copy($registry, "$stage/$name") or return message_exit("Could not stage $registry: $!", 1);
	}
	my $rc;
	{
		local $ENV{SMARTMETER_VZLOGGER_CONFIG_FILE} = $stage_config;
		local $ENV{SMARTMETER_VZLOGGER_MAPPING_FILE} = $stage_mapping;
		local $ENV{SMARTMETER_VZLOGGER_DEFINITIONS_FILE} = $stage_definitions;
		local $ENV{SMARTMETER_UUID_REGISTRY_DIR} = $stage;
		$rc = run_perl("$bindir/vzlogger_config.pl");
		return $rc if ($rc != 0);
		$rc = run_perl("$bindir/vzlogger_validate.pl");
		return $rc if ($rc != 0);
	}
	my (@private_owner, @vzlogger_owner);
	my $config_mode = 0600;
	if ($> == 0) {
		my @loxberry = getpwnam("loxberry");
		my @vzlogger = getpwnam("_vzlogger");
		return message_exit("Could not resolve loxberry or _vzlogger ownership for generated configuration.", 1)
			if (!@loxberry || !@vzlogger);
		@private_owner = ($loxberry[2], $loxberry[3]);
		@vzlogger_owner = ($loxberry[2], $vzlogger[3]);
		$config_mode = 0640;
	}
	my @pairs = (
		[$stage_config, $config_file, $config_mode, @vzlogger_owner],
		[$stage_mapping, $mapping_file, 0600, @private_owner],
	);
	push @pairs, [$stage_definitions, "$config_dir/vzlogger_channel_definitions.json", 0600, @private_owner]
		if (-e $stage_definitions);
	foreach my $registry (glob("$stage/vzlogger_user_channel_uuids_*.json")) {
		my ($name) = $registry =~ m{([^/\\]+)\z};
		push @pairs, [$registry, "$config_dir/$name", 0600, @private_owner];
	}
	my ($ok, $error) = promote_files_atomic(\@pairs);
	return message_exit($error, 1) if (!$ok);
	print "Validated and promoted generated vzLogger configuration.\n";
	return 0;
}

sub activate_or_migrate_vzlogger
{
	if (current_vzlogger_configuration_is_valid()) {
		print "Existing valid vzLogger configuration found. Kept it unchanged instead of regenerating it.\n";
		return activate_current_vzlogger_configuration();
	}
	print "No valid existing vzLogger configuration found. Generating it from the current meter settings.\n";
	return apply_generated_configuration();
}

sub current_vzlogger_configuration_is_valid
{
	return 0 if (!-e $config_file || !-e $mapping_file || generated_meter_count() <= 0);
	return run_perl("$bindir/vzlogger_validate.pl") == 0 ? 1 : 0;
}

sub activate_current_vzlogger_configuration
{
	if (!vzlogger_mode_enabled()) {
		my $rc = stop_bridge();
		my $vzlogger_rc = stop_vzlogger(1);
		$rc = $vzlogger_rc if ($rc == 0 && $vzlogger_rc != 0);
		my $override_rc = install_vzlogger_service_override("remove");
		$rc = $override_rc if ($rc == 0 && $override_rc != 0);
		print "vzLogger mode is disabled. Stopped vzLogger and bridge.\n";
		return $rc;
	}
	my $rc = restart_vzlogger();
	return $rc if ($rc != 0);
	if (bridge_enabled()) {
		$rc = restart_bridge();
	} else {
		$rc = stop_bridge();
		print "MQTT bridge is disabled. Stopped bridge and left vzLogger running.\n";
	}
	return $rc;
}

sub generated_meter_count
{
	return -1 if (!-e $config_file);
	open(my $fh, "<", $config_file) or return -1;
	my $json = do { local $/; <$fh> };
	close($fh);
	my $config = eval { JSON::PP->new->utf8->decode($json || "") };
	return -1 if ($@ || ref($config) ne "HASH" || ref($config->{meters}) ne "ARRAY");
	return scalar(@{$config->{meters}});
}

sub update_vzlogger_log_config
{
	if (!-e $config_file) {
		print "Generated vzLogger configuration is missing. Use Save and apply first.\n";
		return 1;
	}

	open(my $fh, "<", $config_file) or do {
		print "Could not read $config_file: $!\n";
		return 1;
	};
	my $original;
	{
		local $/;
		$original = <$fh>;
	}
	close($fh);

	my $decoded = eval { JSON::PP->new->utf8->decode($original) };
	if ($@ || ref($decoded) ne "HASH") {
		print "Current vzLogger configuration is invalid. Use Save and apply first.\n";
		return 1;
	}

	my $cfg = SmartMeterConfig->new($plugin_config_file);
	if (!$cfg) {
		my $error = SmartMeterConfig->error() || "unknown Config::Simple error";
		print "Could not read $plugin_config_file: $error\n";
		return 1;
	}
	my $debug_enabled = ($cfg->param("VZLOGGER.VZLOGGERDEBUG") || "0") eq "1";
	my $configured_level = $cfg->param("VZLOGGER.LOGLEVEL");
	my $log_level = (defined($configured_level) && $configured_level =~ /\A(?:0|1|3|5|10|15)\z/) ? $configured_level : 0;
	my $verbosity = $debug_enabled ? $log_level : 0;
	my $log_file = $debug_enabled ? $vzlogger_log_file : "/dev/null";
	if (($cfg->param("VZLOGGER.EXPERTMODE") || "0") eq "1") {
		my $expert = read_text($expert_file);
		if (!defined($expert)) {
			print "Expert vzLogger configuration is missing.\n";
			return 1;
		}
		my ($updated_expert, $result) = update_expert_log_settings($expert, $verbosity, $log_file);
		if (!defined($updated_expert)) {
			print format_expert_validation($result);
			print "Could not update log settings while the expert configuration is invalid.\n";
			return 1;
		}
		if (!write_text_atomic($expert_file, $updated_expert) || !write_text_atomic($config_file, $updated_expert)) {
			print "Could not update the expert vzLogger configuration.\n";
			return 1;
		}
		my $validate_rc = run_perl("$bindir/vzlogger_validate.pl");
		return $validate_rc if ($validate_rc != 0);
		print "Validated the expert vzLogger configuration and updated only its root log settings.\n";
		return 0;
	}
	my $log_json = JSON::PP->new->utf8->allow_nonref->encode($log_file);

	my $updated = $original;
	my $verbosity_updates = ($updated =~ s/^(  "verbosity"\s*:\s*)-?\d+(\s*,\s*)$/$1$verbosity$2/mg);
	my $log_updates = ($updated =~ s/^(  "log"\s*:\s*)"(?:\\.|[^"\\])*"(\s*,\s*)$/$1$log_json$2/mg);
	if ($verbosity_updates != 1 || $log_updates != 1) {
		print "Could not locate the generated root log settings in $config_file. Use Save and apply first.\n";
		return 1;
	}

	if ($updated ne $original && !write_vzlogger_config_atomic($updated)) {
		print "Could not update $config_file.\n";
		return 1;
	}

	my $validate_rc = run_perl("$bindir/vzlogger_validate.pl");
	if ($validate_rc != 0) {
		write_vzlogger_config_atomic($original) if ($updated ne $original);
		print "Restored the previous vzLogger configuration. Use Save and apply before starting the service.\n";
		return $validate_rc;
	}

	print "Validated the current vzLogger configuration and updated only its log settings.\n";
	return 0;
}

sub write_vzlogger_config_atomic
{
	my ($content) = @_;
	my $tmp = "$config_file.tmp.$$";
	my $mode = (stat($config_file))[2];
	$mode = defined($mode) ? ($mode & 07777) : 0644;
	open(my $fh, ">", $tmp) or return 0;
	if (!print $fh $content) {
		close($fh);
		unlink($tmp);
		return 0;
	}
	if (!close($fh)) {
		unlink($tmp);
		return 0;
	}
	chmod($mode, $tmp);
	if (!rename($tmp, $config_file)) {
		unlink($tmp);
		return 0;
	}
	return 1;
}

sub start_bridge
{
	my $install_rc = install_bridge_service("install");
	return $install_rc if ($install_rc != 0);

	if (service_installed($bridge_service)) {
		my $rc = run_privileged("start $bridge_service", systemctl_command(), "start", $bridge_service);
		print "Started $bridge_service service.\n" if ($rc == 0);
		$rc = 1 if ($rc == 0 && !wait_for_service_state($bridge_service, 1));
		return $rc;
	}

	return 0 if (bridge_running());

	my $pid = fork();
	die "Could not fork bridge process: $!\n" if (!defined($pid));
	if ($pid == 0) {
		# The bridge writes its own LoxBerry log session, so its standard streams
		# are discarded in this fork fallback (the systemd unit is the normal path).
		open STDIN, "</dev/null";
		open STDOUT, ">/dev/null";
		open STDERR, ">/dev/null";
		exec($^X, "$bindir/vzlogger_mqtt_bridge.pl");
		exit 1;
	}
	print "Started bridge process $pid.\n";
	return 0;
}

sub restart_bridge
{
	my $install_rc = install_bridge_service("install");
	return $install_rc if ($install_rc != 0);

	if (service_installed($bridge_service)) {
		my $rc = run_privileged("restart $bridge_service", systemctl_command(), "restart", $bridge_service);
		print "Restarted $bridge_service service.\n" if ($rc == 0);
		$rc = 1 if ($rc == 0 && !wait_for_service_state($bridge_service, 1));
		return $rc;
	}

	my $rc = stop_bridge();
	return $rc if ($rc != 0);
	return start_bridge();
}

sub stop_bridge
{
	if (service_installed($bridge_service)) {
		my $rc = run_privileged("stop $bridge_service", systemctl_command(), "stop", $bridge_service);
		run_privileged("reset failed state for $bridge_service", systemctl_command(), "reset-failed", $bridge_service) if ($rc == 0);
		print "Stopped $bridge_service service.\n" if ($rc == 0);
		$rc = 1 if ($rc == 0 && !wait_for_service_state($bridge_service, 0));
		return $rc;
	}

	return run_perl("$bindir/vzlogger_mqtt_bridge.pl", "--stop");
}

sub restart_vzlogger
{
	stop_orphaned_obis_discovery_processes();
	if (!command_exists("systemctl")) {
		print "systemctl not available. Generated config only.\n";
		return 1;
	}

	if (!-d $runtime_dir) {
		make_path($runtime_dir);
	}
	chmod(0750, $runtime_dir);
	prepare_vzlogger_log_file();

	my $override_rc = install_vzlogger_service_override("install");
	if ($override_rc != 0) {
		print "Could not configure vzlogger to use $config_file.\n";
		print "Skipped vzlogger restart to avoid running with a different configuration.\n";
		return $override_rc;
	}

	my $enable_rc = enable_vzlogger_autostart();
	return $enable_rc if ($enable_rc != 0);
	my $restart_rc = run_privileged("restart vzlogger", systemctl_command(), "restart", "vzlogger");
	print "Restarted vzlogger service.\n" if ($restart_rc == 0);
	$restart_rc = 1 if ($restart_rc == 0 && !wait_for_service_state("vzlogger", 1));
	return $restart_rc;
}

sub prepare_vzlogger_log_file
{
	return if (!vzlogger_debug_enabled());
	make_path($plugin_log_dir) if (!-d $plugin_log_dir);

	if (!-e $vzlogger_log_file) {
		open(my $fh, ">>", $vzlogger_log_file) or do {
			print "Could not create $vzlogger_log_file: $!\n";
			return;
		};
		close($fh);
	}

	if ($> == 0) {
		my $vzlogger_uid = getpwnam("_vzlogger");
		my $loxberry_gid = getgrnam("loxberry");
		chown($vzlogger_uid, $loxberry_gid, $vzlogger_log_file) if (defined($vzlogger_uid) && defined($loxberry_gid));
		chmod(0640, $vzlogger_log_file);
		return;
	}

	# Ownership is established by the privileged service-override helper.
	chmod(0640, $vzlogger_log_file);
}

sub start_vzlogger
{
	stop_orphaned_obis_discovery_processes();
	if (!command_exists("systemctl")) {
		print "systemctl not available.\n";
		return 1;
	}
	if (!service_installed("vzlogger")) {
		print "vzlogger service is not installed.\n";
		return 1;
	}
	prepare_vzlogger_log_file();
	my $override_rc = install_vzlogger_service_override("install");
	if ($override_rc != 0) {
		print "Could not configure vzlogger to use $config_file.\n";
		print "Skipped vzlogger start to avoid running with a different configuration.\n";
		return $override_rc;
	}
	my $enable_rc = enable_vzlogger_autostart();
	return $enable_rc if ($enable_rc != 0);
	my $start_rc = run_privileged("start vzlogger", systemctl_command(), "start", "vzlogger");
	print "Started vzlogger service.\n" if ($start_rc == 0);
	$start_rc = 1 if ($start_rc == 0 && !wait_for_service_state("vzlogger", 1));
	return $start_rc;
}

sub stop_vzlogger
{
	my ($disable) = @_;
	stop_orphaned_obis_discovery_processes();
	return 1 if (!command_exists("systemctl"));
	if (!service_installed("vzlogger")) {
		print "vzlogger service is not installed.\n";
		return 0;
	}
	my $rc = run_privileged("stop vzlogger", systemctl_command(), "stop", "vzlogger");
	run_privileged("reset failed state for vzlogger", systemctl_command(), "reset-failed", "vzlogger") if ($rc == 0);
	$rc = 1 if ($rc == 0 && !wait_for_service_state("vzlogger", 0));
	if ($disable && $rc == 0) {
		my $disable_rc = run_privileged("disable vzlogger autostart", systemctl_command(), "disable", "vzlogger");
		print "Disabled vzlogger autostart.\n" if ($disable_rc == 0);
		return $disable_rc;
	}
	return $rc;
}

sub stop_orphaned_obis_discovery_processes
{
	return if (($ENV{SMARTMETER_OBIS_WATCHDOG} || "") eq "1");
	my $stopped_watchdog = 0;
	if (-e $obis_watchdog_pid_file && open(my $pid_fh, "<", $obis_watchdog_pid_file)) {
		my @watchdog_pids = <$pid_fh>;
		close($pid_fh);
		my $watchdog_pid = $watchdog_pids[0];
		my $test_group_pid = $watchdog_pids[1];
		chomp($watchdog_pid) if (defined($watchdog_pid));
		chomp($test_group_pid) if (defined($test_group_pid));
		if (obis_watchdog_running($watchdog_pid) && int($watchdog_pid) != $$) {
			kill("TERM", -int($test_group_pid)) if ($test_group_pid && $test_group_pid =~ /\A\d+\z/);
			$stopped_watchdog = kill("TERM", -int($watchdog_pid)) ? 1 : 0;
			log_control("terminated active OBIS discovery watchdog pid=$watchdog_pid") if ($stopped_watchdog);
			select(undef, undef, undef, 0.5);
			kill("KILL", -int($test_group_pid)) if ($test_group_pid && $test_group_pid =~ /\A\d+\z/);
			kill("KILL", -int($watchdog_pid));
		}
		unlink($obis_watchdog_pid_file);
	}

	my $config_prefix = "$home/config/plugins/$psubfolder/vzLogger_IrTest_";
	my @pids;
	opendir(my $proc, "/proc") or return;
	foreach my $entry (readdir($proc)) {
		next if ($entry !~ /\A\d+\z/ || $entry == $$);
		open(my $status_fh, "<", "/proc/$entry/status") or next;
		my $parent_pid = -1;
		while (my $line = <$status_fh>) {
			if ($line =~ /\APPid:\s+(\d+)/) {
				$parent_pid = int($1);
				last;
			}
		}
		close($status_fh);
		next if ($parent_pid != 1);

		open(my $cmdline_fh, "<", "/proc/$entry/cmdline") or next;
		local $/;
		my $cmdline = <$cmdline_fh>;
		close($cmdline_fh);
		my @args = grep { defined($_) && $_ ne "" } split(/\0/, $cmdline || "");
		next if (!@args || $args[0] !~ m{(?:\A|/)vzlogger\z});
		my $matches_plugin_test = 0;
		for (my $i = 0; $i < $#args; $i++) {
			if ($args[$i] eq "-c" && $args[$i + 1] =~ /\A\Q$config_prefix\E[A-Za-z0-9_.:-]+\.conf\z/) {
				$matches_plugin_test = 1;
				last;
			}
		}
		next if (!$matches_plugin_test);
		if (kill("TERM", int($entry))) {
			push @pids, int($entry);
			log_control("terminated orphaned OBIS discovery process pid=$entry");
		}
	}
	closedir($proc);
	return if (!@pids && !$stopped_watchdog);

	if (@pids) {
		select(undef, undef, undef, 0.5);
		foreach my $pid (@pids) {
			if (kill(0, $pid)) {
				kill("KILL", $pid);
				log_control("killed unresponsive orphaned OBIS discovery process pid=$pid");
			}
		}
	}
	my $count = scalar(@pids) + ($stopped_watchdog ? 1 : 0);
	mark_obis_discovery_cancelled("OBIS discovery was stopped by service action '$action'.");
	print "Stopped $count vzLogger OBIS discovery process(es).\n";
}

sub mark_obis_discovery_cancelled
{
	my ($message) = @_;
	return if (!-e $obis_status_file || !open(my $read_fh, "<", $obis_status_file));
	local $/;
	my $json = <$read_fh>;
	close($read_fh);
	my $status = eval { JSON::PP->new->utf8->decode($json || "") };
	return if (ref($status) ne "HASH" || ($status->{state} || "") !~ /\A(?:starting|running|cancelling)\z/);
	$status->{state} = "cancelled";
	$status->{ok} = JSON::PP::true;
	$status->{message} = $message;
	$status->{finished_at} = time();
	my $tmp = "$obis_status_file.$$";
	return if (!open(my $write_fh, ">", $tmp));
	print $write_fh JSON::PP->new->utf8->canonical->encode($status);
	close($write_fh);
	rename($tmp, $obis_status_file);
}

sub obis_watchdog_running
{
	my ($pid) = @_;
	return 0 if (!$pid || $pid !~ /\A\d+\z/ || !kill(0, int($pid)));
	open(my $cmdline_fh, "<", "/proc/$pid/cmdline") or return 0;
	local $/;
	my $cmdline = <$cmdline_fh>;
	close($cmdline_fh);
	return ($cmdline || "") =~ /\A\Q$psubfolder-vzlogger-obis-watchdog\E(?:\0|\s|\z)/ ? 1 : 0;
}

sub enable_vzlogger_autostart
{
	return 1 if (!command_exists("systemctl"));
	if (!service_installed("vzlogger")) {
		print "vzlogger service is not installed.\n";
		return 1;
	}
	my $enable_rc = run_privileged("enable vzlogger autostart", systemctl_command(), "enable", "vzlogger");
	print "Enabled vzlogger autostart.\n" if ($enable_rc == 0);
	return $enable_rc;
}

sub read_enabled
{
	my $cfg = SmartMeterConfig->new($plugin_config_file);
	return 0 if (!$cfg);
	return ($cfg->param("MAIN.READ") || "0") eq "1";
}

sub vzlogger_debug_enabled
{
	my $cfg = SmartMeterConfig->new($plugin_config_file);
	return 0 if (!$cfg);
	return ($cfg->param("VZLOGGER.VZLOGGERDEBUG") || "0") eq "1";
}

sub vzlogger_mode_enabled
{
	return implementation_mode(SmartMeterConfig->new($plugin_config_file)) eq "vzlogger";
}

sub bridge_enabled
{
	return 0 if (!vzlogger_mode_enabled() || !read_enabled());
	my $cfg = SmartMeterConfig->new($plugin_config_file);
	return 0 if (!$cfg);
	return generated_mqtt_enabled() if (($cfg->param("VZLOGGER.EXPERTMODE") || "0") eq "1");
	my $mqtt_enabled = $cfg->param("VZLOGGER.MQTTENABLED");
	return !defined($mqtt_enabled) || $mqtt_enabled eq "1";
}

sub generated_mqtt_enabled
{
	return 0 if (!-e $config_file);
	open(my $fh, "<", $config_file) or return 0;
	local $/;
	my $json = <$fh>;
	close($fh);
	my $config = eval { JSON::PP->new->utf8->decode($json) };
	return 0 if ($@ || ref($config) ne "HASH" || ref($config->{mqtt}) ne "HASH");
	return $config->{mqtt}->{enabled} ? 1 : 0;
}

sub install_bridge_service
{
	my ($action) = @_;
	my $script = "$bindir/install_vzlogger_bridge_service.sh";
	return message_exit("Bridge service helper not found: $script", 1) if (!-e $script);

	if ($> == 0) {
		system("sh", $script, $home, $psubfolder, $action);
		my $exit = $? >> 8;
		log_control("exit=$exit: sh $script $home $psubfolder $action");
		return $exit;
	}

	if (command_exists("sudo")) {
		system("sudo", "-n", "/bin/sh", $script, $home, $psubfolder, $action);
		my $exit = $? >> 8;
		log_control("exit=$exit: sudo -n /bin/sh $script $home $psubfolder $action");
		return $exit if ($exit == 0);
		print "Could not run sudo non-interactively. Run as root: sh $script $home $psubfolder $action\n";
		return $exit || 1;
	}

	print "Root privileges are required. Run as root: sh $script $home $psubfolder $action\n";
	log_control("root required: sh $script $home $psubfolder $action");
	return 2;
}

sub install_vzlogger_service_override
{
	my ($action) = @_;
	my $script = "$bindir/install_vzlogger_service_override.sh";
	return message_exit("vzLogger service override helper not found: $script", 1) if (!-e $script);

	if ($> == 0) {
		system("sh", $script, $home, $psubfolder, $action);
		my $exit = $? >> 8;
		log_control("exit=$exit: sh $script $home $psubfolder $action");
		return $exit;
	}

	if (command_exists("sudo")) {
		system("sudo", "-n", "/bin/sh", $script, $home, $psubfolder, $action);
		my $exit = $? >> 8;
		log_control("exit=$exit: sudo -n /bin/sh $script $home $psubfolder $action");
		return $exit if ($exit == 0);
		print "Could not run sudo non-interactively. Run as root: sh $script $home $psubfolder $action\n";
		return $exit || 1;
	}

	print "Root privileges are required. Run as root: sh $script $home $psubfolder $action\n";
	log_control("root required: sh $script $home $psubfolder $action");
	return 2;
}

sub bridge_running
{
	my $pid_file = "$runtime_dir/vzlogger_mqtt_bridge.pid";
	return 0 if (!-e $pid_file);
	open(my $fh, "<", $pid_file) or return 0;
	my $pid = <$fh>;
	close($fh);
	chomp($pid);
	return 0 if (!$pid || $pid !~ /\A\d+\z/);
	return kill(0, $pid) ? 1 : 0;
}

sub service_state
{
	my ($service) = @_;
	return "unknown" if (!command_exists("systemctl"));
	my $state = `systemctl is-active $service 2>/dev/null`;
	chomp($state);
	return $state || "inactive";
}

sub wait_for_service_state
{
	my ($service, $running) = @_;
	for (1 .. 20) {
		my $active = service_state($service) eq "active" ? 1 : 0;
		return 1 if ($active == ($running ? 1 : 0));
		select(undef, undef, undef, 0.1);
	}
	print "Service $service did not reach the requested " . ($running ? "running" : "stopped") . " state.\n";
	return 0;
}

sub service_summary
{
	my ($service) = @_;
	my $state = service_state($service);
	my $pid = service_pid($service);
	my $installed = service_installed($service) ? "installed" : "not installed";
	return "$state | PID: " . ($pid || "-") . " | Service: $service | $installed";
}

sub service_pid
{
	my ($service) = @_;
	return "" if (!command_exists("systemctl"));
	my $pid = `systemctl show -p MainPID --value $service 2>/dev/null`;
	chomp($pid);
	return ($pid && $pid ne "0") ? $pid : "";
}

sub service_installed
{
	my ($service) = @_;
	return 1 if (-e "/etc/systemd/system/$service.service");
	return 1 if (-e "/lib/systemd/system/$service.service");
	return 0;
}

sub systemctl_command
{
	return "/bin/systemctl" if (-x "/bin/systemctl");
	return "/usr/bin/systemctl" if (-x "/usr/bin/systemctl");
	return "systemctl";
}

sub package_state
{
	my ($package) = @_;
	return "unknown" if (!command_exists("dpkg-query"));
	my $state = `dpkg-query -W -f='\${Status}' $package 2>/dev/null`;
	chomp($state);
	return $state =~ /install ok installed/ ? "installed" : "not installed";
}

sub validation_state
{
	return "not generated" if (!-e $config_file);
	my $script = "$bindir/vzlogger_validate.pl";
	return "validator missing" if (!-e $script);
	my $command = shell_quote($^X) . " " . shell_quote($script) . " >/dev/null 2>&1";
	system($command);
	return ($? == 0) ? "valid" : "invalid";
}

sub create_debug_log
{
	my $timestamp = timestamp();
	my $debug_file = "$plugin_log_dir/vzlogger_debug_$timestamp.log";
	open(my $fh, ">", $debug_file) or return message_exit("Could not write $debug_file: $!", 1);

	print_section($fh, "SmartMeter vzLogger Debug Log");
	print $fh "Created: $timestamp\n";
	print $fh "Plugin: $psubfolder\n";
	print $fh "Runtime directory: $runtime_dir\n";
	print $fh "Plugin log directory: $plugin_log_dir\n";
	print $fh "Config file: $config_file\n";
	print $fh "Mapping file: $mapping_file\n";

	print_section($fh, "Control Status");
	print $fh "vzlogger binary: " . (command_exists("vzlogger") ? "available" : "missing") . "\n";
	print $fh "vzlogger package: " . package_state("vzlogger") . "\n";
	print $fh "Volkszaehler apt source: " . (-e "/etc/apt/sources.list.d/volkszaehler-volkszaehler-org-project.list" ? "configured" : "missing") . "\n";
	print $fh "vzlogger config: " . (-e $config_file ? $config_file : "missing") . "\n";
	print $fh "vzlogger service config: " . (-e $vzlogger_override_file ? $config_file : "system default") . "\n";
	print $fh "config validation: " . validation_state() . "\n";
	print $fh "vzlogger service: " . service_summary("vzlogger") . "\n";
	print $fh "MQTT bridge service: " . service_summary($bridge_service) . "\n";
	print $fh "MQTT bridge process: " . (bridge_running() ? "running" : "stopped") . "\n";

	print_section($fh, "Command Output");
	print_command($fh, "vzlogger --version", "vzlogger", "--version");
	print_command($fh, "systemctl status vzlogger", "systemctl", "status", "vzlogger", "--no-pager");
	print_command($fh, "systemctl cat vzlogger", "systemctl", "cat", "vzlogger", "--no-pager");
	print_command($fh, "systemctl status $bridge_service", "systemctl", "status", $bridge_service, "--no-pager");
	print_command($fh, "journalctl -u vzlogger", "journalctl", "-u", "vzlogger", "-n", "80", "--no-pager");
	print_command($fh, "journalctl -u $bridge_service", "journalctl", "-u", $bridge_service, "-n", "80", "--no-pager");

	print_file($fh, "Plugin config", $plugin_config_file, 1);
	print_file($fh, "Generated vzLogger config", $config_file, 1);
	print_file($fh, "Channel mapping", $mapping_file, 0);
	print_file($fh, "Control action log", latest_plugin_log("control"), 0, 200);
	print_file($fh, "Bridge log tail", latest_plugin_log("bridge"), 0, 200);
	print_loxberry_logs($fh, $debug_file);
	print_runtime_cache($fh);
	print_mqtt_capture($fh);

	close($fh);
	cleanup_debug_logs();
	print "Created debug log: $debug_file\n";
	print "Attach this file when reporting vzLogger/MQTT bridge issues.\n";
	return 0;
}

sub cleanup_debug_logs
{
	my @logs = sort glob("$plugin_log_dir/vzlogger_debug_*.log");
	while (@logs > 5) {
		my $oldest = shift @logs;
		unlink($oldest);
	}
}

sub print_section
{
	my ($fh, $title) = @_;
	print $fh "\n=== $title ===\n";
}

sub print_command
{
	my ($fh, $label, @command) = @_;
	print_section($fh, $label);
	if (!command_exists($command[0])) {
		print $fh "Command not available: $command[0]\n";
		return;
	}
	my $pid = open(my $cmd_fh, "-|", @command);
	if (!$pid) {
		print $fh "Could not run command: $!\n";
		return;
	}
	while (my $line = <$cmd_fh>) {
		redact_sensitive($line);
		print $fh $line;
	}
	close($cmd_fh);
	print $fh "Exit code: " . ($? >> 8) . "\n";
}

sub print_file
{
	my ($fh, $label, $file, $redact, $tail_lines) = @_;
	print_section($fh, $label);
	if (!defined($file) || $file eq "") {
		print $fh "Not available\n";
		return;
	}
	if (!-e $file) {
		print $fh "Missing: $file\n";
		return;
	}
	open(my $in, "<", $file) or do {
		print $fh "Could not read $file: $!\n";
		return;
	};
	my @lines = <$in>;
	close($in);
	@lines = @lines > $tail_lines ? @lines[-$tail_lines .. -1] : @lines if ($tail_lines);
	foreach my $line (@lines) {
		redact_sensitive($line) if ($redact);
		print $fh $line;
	}
}

sub redact_sensitive
{
	$_[0] =~ s/("(?:key)?pass(?:word)?"\s*:\s*")[^"]*/$1***REDACTED***/ig;
	$_[0] =~ s/("(?:token|secretKey)"\s*:\s*")[^"]*/$1***REDACTED***/ig;
	$_[0] =~ s/(\bMQTT(?:KEY)?PASS\s*=\s*).*/$1***REDACTED***/ig;
	$_[0] =~ s/(\bpass(?:word)?\s*=\s*).*/$1***REDACTED***/ig;
	$_[0] =~ s/(\s-P\s+)(?:"[^"]*"|'[^']*'|\S+)/$1***REDACTED***/g;
}

sub print_runtime_cache
{
	my ($fh) = @_;
	print_section($fh, "Runtime cache files");
	opendir(my $dir, $runtime_dir) or do {
		print $fh "Could not open $runtime_dir: $!\n";
		return;
	};
	my @files = sort grep { /\.data\z/ } readdir($dir);
	closedir($dir);
	if (!@files) {
		print $fh "No .data cache files found.\n";
		return;
	}
	foreach my $file (@files) {
		print_file($fh, "Cache file $file", "$runtime_dir/$file", 0);
	}
}

sub print_loxberry_logs
{
	my ($fh, $exclude_file) = @_;
	print_section($fh, "LoxBerry install and plugin logs");
	my @candidates = (
		"$home/log/plugins/$psubfolder/*.log",
		"$home/log/system/plugininstall*.log",
		"$home/log/system_tmpfs/plugininstall*.log",
		"$home/log/system_tmpfs/*.log",
		"/opt/loxberry/log/system/plugininstall*.log",
		"/opt/loxberry/log/system_tmpfs/plugininstall*.log",
	);
	my %seen;
	my @files;
	foreach my $pattern (@candidates) {
		push @files, grep { $_ ne $exclude_file && !$seen{$_}++ && -f $_ } glob($pattern);
	}
	if (!@files) {
		print $fh "No matching LoxBerry install or plugin log files found.\n";
		return;
	}
	foreach my $file (sort @files) {
		print_file($fh, "Log tail $file", $file, 1, 120);
	}
}

sub print_mqtt_capture
{
	my ($fh) = @_;
	print_section($fh, "MQTT capture for parser verification");
	if (!command_exists("mosquitto_sub")) {
		print $fh "mosquitto_sub is not available.\n";
		return;
	}
	if (!command_exists("timeout")) {
		print $fh "timeout is not available. Skipping bounded MQTT capture.\n";
		return;
	}
	my $cfg = SmartMeterConfig->new($plugin_config_file);
	my $base_topic = $cfg ? sanitize_topic($cfg->param("MAIN.MQTTTOPIC") || "smartmeter") : "smartmeter";
	my $topic = "$base_topic/vzlogger/#";
	my $mqtt = read_mqtt_settings();
	print $fh "Subscribe topic: $topic\n";
	print $fh "Broker: $mqtt->{host}:$mqtt->{port}\n";
	print $fh "Capture duration: 10 seconds\n";
	my @command = ("timeout", "10", "mosquitto_sub", "-h", $mqtt->{host}, "-p", $mqtt->{port}, "-t", $topic, "-F", "%t %p", "-q", $mqtt->{qos});
	push @command, ("-k", $mqtt->{keepalive}) if ($mqtt->{keepalive} > 0);
	push @command, ("--cafile", $mqtt->{cafile}) if ($mqtt->{cafile});
	push @command, ("--capath", $mqtt->{capath}) if ($mqtt->{capath});
	push @command, ("--cert", $mqtt->{certfile}) if ($mqtt->{certfile});
	push @command, ("--key", $mqtt->{keyfile}) if ($mqtt->{keyfile});
	push @command, ("-u", $mqtt->{user}) if ($mqtt->{user});
	push @command, ("-P", $mqtt->{pass}) if ($mqtt->{pass});
	my $pid = open(my $mqtt_fh, "-|", @command);
	if (!$pid) {
		print $fh "Could not start MQTT capture: $!\n";
		return;
	}
	my $count = 0;
	while (my $line = <$mqtt_fh>) {
		print $fh $line;
		$count++;
	}
	close($mqtt_fh);
	print $fh "Captured MQTT messages: $count\n";
	print $fh "Exit code: " . ($? >> 8) . "\n";
}

sub read_mqtt_settings
{
	my $cfg = SmartMeterConfig->new($plugin_config_file);
	my %settings = %{SmartMeterVZLoggerConfig::read_mqtt_settings($home, $cfg)};
	$settings{qos} = 0;
	$settings{keepalive} = 30;
	if ($cfg) {
		$settings{qos} = clean_qos($cfg->param("VZLOGGER.MQTTQOS"), 0);
		$settings{keepalive} = clean_number($cfg->param("VZLOGGER.MQTTKEEPALIVE"), 30);
	}
	return \%settings;
}

sub timestamp
{
	my ($sec, $min, $hour, $mday, $mon, $year) = localtime();
	return sprintf("%04d%02d%02d-%02d%02d%02d", $year + 1900, $mon + 1, $mday, $hour, $min, $sec);
}

sub shell_quote
{
	my ($value) = @_;
	$value =~ s/'/'"'"'/g;
	return "'$value'";
}

sub run_privileged
{
	my ($label, @command) = @_;
	log_control("privileged: $label");
	if ($> == 0) {
		system(@command);
		my $exit = $? >> 8;
		log_control("exit=$exit: " . join(" ", @command));
		return $exit;
	}
	if (command_exists("sudo")) {
		system("sudo", "-n", @command);
		my $exit = $? >> 8;
		print "Could not $label via sudo non-interactively.\n" if ($exit != 0);
		log_control("exit=$exit: sudo -n " . join(" ", @command));
		return $exit;
	}
	print "Root privileges are required to $label.\n";
	log_control("root required: " . join(" ", @command));
	return 2;
}

sub log_control
{
	LOGINF($_[0]);
}

# Returns the newest LoxBerry log file for a given base name (e.g. "control",
# "bridge"), or undef if none exists. Timestamped names are sorted lexically,
# which matches chronological order for the LoxBerry high-resolution prefix.
sub latest_plugin_log
{
	my ($name) = @_;
	my @files = sort glob("$plugin_log_dir/*_$name.log");
	return @files ? $files[-1] : undef;
}

sub message_exit
{
	my ($message, $exit_code) = @_;
	print "$message\n";
	return $exit_code;
}

sub command_exists
{
	my ($command) = @_;
	for my $dir (split(/:/, $ENV{PATH} || "")) {
		return 1 if (-x "$dir/$command");
	}
	return 0;
}
