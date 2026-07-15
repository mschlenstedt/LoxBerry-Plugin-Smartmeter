#!/usr/bin/perl

use strict;
use warnings;

use Config::Simple;
use File::Path qw(make_path);
use LoxBerry::System;

my $home = $lbhomedir;
my $psubfolder = $lbpplugindir;
my $bindir = "$home/bin/plugins/$psubfolder";
my $plugin_config_file = "$home/config/plugins/$psubfolder/smartmeter.cfg";
my $config_file = "$home/config/plugins/$psubfolder/vzlogger.conf";
my $mapping_file = "$home/config/plugins/$psubfolder/vzlogger_channels.json";
my $runtime_dir = "/var/run/shm/$psubfolder";
my $plugin_log_dir = "$home/log/plugins/$psubfolder";
my $control_log_file = "$plugin_log_dir/vzlogger_control.log";
my $vzlogger_log_file = "$plugin_log_dir/vzlogger.log";
my $bridge_service = "smartmeter-v2-vzlogger-bridge";
my $vzlogger_override_file = "/etc/systemd/system/vzlogger.service.d/smartmeter-v2.conf";
my $action = shift @ARGV || "status";

make_path($runtime_dir) if (!-d $runtime_dir);
make_path($plugin_log_dir) if (!-d $plugin_log_dir);
log_control("action=$action user=" . ($ENV{USER} || $ENV{LOGNAME} || "unknown"));

if ($action eq "generate") {
	exit generate_and_validate();
}

if ($action eq "apply") {
	my $rc = generate_and_validate();
	exit $rc if ($rc != 0);
	if (!vzlogger_mode_enabled()) {
		stop_bridge();
		stop_vzlogger(1);
		install_vzlogger_service_override("remove");
		print "vzLogger mode is disabled. Stopped vzLogger and bridge.\n";
		exit 0;
	}
	restart_vzlogger();
	if (bridge_enabled()) {
		restart_bridge();
	} else {
		stop_bridge();
		print "MQTT bridge is disabled. Stopped bridge and left vzLogger running.\n";
	}
	exit 0;
}

if ($action eq "restart-vzlogger") {
	my $rc = generate_and_validate();
	exit $rc if ($rc != 0);
	if (!vzlogger_mode_enabled()) {
		print "vzLogger mode is disabled. Did not restart vzLogger.\n";
		exit 0;
	}
	restart_vzlogger();
	exit 0;
}

if ($action eq "start-vzlogger") {
	my $rc = generate_and_validate();
	exit $rc if ($rc != 0);
	if (!vzlogger_mode_enabled()) {
		print "vzLogger mode is disabled. Did not start vzLogger.\n";
		exit 0;
	}
	start_vzlogger();
	exit 0;
}

if ($action eq "stop-vzlogger") {
	stop_vzlogger();
	exit 0;
}

if ($action eq "restart-bridge") {
	my $rc = generate_and_validate();
	exit $rc if ($rc != 0);
	if (!bridge_enabled()) {
		print "MQTT bridge is disabled. Did not restart the MQTT bridge.\n";
		exit 0;
	}
	restart_bridge();
	exit 0;
}

if ($action eq "validate") {
	exit generate_and_validate();
}

if ($action eq "start-bridge") {
	my $rc = generate_and_validate();
	exit $rc if ($rc != 0);
	if (!bridge_enabled()) {
		print "MQTT bridge is disabled. Did not start the MQTT bridge.\n";
		exit 0;
	}
	start_bridge();
	exit 0;
}

if ($action eq "stop-bridge") {
	stop_bridge();
	exit 0;
}

if ($action eq "disable-vzlogger") {
	stop_bridge();
	stop_vzlogger(1);
	install_vzlogger_service_override("remove");
	print "Stopped vzLogger and bridge.\n";
	exit 0;
}

if ($action eq "status") {
	print "implementation: " . implementation_mode() . "\n";
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

print "Usage: $0 generate|validate|apply|restart-vzlogger|start-vzlogger|stop-vzlogger|restart-bridge|start-bridge|stop-bridge|disable-vzlogger|status|debug-log\n";
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
	my $rc = run_perl("$bindir/vzlogger_config.pl");
	return $rc if ($rc != 0);
	return run_perl("$bindir/vzlogger_validate.pl");
}

