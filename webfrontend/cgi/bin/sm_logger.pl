#!/usr/bin/perl

# Copyright 2017 Michael Schlenstedt, michael@loxberry.de
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

################################
### Moduls
################################
use Device::SerialPort;
use Getopt::Long;
use File::HomeDir;
use Cwd 'abs_path';
use DateTime;
#use DateTime::TimeZone;
#use warnings;
#use strict;

################################
### Configuration
################################

### Defaults
our $verbose = 0;
our $device = "";
our $serial = "";
our $protocol = "";

GetOptions (    "verbose"          => \$verbose,
                "device=s"         => \$device,
                "protocol=s"       => \$protocol,
                "parse=s"          => \$parse,
                "handshake=s"      => \$handshake,
                "baudrate=i"       => \$baudrate,
                "startbaudrate=i"  => \$startbaudrate,
                "timeout=i"        => \$timeout,
                "delay=i"          => \$delay,
                "databits=i"       => \$databits,
                "stopbits=i"       => \$stopbits,
                "parity=s"         => \$parity,
                "protocol=s"       => \$protocol,
                "help"             => \$help,
);

### Usage
if ( $help ) {
	print "Usage: $0 --device TTYDEVICE [--protocol PROTOCOL] [--startbaudrate STARTBAUDRAT] [--baudrate BAUDRATE] [--timeout TIMEOUT] \n";
	print "       [--delay DELAY} [--handshake HANDSHAKE] [--databits DATABITS] [--stopbits STOPBITS] [--parity PARITY] [--help] [--verbose]\n";
	print "       [--help] [--verbose] [--parse DUMPFILE]\n";
	exit;
}

### Debugging?
if ( !$verbose ) {
	$verbose = 0;
} else {
	$verbose = 1;
}

### Serieller Port
if ( (!$device || !-e $device) && !$parse ) {
	print "Please use --device to specify TTY device. Use --help to get help.\n";
	exit;
}
if ( $device !~ /usb-Silicon_Labs_CP2104_USB_to_UART_Bridge_Controller/  && !$parse ) {
	print "Your serial device seems not to be support.\n";
	exit;
}

### Serial of I/R Head
if ( !$parse ) {
	$serial	= $device;
	$serial	=~ s/([\n])//g;
	$serial	=~ s%/dev/serial/by-id/usb-Silicon_Labs_CP2104_USB_to_UART_Bridge_Controller_%%g;
	$serial	=~ s%-if00-port0%%g;
} else {
	$serial	= $parse;
	$serial	=~ s/([\n])//g;
	$serial	=~ s%\.dump%%g;
}

### Figure out in which subfolder we are installed
our $psubfolder = abs_path($0);
$psubfolder =~ s/(.*)\/(.*)\/bin\/(.*)$/$2/g;

# Create temp folder if not already exist
if (!-d "/var/run/shm/$psubfolder") {
	system("mkdir -p /var/run/shm/$psubfolder > /dev/null 2>&1");
}
# Check for temporary log folder
if (!-e "$installfolder/log/plugins/$psubfolder/shm") {
	system("ln -s /var/run/shm/$psubfolder  $installfolder/log/plugins/$psubfolder/shm > /dev/null 2>&1");
}

# Clear Log
system("rm /var/run/shm/$psubfolder/$serial\.log > /dev/null 2>&1");
if ( !$parse ) {
	system("rm /var/run/shm/$psubfolder/$serial\.dump > /dev/null 2>&1");
}

################################
### Determine which protocol to use
################################

if ( $protocol eq "genericd0" ) {

	### Defaults
	our $baudrate = 300 if !$baudrate;
	our $startbaudrate = 300 if !$startbaudrate;
	our $databits = 7 if !$databits;
	our $stopbits = 1 if !$stopbits;
	our $parity = "even" if !$parity;
	our $handshake = "none" if !$handshake;
	our $timeout = "120" if !$timeout;
	our $delay = "2" if !$delay;

	&PROTO_GENERICD0;
}

