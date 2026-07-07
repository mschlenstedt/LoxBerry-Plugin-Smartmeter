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
my $bridge_service = "smartmeter-v2-vzlogger-bridge";
my $action = shift @ARGV || "status";

make_path($runtime_dir) if (!-d $runtime_dir);

if ($action eq "generate") {
	my $rc = run_perl("$bindir/vzlogger_config.pl");
	exit $rc if ($rc != 0);
	exit run_perl("$bindir/vzlogger_validate.pl");
}

if ($action eq "apply") {
	my $rc = run_perl("$bindir/vzlogger_config.pl");
	exit $rc if ($rc != 0);
	$rc = run_perl("$bindir/vzlogger_validate.pl");
	exit $rc if ($rc != 0);
	if (!read_enabled()) {
		stop_bridge();
		stop_vzlogger();
		print "Meter reading is disabled. Stopped vzLogger and bridge.\n";
		exit 0;
	}
	restart_vzlogger();
	start_bridge();
	exit 0;
}

if ($action eq "install-vzlogger") {
	exit install_vzlogger();
}

if ($action eq "install-bridge-service") {
	exit install_bridge_service("install");
}

if ($action eq "remove-bridge-service") {
	exit install_bridge_service("remove");
}

if ($action eq "validate") {
	exit run_perl("$bindir/vzlogger_validate.pl");
}

if ($action eq "start-bridge") {
	start_bridge();
	exit 0;
}

if ($action eq "stop-bridge") {
	stop_bridge();
	exit 0;
}

if ($action eq "status") {
	print "vzlogger binary: " . (command_exists("vzlogger") ? "available" : "missing") . "\n";
	print "vzlogger package: " . package_state("vzlogger") . "\n";
	print "Volkszaehler apt source: " . (-e "/etc/apt/sources.list.d/volkszaehler-volkszaehler-org-project.list" ? "configured" : "missing") . "\n";
	print "vzlogger config: " . (-e $config_file ? $config_file : "missing") . "\n";
	print "config validation: " . validation_state() . "\n";
	print "vzlogger service: " . service_state("vzlogger") . "\n";
	print "MQTT bridge service: " . service_state($bridge_service) . "\n";
	print "MQTT bridge process: " . (bridge_running() ? "running" : "stopped") . "\n";
	exit 0;
}

if ($action eq "debug-log") {
	exit create_debug_log();
}

print "Usage: $0 generate|validate|apply|install-vzlogger|install-bridge-service|remove-bridge-service|start-bridge|stop-bridge|status|debug-log\n";
exit 1;

sub run_perl
{
	my @args = @_;
	system($^X, @args);
	return $? >> 8;
}

sub start_bridge
{
	if (service_installed($bridge_service)) {
		system("systemctl", "restart", $bridge_service);
		print "Restarted $bridge_service service.\n";
		return;
	}

	return if (bridge_running());

	my $pid = fork();
	die "Could not fork bridge process: $!\n" if (!defined($pid));
	if ($pid == 0) {
		open STDIN, "</dev/null";
		open STDOUT, ">>$runtime_dir/vzlogger_mqtt_bridge.log";
		open STDERR, ">>$runtime_dir/vzlogger_mqtt_bridge.log";
		exec($^X, "$bindir/vzlogger_mqtt_bridge.pl");
		exit 1;
	}
	print "Started bridge process $pid.\n";
}

