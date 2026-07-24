package LoxBerry::JSON;
use strict;
use warnings;
use JSON::PP;

# Minimal CI stub for LoxBerry::JSON. It implements the parts the plugin uses
# (new / open / write / filename) on top of JSON::PP so syntax checks and unit
# tests run on a plain Perl install without LoxBerry. The real module adds
# locking, write-on-close and error reporting that are not reproduced here.

sub new { return bless {}, ref($_[0]) || $_[0]; }

sub open
{
	my ($self, %params) = @_;
	my $filename = $params{filename};
	die "LoxBerry::JSON->open: Parameter filename is empty.\n" if (!defined($filename) || $filename eq "");
	$self->{filename} = $filename;
	$self->{readonly} = $params{readonly};
	if (!-e $filename) {
		$self->{jsonobj} = {};
		return $self->{jsonobj};
	}
	CORE::open(my $fh, "<", $filename) or die "LoxBerry::JSON->open: cannot read $filename\n";
	local $/;
	my $content = <$fh>;
	CORE::close($fh);
	$content = "{}" if (!defined($content) || $content !~ /\S/);
	$self->{jsonobj} = JSON::PP->new->utf8->relaxed(1)->decode($content);
	return $self->{jsonobj};
}

sub write
{
	my ($self) = @_;
	return if ($self->{readonly});
	return if (!defined($self->{filename}) || !defined($self->{jsonobj}));
	CORE::open(my $fh, ">", $self->{filename}) or return;
	print $fh JSON::PP->new->utf8->pretty->canonical->encode($self->{jsonobj});
	CORE::close($fh);
	return 1;
}

sub filename { return $_[0]->{filename}; }

1;