elsif ( $protocol eq "iskra173d0" ) {

	### Defaults
	our $baudrate = 9600 if !$baudrate;
	our $startbaudrate = 300 if !$startbaudrate;
	our $databits = 7 if !$databits;
	our $stopbits = 1 if !$stopbits;
	our $parity = "even" if !$parity;
	our $handshake = "none" if !$handshake;
	our $timeout = "10" if !$timeout;
	our $delay = "2" if !$delay;
	our $precommand = "";
	our $postcommand = "";

	&PROTO_GENERICD0;
}

elsif ( $protocol eq "iskra174d0" ) {

	### Defaults
	our $baudrate = 9600 if !$baudrate;
	our $startbaudrate = 300 if !$startbaudrate;
	our $databits = 7 if !$databits;
	our $stopbits = 1 if !$stopbits;
	our $parity = "even" if !$parity;
	our $handshake = "none" if !$handshake;
	our $timeout = "10" if !$timeout;
	our $delay = "2" if !$delay;
	our $precommand = "";
	our $postcommand = "";

	&PROTO_GENERICD0;
}

elsif ( $protocol eq "iskra175d0" ) {

	### Defaults
	our $baudrate = 9600 if !$baudrate;
	our $startbaudrate = 300 if !$startbaudrate;
	our $databits = 7 if !$databits;
	our $stopbits = 1 if !$stopbits;
	our $parity = "even" if !$parity;
	our $handshake = "none" if !$handshake;
	our $timeout = "10" if !$timeout;
	our $delay = "2" if !$delay;
	our $precommand = "";
	our $postcommand = "";

	&PROTO_GENERICD0;
}

elsif ( $protocol eq "siemenstd3511d0" ) {

	### Defaults
	our $baudrate = 9600 if !$baudrate;
	our $startbaudrate = 300 if !$startbaudrate;
	our $databits = 7 if !$databits;
	our $stopbits = 1 if !$stopbits;
	our $parity = "even" if !$parity;
	our $handshake = "none" if !$handshake;
	our $timeout = "10" if !$timeout;
	our $delay = "2" if !$delay;
	our $precommand = "303531";
	our $postcommand = "";

	&PROTO_GENERICD0;
}

elsif ( $protocol eq "pafal20ec3grd0" ) {

	### Defaults
	our $baudrate = 300 if !$baudrate;
	our $startbaudrate = 300 if !$startbaudrate;
	our $databits = 7 if !$databits;
	our $stopbits = 1 if !$stopbits;
	our $parity = "even" if !$parity;
	our $handshake = "none" if !$handshake;
	our $timeout = "120" if !$timeout;
	our $delay = "2" if !$delay;
	our $precommand = "";
	our $postcommand = "";

	&PROTO_GENERICD0;
}

elsif ( $protocol eq "iskra681sml" ) {

	### Defaults
	our $baudrate = 9600 if !$baudrate;
	our $startbaudrate = 9600 if !$startbaudrate;
	our $databits = 8 if !$databits;
	our $stopbits = 1 if !$stopbits;
	our $parity = "none" if !$parity;
	our $handshake = "none" if !$handshake;
	our $timeout = "60" if !$timeout;
	our $delay = "2" if !$delay;
	our $precommand = "";
	our $postcommand = "";

	&PROTO_GENERICSML;
}

else {
	$verbose =1;
	&LOG ("No known protocol specified. Try --help to get an overview of possible options.", "FAIL");
	exit;
}

################################
### Output
################################

&LOG("All data written to /var/run/shm/$psubfolder/$serial.xxxx");

exit;


################################
###
### Subroutines
###
################################


################################
### Sub GENERIC D0 Protocol
################################