sub start_bridge
{
	my $install_rc = install_bridge_service("install");
	return if ($install_rc != 0);

	if (service_installed($bridge_service)) {
		my $rc = run_privileged("start $bridge_service", systemctl_command(), "start", $bridge_service);
		print "Started $bridge_service service.\n" if ($rc == 0);
		return;
	}

	return if (bridge_running());

	my $pid = fork();
	die "Could not fork bridge process: $!\n" if (!defined($pid));
	if ($pid == 0) {
		open STDIN, "</dev/null";
		open STDOUT, ">>$home/log/plugins/$psubfolder/vzlogger_mqtt_bridge.log";
		open STDERR, ">>$home/log/plugins/$psubfolder/vzlogger_mqtt_bridge.log";
		exec($^X, "$bindir/vzlogger_mqtt_bridge.pl");
		exit 1;
	}
	print "Started bridge process $pid.\n";
}

sub restart_bridge
{
	my $install_rc = install_bridge_service("install");
	return if ($install_rc != 0);

	if (service_installed($bridge_service)) {
		my $rc = run_privileged("restart $bridge_service", systemctl_command(), "restart", $bridge_service);
		print "Restarted $bridge_service service.\n" if ($rc == 0);
		return;
	}

	stop_bridge();
	start_bridge();
}

sub stop_bridge
{
	if (service_installed($bridge_service)) {
		my $rc = run_privileged("stop $bridge_service", systemctl_command(), "stop", $bridge_service);
		run_privileged("reset failed state for $bridge_service", systemctl_command(), "reset-failed", $bridge_service) if ($rc == 0);
		print "Stopped $bridge_service service.\n" if ($rc == 0);
		return;
	}

	run_perl("$bindir/vzlogger_mqtt_bridge.pl", "--stop");
}

sub restart_vzlogger
{
	if (!command_exists("systemctl")) {
		print "systemctl not available. Generated config only.\n";
		return;
	}

	if (!-d $runtime_dir) {
		make_path($runtime_dir);
	}
	chmod(0777, $runtime_dir);
	prepare_vzlogger_log_file();

	my $override_rc = install_vzlogger_service_override("install");
	if ($override_rc != 0) {
		print "Could not configure vzlogger to use $config_file.\n";
		print "Skipped vzlogger restart to avoid running with a different configuration.\n";
		return;
	}

	enable_vzlogger_autostart();
	my $restart_rc = run_privileged("restart vzlogger", systemctl_command(), "restart", "vzlogger");
	print "Restarted vzlogger service.\n" if ($restart_rc == 0);
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
		my $adm_gid = getgrnam("adm");
		chown($vzlogger_uid, $adm_gid, $vzlogger_log_file) if (defined($vzlogger_uid) && defined($adm_gid));
		chmod(0664, $vzlogger_log_file);
		return;
	}

	# Web actions run as loxberry and may not have sudo rights for chown/chmod.
	# Keep the file writable for the _vzlogger service user when root setup is not available.
	chmod(0666, $vzlogger_log_file);
}

sub start_vzlogger
{
	if (!command_exists("systemctl")) {
		print "systemctl not available.\n";
		return;
	}
	if (!service_installed("vzlogger")) {
		print "vzlogger service is not installed.\n";
		return;
	}
	prepare_vzlogger_log_file();
	my $override_rc = install_vzlogger_service_override("install");
	if ($override_rc != 0) {
		print "Could not configure vzlogger to use $config_file.\n";
		print "Skipped vzlogger start to avoid running with a different configuration.\n";
		return;
	}
	enable_vzlogger_autostart();
	my $start_rc = run_privileged("start vzlogger", systemctl_command(), "start", "vzlogger");
	print "Started vzlogger service.\n" if ($start_rc == 0);
}

sub stop_vzlogger
{
	my ($disable) = @_;
	return if (!command_exists("systemctl"));
	if (!service_installed("vzlogger")) {
		print "vzlogger service is not installed.\n";
		return;
	}
	my $rc = run_privileged("stop vzlogger", systemctl_command(), "stop", "vzlogger");
	if ($disable && $rc == 0) {
		my $disable_rc = run_privileged("disable vzlogger autostart", systemctl_command(), "disable", "vzlogger");
		print "Disabled vzlogger autostart.\n" if ($disable_rc == 0);
	}
	run_privileged("reset failed state for vzlogger", systemctl_command(), "reset-failed", "vzlogger") if ($rc == 0);
}

sub enable_vzlogger_autostart
{
	return if (!command_exists("systemctl"));
	if (!service_installed("vzlogger")) {
		print "vzlogger service is not installed.\n";
		return;
	}
	my $enable_rc = run_privileged("enable vzlogger autostart", systemctl_command(), "enable", "vzlogger");
	print "Enabled vzlogger autostart.\n" if ($enable_rc == 0);
}