sub stop_bridge
{
	if (service_installed($bridge_service)) {
		system("systemctl", "stop", $bridge_service);
		print "Stopped $bridge_service service.\n";
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

	if (-e $config_file) {
		my $copy_rc = system("cp", $config_file, "/etc/vzlogger.conf");
		print "Copied config to /etc/vzlogger.conf.\n" if ($copy_rc == 0);
		print "Could not copy config to /etc/vzlogger.conf. Run as root or copy it manually.\n" if ($copy_rc != 0);
	}

	system("systemctl", "restart", "vzlogger");
	print "Restarted vzlogger service.\n";
}

sub stop_vzlogger
{
	return if (!command_exists("systemctl"));
	system("systemctl", "stop", "vzlogger");
}

sub read_enabled
{
	my $cfg = Config::Simple->new($plugin_config_file);
	return 0 if (!$cfg);
	return ($cfg->param("MAIN.READ") || "0") eq "1";
}

sub install_vzlogger
{
	my $script = "$bindir/install_vzlogger_package.sh";
	return message_exit("Install helper not found: $script", 1) if (!-e $script);

	if ($> == 0) {
		system("sh", $script);
		return $? >> 8;
	}

	if (command_exists("sudo")) {
		system("sudo", "-n", "sh", $script);
		my $exit = $? >> 8;
		return $exit if ($exit == 0);
		print "Could not run sudo non-interactively. Run as root: sh $script\n";
		return $exit || 1;
	}

	print "Root privileges are required. Run as root: sh $script\n";
	return 2;
}

sub install_bridge_service
{
	my ($action) = @_;
	my $script = "$bindir/install_vzlogger_bridge_service.sh";
	return message_exit("Bridge service helper not found: $script", 1) if (!-e $script);

	if ($> == 0) {
		system("sh", $script, $home, $psubfolder, $action);
		return $? >> 8;
	}

	if (command_exists("sudo")) {
		system("sudo", "-n", "sh", $script, $home, $psubfolder, $action);
		my $exit = $? >> 8;
		return $exit if ($exit == 0);
		print "Could not run sudo non-interactively. Run as root: sh $script $home $psubfolder $action\n";
		return $exit || 1;
	}

	print "Root privileges are required. Run as root: sh $script $home $psubfolder $action\n";
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

sub service_installed
{
	my ($service) = @_;
	return 1 if (-e "/etc/systemd/system/$service.service");
	return 1 if (-e "/lib/systemd/system/$service.service");
	return 0;
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
	my $debug_file = "$runtime_dir/vzlogger_debug_$timestamp.log";
	open(my $fh, ">", $debug_file) or return message_exit("Could not write $debug_file: $!", 1);

	print_section($fh, "SmartMeter vzLogger Debug Log");
	print $fh "Created: $timestamp\n";
	print $fh "Plugin: $psubfolder\n";
	print $fh "Runtime directory: $runtime_dir\n";
	print $fh "Config file: $config_file\n";
	print $fh "Mapping file: $mapping_file\n";

	print_section($fh, "Control Status");
	print $fh "vzlogger binary: " . (command_exists("vzlogger") ? "available" : "missing") . "\n";
	print $fh "vzlogger package: " . package_state("vzlogger") . "\n";
	print $fh "Volkszaehler apt source: " . (-e "/etc/apt/sources.list.d/volkszaehler-volkszaehler-org-project.list" ? "configured" : "missing") . "\n";
	print $fh "vzlogger config: " . (-e $config_file ? $config_file : "missing") . "\n";
	print $fh "config validation: " . validation_state() . "\n";
	print $fh "vzlogger service: " . service_state("vzlogger") . "\n";
	print $fh "MQTT bridge service: " . service_state($bridge_service) . "\n";
	print $fh "MQTT bridge process: " . (bridge_running() ? "running" : "stopped") . "\n";

	print_section($fh, "Command Output");
	print_command($fh, "vzlogger --version", "vzlogger", "--version");
	print_command($fh, "systemctl status vzlogger", "systemctl", "status", "vzlogger", "--no-pager");
	print_command($fh, "systemctl status $bridge_service", "systemctl", "status", $bridge_service, "--no-pager");
	print_command($fh, "journalctl -u vzlogger", "journalctl", "-u", "vzlogger", "-n", "80", "--no-pager");
	print_command($fh, "journalctl -u $bridge_service", "journalctl", "-u", $bridge_service, "-n", "80", "--no-pager");

	print_file($fh, "Plugin config", $plugin_config_file, 0);
	print_file($fh, "Generated vzLogger config", $config_file, 1);
	print_file($fh, "Channel mapping", $mapping_file, 0);
	print_file($fh, "Bridge log tail", "$runtime_dir/vzlogger_mqtt_bridge.log", 0, 200);
	print_runtime_cache($fh);
	print_mqtt_capture($fh);

	close($fh);
	print "Created debug log: $debug_file\n";
	print "Attach this file when reporting vzLogger/MQTT bridge issues.\n";
	return 0;
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
		$line =~ s/("pass"\s*:\s*")[^"]*/$1***REDACTED***/i if ($redact);
		$line =~ s/(\bpass(?:word)?\s*=\s*).*/$1***REDACTED***/i if ($redact);
		print $fh $line;
	}
}

sub print_runtime_cache
{
	my ($fh) = @_;
	print_section($fh, "Runtime cache files");
	if (!opendir(my $dir, $runtime_dir)) {
		print $fh "Could not open $runtime_dir: $!\n";
		return;
	}
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
	$settings{user} = first_value($mqtt, qw(User Username Login)) || "";
	$settings{pass} = first_value($mqtt, qw(Pass Password)) || "";
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