sub PROTO_GENERICD0
{

	if ( !$parse ) {

		&LOG ("Initial Baudrate: $startbaudrate", "INFO");
		&LOG ("Max Baudrate: $baudrate", "INFO");
		&LOG ("Protocol: $protocol", "INFO");
		&LOG ("Timeout: $timeout", "INFO");
		&LOG ("Delay: $delay", "INFO");

		### Open serial port
		&INITIALIZE_PORT();

		### Sending Starting Sequenze
		&D0_STARTINGSEQUENZE("2f3f210d0a");

		### Changing Baudrate
		&D0_CHANGEBAUDRATE("$baudrate", "$precommand", "$postcommand");

		### Read serial device
		&READ_SERIAL();

	} else {

		&LOG ("Parsing previous dump file $parse", "INFO");

	}

	&PARSE_DUMP("D0");

	return;

}

################################
### Sub GENERIC SML Protocol
################################

sub PROTO_GENERICSML
{

	if ( !$parse ) {

		&LOG ("Initial Baudrate: $startbaudrate", "INFO");
		&LOG ("Max Baudrate: $baudrate", "INFO");
		&LOG ("Protocol: $protocol", "INFO");
		&LOG ("Timeout: $timeout", "INFO");
		&LOG ("Delay: $delay", "INFO");

		### Open serial port
		&INITIALIZE_PORT();

		### Read serial device
		&READ_SERIAL("HEX");

	} else {

		&LOG ("Parsing previous dump file $parse", "INFO");

	}

	&PARSE_DUMP("SML");

	return;

}

################################
### SUB: D0 Send Starting Sequenze
################################

sub D0_STARTINGSEQUENZE
{

	### Debug output
	&LOG ("Sending D0 Starting Sequence", "INFO");

	### Send Initial Sequenze
	my $data = shift; # http://wiki.selfhtml.org/wiki/Perl/Subroutinen
	if ( !$data) { $data = "2f3f210d0a" }; # Std. if empty: Send as HEX "/?!<CR><LF>"

	my $request = pack('H*',$data);
	my $requestlog = $request;
	$requestlog =~ s/\r\n\z//; # chomp doesn't work here...
	my $num_out = $port->write($request);

	### Debug
  	&LOG ("Send: $requestlog", "INFO");
	if ( !$num_out ) {
		$verbose = 1;
		&LOG ("Write failed.", "FAIL");
		exit;
	}
	if ( $num_out ne length($request) ) {
		$verbose = 1;
		&LOG ("Write incomplete.", "FAIL");
		exit;
	}
	&LOG ("$num_out Bytes written.", "INFO");

	return();
}

################################
### SUB: D0 Change Baudrate
################################

