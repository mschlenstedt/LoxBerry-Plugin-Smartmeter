package SmartMeterLegacyRuntime;

use strict;
use warnings;
use Exporter qw(import);
use Fcntl qw(:flock);
use File::Path qw(make_path);
use SmartMeterVZLoggerConfig qw(implementation_mode);

our @EXPORT_OK = qw(
	initialize_legacy_heads acquire_legacy_fetch_lock legacy_fetch_running
	remove_legacy_cronjobs apply_legacy_runtime clear_legacy_cache
	vzlogger_service_running synchronize_legacy_runtime
);

my @legacy_meter_fields = qw(METER PROTOCOL STARTBAUDRATE BAUDRATE TIMEOUT DELAY HANDSHAKE DATABITS STOPBITS PARITY CRC);
my @cron_folders = qw(cron.01min cron.03min cron.05min cron.10min cron.15min cron.30min cron.hourly cron.reboot);

sub initialize_legacy_heads
{
	my ($plugin_cfg, @heads) = @_;
	return 0 if (!$plugin_cfg);
	my $changed = 0;
	foreach my $device (@heads) {
		my $serial = $device;
		$serial =~ s%/dev/serial/smartmeter/%%g;
		if (!$plugin_cfg->param("$serial.DEVICE")) {
			$plugin_cfg->param("$serial.NAME", $serial);
			$plugin_cfg->param("$serial.SERIAL", $serial);
			$plugin_cfg->param("$serial.DEVICE", $device);
			$changed = 1;
		}
		next if (defined($plugin_cfg->param("$serial.LEGACY_METER")));
		foreach my $field (@legacy_meter_fields) {
			my $value = $plugin_cfg->param("$serial.$field");
			$value = $field eq "METER" ? "0" : "" if (!defined($value));
			$plugin_cfg->param("$serial.LEGACY_$field", $value);
		}
		$changed = 1;
	}
	return $changed;
}

sub acquire_legacy_fetch_lock
{
	my ($runtime_dir) = @_;
	make_path($runtime_dir, { mode => 0750 }) if (!-d $runtime_dir);
	my $file = "$runtime_dir/fetch.lock";
	open(my $fh, ">>", $file) or return (undef, "Could not open Legacy polling lock $file: $!");
	chmod(0640, $file);
	return (undef, "A Legacy meter polling run is currently active.") if (!flock($fh, LOCK_EX | LOCK_NB));
	return ($fh, "");
}

sub legacy_fetch_running
{
	my ($runtime_dir) = @_;
	my ($lock) = acquire_legacy_fetch_lock($runtime_dir);
	return $lock ? 0 : 1;
}

sub vzlogger_service_running
{
	my ($probe) = @_;
	return $probe->() ? 1 : 0 if (ref($probe) eq "CODE");
	return system("systemctl", "is-active", "--quiet", "vzlogger.service") == 0 ? 1 : 0;
}

sub remove_legacy_cronjobs
{
	my ($home, $plugin_id) = @_;
	foreach my $folder (@cron_folders) {
		my $target = "$home/system/cron/$folder/$plugin_id";
		unlink($target) if (-e $target || -l $target);
	}
}

sub apply_legacy_runtime
{
	my ($home, $plugin_id, $plugin_cfg, %options) = @_;
	remove_legacy_cronjobs($home, $plugin_id);
	return _runtime_result("Legacy meter polling is disabled. No cronjob restored.\n", 1)
		if (!$plugin_cfg || ($plugin_cfg->param("MAIN.READ") || "0") ne "1");

	my $cron = $plugin_cfg->param("MAIN.CRON") || "5";
	my %cron_map = (
		M => ["cron.reboot", "reboot_cron_runner.sh", "reboot"],
		1 => ["cron.01min", "fetch.pl", "1 minute"],
		3 => ["cron.03min", "fetch.pl", "3 minutes"],
		5 => ["cron.05min", "fetch.pl", "5 minutes"],
		10 => ["cron.10min", "fetch.pl", "10 minutes"],
		15 => ["cron.15min", "fetch.pl", "15 minutes"],
		30 => ["cron.30min", "fetch.pl", "30 minutes"],
		60 => ["cron.hourly", "fetch.pl", "hourly"],
	);
	return _runtime_result("Unknown cron interval '$cron'. No Legacy cronjob restored.\n", 0) if (!$cron_map{$cron});
	my ($folder, $script, $label) = @{$cron_map{$cron}};
	my $plugin_folder = $options{plugin_folder} || $plugin_id;
	my $source = "$home/bin/plugins/$plugin_folder/$script";
	my $target = "$home/system/cron/$folder/$plugin_id";
	unlink($target) if (-e $target || -l $target);
	symlink($source, $target) or return _runtime_result("Could not create Legacy cronjob $target: $!\n", 0);

	if ($cron eq "M" && $options{start_minimal_now}) {
		my $pid = fork();
		if (defined($pid) && $pid == 0) {
			open(STDIN, "<", "/dev/null");
			open(STDOUT, ">", "/dev/null");
			open(STDERR, ">", "/dev/null");
			exec($^X, "$home/bin/plugins/$plugin_id/fetch.pl");
			exit 1;
		}
	}
	return _runtime_result("Restored Legacy meter polling cronjob: $label\n", 1);
}

sub synchronize_legacy_runtime
{
	my ($home, $plugin_id, $plugin_cfg, %options) = @_;
	if (implementation_mode($plugin_cfg) ne "legacy") {
		remove_legacy_cronjobs($home, $plugin_id);
		return _runtime_result("Legacy mode is inactive. No cronjob restored.\n", 1);
	}
	return apply_legacy_runtime($home, $plugin_id, $plugin_cfg, %options);
}

sub _runtime_result
{
	my ($message, $ok) = @_;
	return wantarray ? ($message, $ok) : $message;
}

sub clear_legacy_cache
{
	my ($runtime_dir) = @_;
	return (0, "") if (!-d $runtime_dir);
	my ($removed, @errors) = (0);
	foreach my $file (glob("$runtime_dir/*")) {
		next if (!-f $file);
		my ($name) = $file =~ m{([^/]+)\z};
		next if (!defined($name) || $name !~ /\A(?:fetch(?:_manually)?\.log|[^.][^\/]*\.(?:data|dump|log))\z/);
		if (unlink($file)) { $removed++; }
		else { push @errors, "$name: $!"; }
	}
	return ($removed, join(", ", @errors));
}

1;
