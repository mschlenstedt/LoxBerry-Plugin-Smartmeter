package LoxBerry::Log;
use strict;
use warnings;

# Minimal CI stub for LoxBerry::Log. It mirrors just enough of the real module
# for syntax checks and unit tests on a plain Perl install without LoxBerry:
# the directory variables that plugin code imports, plus a logging object whose
# LOG* methods are no-ops. The real module registers the log in the LoxBerry log
# database and honours PLUGINDB_LOGLEVEL; that behaviour is not reproduced here.

our $lbhomedir = '/opt/loxberry';
our $lbpplugindir = 'smartmeter-ng';
our $lbpbindir = '/opt/loxberry/bin/plugins/smartmeter-ng';
our $lbpconfigdir = '/opt/loxberry/config/plugins/smartmeter-ng';
our $lbptemplatedir = '/opt/loxberry/templates/plugins/smartmeter-ng';
our $lbplogdir = '/opt/loxberry/log/plugins/smartmeter-ng';

our @LOG_METHODS = qw(LOGDEB LOGINF LOGOK LOGWARN LOGERR LOGCRIT LOGALERT LOGEMERGE LOGSTART LOGEND LOGTITLE);

sub import {
	my $caller = caller;
	no strict 'refs';
	*{"${caller}::lbhomedir"} = \$lbhomedir;
	*{"${caller}::lbpplugindir"} = \$lbpplugindir;
	*{"${caller}::lbpbindir"} = \$lbpbindir;
	*{"${caller}::lbpconfigdir"} = \$lbpconfigdir;
	*{"${caller}::lbptemplatedir"} = \$lbptemplatedir;
	*{"${caller}::lbplogdir"} = \$lbplogdir;
	# The real module exports the LOG* functions, which act on the last created
	# log object. The stub exports them as no-ops so callers using the function
	# form (e.g. LOGINF "message") pass a syntax check.
	*{"${caller}::$_"} = \&{$_} for @LOG_METHODS;
}

sub new {
	my ($class, %params) = @_;
	return bless { %params }, ref($class) || $class;
}

sub filename { return $_[0]->{filename}; }
sub loglevel { my $self = shift; $self->{loglevel} = shift if (@_); return $self->{loglevel}; }
sub dbkey { return $_[0]->{dbkey}; }
sub open { return 1; }
sub close { return 1; }

# Logging methods are no-ops in the stub. They work both as object methods
# ($log->LOGINF(...)) and as exported functions (LOGINF ...).
for my $method (@LOG_METHODS) {
	no strict 'refs';
	*{$method} = sub { return 1; };
}

1;