sub D0_CHANGEBAUDRATE
{

	our $baudratetarget = shift;
	our $precmd = shift; # http://wiki.selfhtml.org/wiki/Perl/Subroutinen
	our $postcmd = shift; # http://wiki.selfhtml.org/wiki/Perl/Subroutinen

	### Wait for Meter
	sleep $delay;

	### Change Baudrate
	### 303030 (Ascii: 000) = 300baud
	### 303430 (Ascii: 040) = 4800baud
	### 303530 (Ascii: 050) = 9600baud
	### 303530 (Ascii: 060) = 19200baud
	if ( $baudratetarget eq "300" ) {
		our $baudchange = 1;
		our $baudrateh = "303030";
	}
	elsif ( $baudratetarget eq "4800" ) {
		our $baudchange = 1;
		our $baudrateh = "303430";
	}
	elsif ( $baudratetarget eq "9600" ) {
 	 	our $baudchange = 1;
  		our $baudrateh = "303530";
	}
	elsif ( $baudratetarget eq "19200" ) {
 	 	our $baudchange = 1;
  		our $baudrateh = "303630";
	} else {
		&LOG ("The baudrate $baudratetarget is not implemented by this protocol. Using default baudrate: 300 baud.", "WARNING");
		our $baudchange = 0;
		our $baudrate = 300;
	}

	### If we should change the baudrate, send ACK and sequence in hex
	if ($baudchange == 1){

		### Debug
		&LOG ("Changing Baudrate to $baudratetarget", "INFO");

		# Pre-Command to change Baudrate
		if ( $precmd ) {
  			my $data3="06".$precmd."0d0a"; # ACK and precmd in HEX, z. B. "<ACK>040<CR><LF>"
	  		my $precommand = pack('H*',$data3);
			my $precommandlog = $precommand;
			$precommandlog =~ s/\r\n\z//; # chomp doesn't work here...
  			my $num_out3 = $port->write($precommand);
	
			### Debug
  			&LOG ("Send: $precommandlog", "INFO");
			if ( !$num_out3 ) {
				$verbose = 1;
				&LOG ("Write failed.", "FAIL");
				exit;
			}
			if ( $num_out3 ne length($precommand) ) {
				$verbose = 1;
				&LOG ("Write incomplete.", "FAIL");
				exit;
			}
			&LOG ("$num_out3 Bytes written.", "INFO");
		}

		# Command to change Baudrate
  		my $data2="06".$baudrateh."0d0a"; # ACK and new baudrate in HEX, z. B. "<ACK>040<CR><LF>"
  		my $baudwechsel = pack('H*',$data2);
		my $baudwechsellog = $baudwechsel;
		$baudwechsellog =~ s/\r\n\z//; # chomp doesn't work here...
  		my $num_out2 = $port->write($baudwechsel);

		### Debug
  		&LOG ("Send: $baudwechsellog", "INFO");
		if ( !$num_out2 ) {
			$verbose = 1;
			&LOG ("Write failed.", "FAIL");
			exit;
		}
		if ( $num_out2 ne length($baudwechsel) ) {
			$verbose = 1;
			&LOG ("Write incomplete.", "FAIL");
			exit;
		}
		&LOG ("$num_out2 Bytes written.", "INFO");

		# Post-Command to change Baudrate
		if ( $postcmd ) {
	  		my $baudwechsel = pack('H*',$postcmd);
			my $baudwechsellog = $baudwechsel;
			$baudwechsellog =~ s/\r\n\z//; # chomp doesn't work here...
  			my $num_out2 = $port->write($baudwechsel);
	
			### Debug
  			&LOG ("Send: $baudwechsellog", "INFO");
			if ( !$num_out2 ) {
				$verbose = 1;
				&LOG ("Write failed.", "FAIL");
				exit;
			}
			if ( $num_out2 ne length($baudwechsel) ) {
				$verbose = 1;
				&LOG ("Write incomplete.", "FAIL");
				exit;
			}
			&LOG ("$num_out2 Bytes written.", "INFO");
		}

		### Activate new baudrate on device
		sleep 1;
		$port->baudrate($baudratetarget)      || die "Fail setting baudrate. Giving up.\n";

	}

	return();

}

################################
### SUB: Initialize Serial Port
################################

sub INITIALIZE_PORT
{

	### Debug output
	&LOG ("Setting up port $device: Baudrate:$baudrate/$startbaudrate Databits:$databits Stopbits:$stopbits Parity:$parity Handshake:$handshake", "INFO");

	### Open Port
	our $port = new Device::SerialPort($device) || die "Can't open $device: $!. Giving up.\n";
	$port->baudrate($startbaudrate);
	$port->databits($databits);
	$port->stopbits($stopbits);
	$port->parity("$parity");
	$port->handshake("$handshake");
	$port->dtr_active(1);
	$port->rts_active(1);
	$port->read_char_time(0); # 0 seconds for each character
	$port->read_const_time(1000); # 1 second per unfulfilled "read" call
	$port->write_settings || die "Fail write settings to device. Giving up.\n";
	$port->purge_all();

	return();

}

################################
### SUB: Read buffer from serial device
################################

