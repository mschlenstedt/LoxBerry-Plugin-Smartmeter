#!/usr/bin/perl

use strict;
use warnings;
use FindBin;
use Test::More;

sub read_file {
	my ($file) = @_;
	open(my $fh, "<", $file) or die "Could not read $file: $!";
	local $/;
	my $text = <$fh>;
	close($fh);
	return $text;
}

my $control = read_file("$FindBin::Bin/../bin/vzlogger_control.pl");
my $installer = read_file("$FindBin::Bin/../bin/install_vzlogger_bridge_service.sh");
my $postroot = read_file("$FindBin::Bin/../postroot.sh");

unlike(
	$installer,
	qr/systemctl\s+enable\s+"\$SERVICE_NAME"/,
	"installing or refreshing the bridge unit does not implicitly enable autostart",
);
like(
	$control,
	qr/sub\s+start_bridge\b.*?set_bridge_autostart\(1\).*?systemctl_command\(\),\s*"start"/s,
	"starting the configured bridge enables autostart before starting the service",
);
like(
	$control,
	qr/sub\s+restart_bridge\b.*?set_bridge_autostart\(1\).*?systemctl_command\(\),\s*"restart"/s,
	"restarting the configured bridge enables autostart before restarting the service",
);
like(
	$control,
	qr/sub\s+stop_and_disable_bridge\b.*?stop_bridge\(\).*?set_bridge_autostart\(0\)/s,
	"configuration-driven bridge shutdown stops the process and disables autostart",
);
like(
	$control,
	qr/if\s*\(\$action eq "disable-vzlogger"\)\s*\{\s*my \$rc = stop_and_disable_bridge\(\);/s,
	"switching away from vzLogger disables bridge autostart",
);
like(
	$control,
	qr/generated_meter_count\(\) == 0\)\s*\{\s*my \$stop_rc = stop_and_disable_bridge\(\);/s,
	"applying a meterless configuration disables bridge autostart",
);
like(
	$control,
	qr/if\s*\(!vzlogger_mode_enabled\(\)\)\s*\{\s*my \$rc = stop_and_disable_bridge\(\);/s,
	"applying an inactive implementation disables bridge autostart",
);
like(
	$control,
	qr/if\s*\(bridge_enabled\(\)\).*?else\s*\{\s*\$rc = stop_and_disable_bridge\(\);/s,
	"applying a disabled bridge disables its autostart",
);
like(
	$control,
	qr/if\s*\(\$action eq "stop-bridge"\)\s*\{\s*exit stop_bridge\(\);/s,
	"manual bridge Stop remains temporary and does not change saved autostart behavior",
);
like(
	$postroot,
	qr/systemctl stop "\$BRIDGE_SERVICE".*?systemctl disable "\$BRIDGE_SERVICE".*?systemctl reset-failed/s,
	"inactive install and upgrade handling stops and disables the bridge",
);

done_testing();
