package SmartMeterConfig;

use strict;
use warnings;
use LoxBerry::JSON;

# JSON-backed plugin configuration.
#
# The plugin configuration used to be an INI file read through Config::Simple.
# It is stored as JSON now, but the "SECTION.KEY" accessor style is kept so the
# existing call sites continue to work:
#
#   MAIN.READ        ->  { "MAIN":     { "READ": ... } }
#   VZLOGGER.RETRY   ->  { "VZLOGGER": { "RETRY": ... } }
#   <serial>.NAME    ->  { "METERS":   { "<serial>": { "NAME": ... } } }
#
# Every section that is not MAIN or VZLOGGER is a meter, addressed by the
# reader serial. Unlike the INI layout, meters live in their own METERS object
# instead of sitting next to the global sections.
#
# Values are kept as strings, matching the comparisons and regular expressions
# used throughout the plugin. List values (for example OBISCHANNELS) are stored
# as real JSON arrays and returned as array references, which is what
# Config::Simple did for multi-value keys.

my %TOP_SECTION = map { $_ => 1 } qw(MAIN VZLOGGER);
our $ERROR = "";

# new() reports a missing file as an error, like Config::Simple did, because the
# call sites treat that as fatal. create() is the explicit way to start a new
# configuration file.
sub new
{
	my ($class, $filename) = @_;
	if (!defined($filename) || $filename eq "" || !-e $filename) {
		$ERROR = defined($filename) ? "Configuration file $filename does not exist" : "No configuration file given";
		return undef;
	}
	return $class->create($filename);
}

sub create
{
	my ($class, $filename) = @_;
	if (!defined($filename) || $filename eq "") {
		$ERROR = "No configuration file given";
		return undef;
	}
	my $jsonobj = LoxBerry::JSON->new();
	my $data = eval { $jsonobj->open(filename => $filename) };
	if ($@ || ref($data) ne "HASH") {
		$ERROR = $@ || "Could not read $filename";
		return undef;
	}
	foreach my $section (qw(MAIN VZLOGGER METERS)) {
		$data->{$section} = {} if (ref($data->{$section}) ne "HASH");
	}
	$ERROR = "";
	return bless { filename => $filename, jsonobj => $jsonobj, data => $data }, ref($class) || $class;
}

sub error { return $ERROR; }

# Resolves "SECTION.KEY" to the hash holding the key, plus the key itself.
sub _resolve
{
	my ($self, $name, $create) = @_;
	return (undef, undef) if (!defined($name));
	my ($section, $key) = $name =~ /\A([^.]+)\.(.+)\z/;
	return (undef, undef) if (!defined($section));
	return ($self->{data}->{$section}, $key) if ($TOP_SECTION{$section});

	my $meters = $self->{data}->{METERS};
	if (ref($meters->{$section}) ne "HASH") {
		return (undef, undef) if (!$create);
		$meters->{$section} = {};
	}
	return ($meters->{$section}, $key);
}

# param()            -> all keys as "SECTION.KEY"
# param($name)       -> value (scalar, or array reference for list values)
# param($name, $val) -> set value
sub param
{
	my $self = shift;
	return $self->keys_list() if (!@_);
	my ($name, $value) = @_;
	if (@_ >= 2) {
		my ($hash, $key) = $self->_resolve($name, 1);
		return undef if (!$hash);
		$hash->{$key} = $value;
		return $value;
	}
	my ($hash, $key) = $self->_resolve($name, 0);
	return undef if (!$hash);
	return $hash->{$key};
}

sub delete
{
	my ($self, $name) = @_;
	my ($hash, $key) = $self->_resolve($name, 0);
	return if (!$hash);
	CORE::delete $hash->{$key};
	# Drop a meter section once its last key is gone so removed readers leave
	# no empty object behind.
	my ($section) = $name =~ /\A([^.]+)\./;
	if (defined($section) && !$TOP_SECTION{$section}) {
		my $meter = $self->{data}->{METERS}->{$section};
		CORE::delete $self->{data}->{METERS}->{$section}
			if (ref($meter) eq "HASH" && !%{$meter});
	}
	return 1;
}

sub keys_list
{
	my ($self) = @_;
	my @keys;
	foreach my $section (sort CORE::keys %TOP_SECTION) {
		push @keys, map { "$section.$_" } sort CORE::keys %{$self->{data}->{$section} || {}};
	}
	my $meters = $self->{data}->{METERS} || {};
	foreach my $serial (sort CORE::keys %{$meters}) {
		push @keys, map { "$serial.$_" } sort CORE::keys %{$meters->{$serial} || {}};
	}
	return @keys;
}

# Direct access for code that works with the structure instead of flat keys.
sub meters { return $_[0]->{data}->{METERS}; }
sub data { return $_[0]->{data}; }
sub filename { return $_[0]->{filename}; }

sub save { return $_[0]->{jsonobj}->write(); }

# Fills a flat "SECTION.KEY" => value hash, replacing Config::Simple->import_from.
sub import_from
{
	my ($class, $filename, $target) = @_;
	return 0 if (ref($target) ne "HASH");
	my $cfg = $class->new($filename);
	return 0 if (!$cfg);
	%{$target} = map { $_ => $cfg->param($_) } $cfg->param();
	return 1;
}

1;