sub READ_SERIAL
{

	our $hex = shift;

	### Read answer of meter until end
	local $SIG{ALRM} = sub { die };
	eval {
  		alarm($timeout);
		our $count = 5;
		our $buffer = "";
		while ($count > 0) {
			my ($count,$saw) = $port->read(255); # Read 255 signs each
  			if ($count > 0) {
				$buffer .= $saw;
				### Debug: print received signs
				if ($verbose){
					if ($hex eq "HEX"){
						$x = uc(unpack('H*',$saw)); # nach hex wandeln
						print $x;
					} else {
						print $saw;
					}
				}
			} else {
				$count--;
			}
		}
	};
	alarm(0);

	if ($verbose){
		print "\n";
	}

	# Close port
	$port->close;

	# Save output to file and convert line endings
	&LOG ("Save raw buffer to /var/run/shm/$psubfolder/$serial\.dump", "INFO");
	if ($hex eq "HEX"){
		$bufferx = uc(unpack('H*',$buffer)); # nach hex wandeln
	}
	open(F,">>/var/run/shm/$psubfolder/$serial\.dump");
		if ($hex eq "HEX"){
			print F $bufferx;
		} else {
			print F $buffer;
		}
	close (F);
	system("/usr/bin/dos2unix -f /var/run/shm/$psubfolder/$serial\.dump > /dev/null 2>&1");

	if ($hex eq "HEX"){
		return($bufferx);
	} else {
		return($buffer);
	}

}

################################
### SUB: Parse D0
################################

