package LoxBerry::System;
use strict;
use warnings;

our $lbhomedir = '/opt/loxberry';
our $lbpplugindir = 'smartmeter-v2';
our $lbpbindir = '/opt/loxberry/bin/plugins/smartmeter-v2';
our $lbpconfigdir = '/opt/loxberry/config/plugins/smartmeter-v2';
our $lbptemplatedir = '/opt/loxberry/templates/plugins/smartmeter-v2';
our $lbplogdir = '/opt/loxberry/log/plugins/smartmeter-v2';

sub import {
	my $caller = caller;
	no strict 'refs';
	*{"${caller}::lbhomedir"} = \$lbhomedir;
	*{"${caller}::lbpplugindir"} = \$lbpplugindir;
	*{"${caller}::lbpbindir"} = \$lbpbindir;
	*{"${caller}::lbpconfigdir"} = \$lbpconfigdir;
	*{"${caller}::lbptemplatedir"} = \$lbptemplatedir;
	*{"${caller}::lbplogdir"} = \$lbplogdir;
}

sub pluginversion { return '0.0.0'; }
sub readlanguage { return (); }

1;