sub read_enabled
{
	my $cfg = Config::Simple->new($plugin_config_file);
	return 0 if (!$cfg);
	return ($cfg->param("MAIN.READ") || "0") eq "1";
}

sub vzlogger_debug_enabled
{
	my $cfg = Config::Simple->new($plugin_config_file);
	return 0 if (!$cfg);
	return ($cfg->param("VZLOGGER.VZLOGGERDEBUG") || "0") eq "1";
}

sub implementation_mode
{
	my $cfg = Config::Simple->new($plugin_config_file);
	return "legacy" if (!$cfg);
	my $mode = $cfg->param("MAIN.IMPLEMENTATION") || "";
	return $mode if ($mode =~ /\A(?:legacy|vzlogger)\z/);
	return read_enabled() ? "legacy" : "vzlogger";
}

sub vzlogger_mode_enabled
{
	return implementation_mode() eq "vzlogger";
}

sub bridge_enabled
{
	return vzlogger_mode_enabled() && read_enabled();
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

	print_file($fh, "Plugin config", $plugin_config_file, 0);
	print_file($fh, "Generated vzLogger config", $config_file, 1);
	print_file($fh, "Channel mapping", $mapping_file, 0);
	print_file($fh, "Control action log", $control_log_file, 0, 200);
	print_file($fh, "Bridge log tail", "$home/log/plugins/$psubfolder/vzlogger_mqtt_bridge.log", 0, 200);
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
	$_[0] =~ s/("pass"\s*:\s*")[^"]*/$1***REDACTED***/ig;
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
	my $cfg = Config::Simple->new($plugin_config_file);
	my $base_topic = $cfg ? sanitize_topic($cfg->param("MAIN.MQTTTOPIC") || "smartmeter") : "smartmeter";
	my $topic = "$base_topic/vzlogger/#";
	my $mqtt = read_mqtt_settings();
	print $fh "Subscribe topic: $topic\n";
	print $fh "Broker: $mqtt->{host}:$mqtt->{port}\n";
	print $fh "Capture duration: 10 seconds\n";
	my @command = ("timeout", "10", "mosquitto_sub", "-h", $mqtt->{host}, "-p", $mqtt->{port}, "-t", $topic, "-F", "%t %p");
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
	my $general_json = "$home/config/system/general.json";
	my %settings = (
		host => "127.0.0.1",
		port => 1883,
		user => "",
		pass => "",
	);

	return \%settings if (!-e $general_json);
	open(my $fh, "<", $general_json) or return \%settings;
	local $/;
	my $json_text = <$fh>;
	close($fh);

	eval { require JSON::PP; };
	return \%settings if ($@);
	my $general = eval { JSON::PP->new->utf8->decode($json_text) };
	return \%settings if ($@ || !ref($general) || !ref($general->{Mqtt}));

	my $mqtt = $general->{Mqtt};
	$settings{host} = first_value($mqtt, qw(Host Hostname Broker Brokerhost Server IpAddress Ipaddress)) || $settings{host};
	$settings{port} = clean_number(first_value($mqtt, qw(Port Brokerport Mqttport)), $settings{port});
	$settings{user} = first_value($mqtt, qw(Brokeruser Brokerusername User Username Login)) || "";
	$settings{pass} = first_value($mqtt, qw(Brokerpass Brokerpassword Pass Password)) || "";
	return \%settings;
}

sub first_value
{
	my ($hash, @keys) = @_;
	foreach my $key (@keys) {
		return $hash->{$key} if (defined($hash->{$key}) && $hash->{$key} ne "");
	}
	return undef;
}

sub clean_number
{
	my ($value, $default) = @_;
	return int($value) if (defined($value) && $value =~ /\A\d+\z/);
	return $default;
}

sub sanitize_topic
{
	my ($topic) = @_;
	$topic ||= "smartmeter";
	$topic =~ s/^\s+|\s+$//g;
	$topic =~ s/^\/+|\/+$//g;
	$topic =~ s/[#+]//g;
	return $topic || "smartmeter";
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
	my ($message) = @_;
	if (-e $control_log_file && -s $control_log_file >= 512 * 1024) {
		unlink("$control_log_file.1") if (-e "$control_log_file.1");
		rename($control_log_file, "$control_log_file.1");
	}
	open(my $fh, ">>", $control_log_file) or return;
	print $fh timestamp() . " $message\n";
	close($fh);
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