sub PARSE_DUMP
{

	our $proto = shift;

	if ($proto eq "SML") {
		&LOG ("Parse /var/run/shm/$psubfolder/$serial\.dump as SML-Protocol.", "INFO");
		our $buffer = `php ./sml_parser.php /var/run/shm/$psubfolder/$serial\.dump`;
	} else {
		&LOG ("Parse /var/run/shm/$psubfolder/$serial\.dump as D0-Protocol.", "INFO");
		open(F,"</var/run/shm/$psubfolder/$serial\.dump");
			our $buffer = do { local $/; <F> };
		close (F);
	}

	### Energy consumption: Readings  (OBIS 1.8.x*255)
	($readingconsT0) = $buffer =~ /1\.8\.0\*[255|00]+\(([\d\.]+)/;
	($readingconsT1) = $buffer =~ /1\.8\.1\*[255|00]+\(([\d\.]+)/;
	($readingconsT2) = $buffer =~ /1\.8\.2\*[255|00]+\(([\d\.]+)/;
	($readingconsT3) = $buffer =~ /1\.8\.3\*[255|00]+\(([\d\.]+)/;
	($readingconsT4) = $buffer =~ /1\.8\.4\*[255|00]+\(([\d\.]+)/;
	($readingconsT5) = $buffer =~ /1\.8\.5\*[255|00]+\(([\d\.]+)/;
	($readingconsT6) = $buffer =~ /1\.8\.6\*[255|00]+\(([\d\.]+)/;
	($readingconsT7) = $buffer =~ /1\.8\.7\*[255|00]+\(([\d\.]+)/;
	($readingconsT8) = $buffer =~ /1\.8\.8\*[255|00]+\(([\d\.]+)/;
	($readingconsT9) = $buffer =~ /1\.8\.9\*[255|00]+\(([\d\.]+)/;

	### Energy delivery: Readings  (OBIS 2.8.x*255)
	($readingdelT0) = $buffer =~ /2\.8\.0\*[255|00]+\(([\d\.]+)/;
	($readingdelT1) = $buffer =~ /2\.8\.1\*[255|00]+\(([\d\.]+)/;
	($readingdelT2) = $buffer =~ /2\.8\.2\*[255|00]+\(([\d\.]+)/;
	($readingdelT3) = $buffer =~ /2\.8\.3\*[255|00]+\(([\d\.]+)/;
	($readingdelT4) = $buffer =~ /2\.8\.4\*[255|00]+\(([\d\.]+)/;
	($readingdelT5) = $buffer =~ /2\.8\.5\*[255|00]+\(([\d\.]+)/;
	($readingdelT6) = $buffer =~ /2\.8\.6\*[255|00]+\(([\d\.]+)/;
	($readingdelT7) = $buffer =~ /2\.8\.7\*[255|00]+\(([\d\.]+)/;
	($readingdelT8) = $buffer =~ /2\.8\.8\*[255|00]+\(([\d\.]+)/;
	($readingdelT9) = $buffer =~ /2\.8\.9\*[255|00]+\(([\d\.]+)/;

	### Energy consumption: Power  (OBIS mixture - no standard?)
	($power1) = $buffer =~ /1\.7\.0\*[255|00]+\(([\d\.]+)/;
	($power2) = $buffer =~ /2\.7\.0\*[255|00]+\(([\d\.]+)/;
	($power3) = $buffer =~ /15\.7\.0\*[255|00]+\(([\d\.]+)/;
	($power4) = $buffer =~ /16\.7\.0\*[255|00]+\(([\d\.]+)/;

	### Calculate Avg. Power
	my $powercalccons = &CALCULATE_POWER("$readingconsT0","CONS");
	my $powercalcdel = &CALCULATE_POWER("$readingdelT0","DEL");

	# Today's date for LOGfile
	(my $sec,my $min,my $hour,my $mday,my $mon,my $year,my $wday,my $yday,my $isdst) = localtime();
	$year = $year+1900;
	$mon = $mon+1;
	$mon = sprintf("%02d", $mon);
	$mday = sprintf("%02d", $mday);
	$hour = sprintf("%02d", $hour);
	$min = sprintf("%02d", $min);
	$sec = sprintf("%02d", $sec);

	my $datereadable = "$year-$mon-$mday $hour:$min:$sec";

	# Loxone Epoche Date
	my $dt = DateTime->new( year   => $year, month  => $mon, day    => $mday, hour   => $hour, minute => $min, 
				second => $sec, nanosecond => 500000000, time_zone => 'local' );
	my $epoch_time = $dt->epoch;
#	my $tz = DateTime::TimeZone->new( name => 'local' );
#	my $offset = $tz->offset_for_datetime($dt);

	# Date Reference: Convert into Loxone Epoche (1.1.2009)
	my $dateref = DateTime->new(
		year      => 2009,
		month     => 1,
		day       => 1,
	);
	my $epoche_time_lox = $epoch_time - $dateref->epoch();

#	print "Epoche Date: $epoch_time\n";
#	print "Epoche Date Lox: $epoche_time_lox\n";
#	print "Offset: $offset\n";

	### Save to data file
	&LOG ("Save Meter data to /var/run/shm/$psubfolder/$serial\.data.", "INFO");
	open(F,">/var/run/shm/$psubfolder/$serial\.data");
		print F "Last_Update: $datereadable\n";
		print F "Last_UpdateLoxEpoche: $epoche_time_lox\n";
		print F "Consumption_Total_OBIS_1.8.0: $readingconsT0\n";
		print F "Consumption_Tarif1_OBIS_1.8.1: $readingconsT1\n";
		print F "Consumption_Tarif2_OBIS_1.8.2: $readingconsT2\n";
		print F "Consumption_Tarif3_OBIS_1.8.3: $readingconsT3\n";
		print F "Consumption_Tarif4_OBIS_1.8.4: $readingconsT4\n";
		print F "Consumption_Tarif5_OBIS_1.8.5: $readingconsT5\n";
		print F "Consumption_Tarif6_OBIS_1.8.6: $readingconsT6\n";
		print F "Consumption_Tarif7_OBIS_1.8.7: $readingconsT7\n";
		print F "Consumption_Tarif8_OBIS_1.8.8: $readingconsT8\n";
		print F "Consumption_Tarif9_OBIS_1.8.9: $readingconsT9\n";
		print F "Consumption_CalculatedPower_OBIS_1.99.0: $powercalccons\n";
		print F "Consumption_Power_OBIS_1.7.0: $power1\n";
		print F "Delivery_Total_OBIS_2.8.0: $readingdelT0\n";
		print F "Delivery_Tarif1_OBIS_2.8.1: $readingdelT1\n";
		print F "Delivery_Tarif2_OBIS_2.8.2: $readingdelT2\n";
		print F "Delivery_Tarif3_OBIS_2.8.3: $readingdelT3\n";
		print F "Delivery_Tarif4_OBIS_2.8.4: $readingdelT4\n";
		print F "Delivery_Tarif5_OBIS_2.8.5: $readingdelT5\n";
		print F "Delivery_Tarif6_OBIS_2.8.6: $readingdelT6\n";
		print F "Delivery_Tarif7_OBIS_2.8.7: $readingdelT7\n";
		print F "Delivery_Tarif8_OBIS_2.8.8: $readingdelT8\n";
		print F "Delivery_Tarif9_OBIS_2.8.9: $readingdelT9\n";
		print F "Delivery_CalculatedPower_OBIS_2.99.0: $powercalcdel\n";
		print F "Delivery_Power_OBIS_2.7.0: $power2\n";
		print F "Total_Power_OBIS_15.7.0: $power3\n";
		print F "Total_Power_OBIS_16.7.0: $power4\n";
	close (F);

	return();

}

################################
### SUB: Calculate Power
################################

sub CALCULATE_POWER
{

	our $reading = shift;
	our $direction = lc shift;
	&LOG ("Calculate average power for $direction.", "INFO");

	$reading = sprintf("%.3f", $reading);
	if ( !$reading ){
		&LOG ("No current meter reading. Calculation not possible,", "WARNING");
		return (0);
	}

	# Calculate power - the ISKRA MT174 doesn't provide power
	$now = time;
	if ( -e "/var/run/shm/$psubfolder/$serial\.last$direction" ) {
		open(F,"</var/run/shm/$psubfolder/$serial\.last$direction");
		@lines = <F>;
		foreach (@lines){
			s/[\n\r]//g;
			@fields  = split(/\|/);
			$lasttime = @fields[0];
			$lastreading = @fields[1];
		}
		close(F);
		if ( $reading < $lastreading ) {
			$lastreading = $reading;
		}
		$period = ($now - $lasttime) / 3600;
		$energy = $reading - $lastreading;
		$power = $energy / $period;
	} else {
		&LOG ("No last meter reading available. Calculation not possible,", "WARNING");
		system("touch /var/run/shm/$psubfolder/$serial\.last$direction > /dev/null 2>&1");
		$period = 0;
		$energy = 0;
		$power = 0;
	}

	### Round
	$energy = sprintf("%.4f", $energy);
	$power = sprintf("%.4f", $power);
	$period = sprintf("%.4f", $period);

	### Debug output
	&LOG ("Last Reading: $lastreading. Saved before: $period hours. Consumption: $energy. Avg. Power: $power,", "INFO");

	### Zaehlerstand und Leistung speichern
	if ( $reading > 0 ) {
		open(F,">/var/run/shm/$psubfolder/$serial\.last$direction");
			print F "$now|$reading\n";
		close(F);
	}

	return ($power);

}


################################
### SUB: Log
################################

sub LOG
{

	my $message	= shift; # http://wiki.selfhtml.org/wiki/Perl/Subroutinen
	my $type	= uc shift; # http://wiki.selfhtml.org/wiki/Perl/Subroutinen
	if ( !$type ) { $type = "INFO" };

	if ($verbose){
		print "$message\n";
	}

	# Today's date for LOGfile
	(my $sec,my $min,my $hour,my $mday,my $mon,my $year,my $wday,my $yday,my $isdst) = localtime();
	$year = $year+1900;
	$mon = $mon+1;
	$mon = sprintf("%02d", $mon);
	$mday = sprintf("%02d", $mday);
	$hour = sprintf("%02d", $hour);
	$min = sprintf("%02d", $min);
	$sec = sprintf("%02d", $sec);

	# Logfile
	open(F,">>/var/run/shm/$psubfolder/$serial\.log");
		print F "$year-$mon-$mday $hour:$min:$sec <$type> $message\n";
	close (F);

  	return();

}

