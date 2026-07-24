package SmartMeterVZLoggerChannels;

use strict;
use warnings;
use Digest::MD5 qw(md5_hex);
use Exporter qw(import);
use JSON::PP;

our @EXPORT_OK = qw(
	parse_obis compose_obis normalize_obis default_output_key valid_output_key output_key_format stable_uuid
	read_json write_json_atomic load_catalog lookup_obis
	new_document migrate_legacy_meter validate_document localize_validation_errors native_channel
	output_order_mapping ordered_output_names
);

sub output_order_mapping
{
	my ($mapping) = @_;
	my %order;
	foreach my $uuid (sort keys %{ref($mapping) eq "HASH" ? $mapping : {}}) {
		my $entry = $mapping->{$uuid};
		next if (ref($entry) ne "HASH");
		my $serial = $entry->{serial};
		my $index = $entry->{channel_index};
		next if (!defined($serial) || ref($serial) || $serial eq "");
		next if (!defined($index) || ref($index) || $index !~ /\A\d+\z/);

		my $name = $entry->{name};
		if (defined($name) && !ref($name) && $name ne "") {
			$order{$serial}->{$name} = { channel_index => int($index), kind => 0 };
		}
	}
	return \%order;
}

sub ordered_output_names
{
	my ($values, $order) = @_;
	$values = {} if (ref($values) ne "HASH");
	$order = {} if (ref($order) ne "HASH");
	my %timestamp_rank = (Last_Update => 0, Last_UpdateLoxEpoche => 1);
	return sort {
		my $a_timestamp = exists($timestamp_rank{$a}) ? $timestamp_rank{$a} : undef;
		my $b_timestamp = exists($timestamp_rank{$b}) ? $timestamp_rank{$b} : undef;
		defined($a_timestamp) || defined($b_timestamp)
			? (defined($a_timestamp) && defined($b_timestamp)
				? $a_timestamp <=> $b_timestamp
				: defined($a_timestamp) ? -1 : 1)
			: _compare_channel_output($a, $b, $order);
	} keys %$values;
}

sub _compare_channel_output
{
	my ($a, $b, $order) = @_;
	my $a_order = ref($order->{$a}) eq "HASH" ? $order->{$a} : undef;
	my $b_order = ref($order->{$b}) eq "HASH" ? $order->{$b} : undef;
	if ($a_order && $b_order) {
		return $a_order->{channel_index} <=> $b_order->{channel_index}
			|| ($a_order->{kind} || 0) <=> ($b_order->{kind} || 0)
			|| lc($a) cmp lc($b)
			|| $a cmp $b;
	}
	return -1 if ($a_order);
	return 1 if ($b_order);
	return lc($a) cmp lc($b) || $a cmp $b;
}

sub stable_uuid
{
	my ($seed) = @_;
	my $hex = md5_hex(defined($seed) ? $seed : "");
	# Keep the exact legacy layout so the first migrated channel retains the UUID
	# previously generated from plugin, reader, and identifier.
	return join("-", substr($hex, 0, 8), substr($hex, 8, 4), substr($hex, 12, 4), substr($hex, 16, 4), substr($hex, 20, 12));
}

sub parse_obis
{
	my ($value) = @_;
	return undef if (!defined($value) || ref($value));
	$value =~ s/^\s+|\s+$//g;
	return undef if ($value !~ /\A(?:(\d+)-(\d+):)?([A-Za-z0-9]+)\.(\d+)\.(\d+)(?:\*(\d+))?\z/);
	my ($a, $b, $c, $d, $e, $f) = ($1, $2, $3, $4, $5, $6);
	return undef if (defined($f) && ($f > 255));
	$f = undef if (defined($f) && $f == 255);
	return {
		a => defined($a) ? int($a) : undef,
		b => defined($b) ? int($b) : undef,
		c => $c =~ /\A\d+\z/ ? int($c) : $c,
		d => int($d), e => int($e), f => defined($f) ? int($f) : undef,
		base => (defined($a) ? "$a-$b:" : "") . "$c.$d.$e",
	};
}

sub compose_obis
{
	my ($base, $storage) = @_;
	my $parsed = parse_obis($base);
	return "" if (!$parsed);
	$storage = undef if (!defined($storage) || $storage eq "" || $storage eq "255");
	return "" if (defined($storage) && $storage !~ /\A\d+\z/);
	return "" if (defined($storage) && ($storage < 0 || $storage > 254));
	return $parsed->{base} . (defined($storage) ? "*$storage" : "");
}

sub normalize_obis
{
	my ($value) = @_;
	my $parsed = parse_obis($value);
	return "" if (!$parsed);
	return compose_obis($parsed->{base}, $parsed->{f});
}

sub default_output_key
{
	my ($identifier, $catalog) = @_;
	my $parsed = parse_obis($identifier);
	return "Value_OBIS_Unknown" if (!$parsed);
	my $info = ref($catalog) eq "HASH" ? lookup_obis($catalog, $identifier, "en") : {};
	my $name = $info->{output_name} || ($info->{known} ? $info->{short} : "Unknown") || "Unknown";
	$name =~ s/\s+/_/g;
	$name =~ s/[^A-Za-z0-9_]+/_/g;
	$name =~ s/^_+|_+$//g;
	$name = "Value" if ($name eq "");
	my $short_obis = join(".", $parsed->{c}, $parsed->{d}, $parsed->{e});
	$short_obis .= "*$parsed->{f}" if (defined($parsed->{f}));
	my $suffix = "_OBIS_$short_obis";
	my $available = 64 - length($suffix);
	return substr("Value" . $suffix, 0, 64) if ($available < 1);
	$name = substr($name, 0, $available) if ($available >= 1 && length($name) > $available);
	$name =~ s/_+$//;
	return $name . $suffix;
}

sub valid_output_key
{
	my ($key) = @_;
	# The key becomes the MQTT topic of the channel, so the MQTT wildcards
	# '#' and '+' are not allowed. '/' stays valid as a topic separator.
	return defined($key) && !ref($key) && $key =~ /\A[A-Za-z0-9 _|()\[\]\/\'%\$!.*\-]{1,64}\z/;
}

sub output_key_format
{
	return "1-64 characters; allowed: letters, digits, spaces, underscore, | ( ) [ ] / ' % \$ ! . * -";
}

sub read_json
{
	my ($file) = @_;
	return undef if (!$file || !-e $file || !open(my $fh, "<", $file));
	local $/;
	my $text = <$fh>;
	close($fh);
	my $value = eval { JSON::PP->new->utf8->decode($text || "") };
	return $@ ? undef : $value;
}

sub write_json_atomic
{
	my ($file, $value) = @_;
	my $tmp = "$file.$$";
	open(my $fh, ">", $tmp) or die "Could not write $tmp: $!\n";
	print $fh JSON::PP->new->utf8->canonical->pretty->encode($value);
	close($fh) or die "Could not close $tmp: $!\n";
	chmod(0600, $tmp) or die "Could not protect $tmp: $!\n";
	rename($tmp, $file) or die "Could not replace $file: $!\n";
}

sub new_document
{
	return { version => 1, meters => {} };
}

sub migrate_legacy_meter
{
	my ($document, $serial, $plugin_id, $discovered, $selected, $custom, $catalog) = @_;
	$document ||= new_document();
	$document->{meters} ||= {};
	return $document->{meters}->{$serial} if (ref($document->{meters}->{$serial}) eq "ARRAY");
	my %selected = map { normalize_obis($_) => 1 } @{ref($selected) eq "ARRAY" ? $selected : []};
	my $selection_explicit = ref($selected) eq "ARRAY";
	my @definitions;
	my %seen;
	foreach my $item (@{ref($discovered) eq "ARRAY" ? $discovered : []}) {
		my $raw = ref($item) eq "HASH" ? $item->{identifier} : $item;
		my $identifier = normalize_obis($raw);
		next if (!$identifier || $seen{$identifier}++);
		push @definitions, _legacy_definition($serial, $plugin_id, $identifier,
			$selection_explicit ? !!$selected{$identifier} : 1, "discovered", scalar(@definitions), $catalog);
	}
	foreach my $raw (@{ref($selected) eq "ARRAY" ? $selected : []}, @{ref($custom) eq "ARRAY" ? $custom : []}) {
		my $identifier = normalize_obis($raw);
		next if (!$identifier || $seen{$identifier}++);
		push @definitions, _legacy_definition($serial, $plugin_id, $identifier, 1,
			$selected{$identifier} ? "migrated" : "manual", scalar(@definitions), $catalog);
	}
	$document->{meters}->{$serial} = \@definitions;
	return \@definitions;
}

sub _legacy_definition
{
	my ($serial, $plugin_id, $identifier, $enabled, $origin, $index, $catalog) = @_;
	my $parsed = parse_obis($identifier);
	my $key = default_output_key($identifier, $catalog);
	return {
		uuid => stable_uuid("$plugin_id:$serial:$identifier"),
		enabled => $enabled ? JSON::PP::true : JSON::PP::false,
		origin => $origin,
		obis => $parsed->{base}, storage => $parsed->{f}, display_name => "",
		api => "null", aggmode => "none", duplicates => 0,
		api_options => { volkszaehler => {}, influxdb => {}, mysmartgrid => {} },
		plugin_output => { enabled => $enabled ? JSON::PP::true : JSON::PP::false, key => $key },
	};
}

sub load_catalog
{
	my ($file) = @_;
	my $catalog = read_json($file);
	return $catalog if (ref($catalog) eq "HASH" && ref($catalog->{entries}) eq "ARRAY");
	return { version => 1, sources => {}, entries => [], rules => [] };
}

sub lookup_obis
{
	my ($catalog, $identifier, $language) = @_;
	$language = ($language || "en") eq "de" ? "de" : "en";
	my $parsed = parse_obis($identifier);
	return { known => JSON::PP::false, short => $identifier || "Unknown OBIS", long => "The identifier is not a valid OBIS code." } if (!$parsed);
	my $full = compose_obis($parsed->{base}, $parsed->{f});
	my @candidates = ($full, $parsed->{base});
	foreach my $candidate (@candidates) {
		foreach my $entry (@{$catalog->{entries} || []}) {
			next if (($entry->{code} || "") ne $candidate);
			return _catalog_result($entry, $parsed, $language, "exact");
		}
	}
	foreach my $rule (sort { ($a->{priority} || 9999) <=> ($b->{priority} || 9999) } @{$catalog->{rules} || []}) {
		my $match = $rule->{match} || {};
		my $ok = 1;
		foreach my $group (qw(a b c d e)) {
			next if (!exists($match->{$group}));
			my $wanted = $match->{$group};
			my $actual = $parsed->{$group};
			$ok = 0 if (ref($wanted) eq "ARRAY" ? !grep { defined($actual) && "$_" eq "$actual" } @$wanted : !defined($actual) || "$wanted" ne "$actual");
		}
		return _catalog_result($rule, $parsed, $language, "rule") if ($ok);
	}
	my $groups = _groups_text($parsed, $language);
	return {
		known => JSON::PP::false,
		short => $language eq "de" ? "Unbekannter oder herstellerspezifischer OBIS-Code" : "Unknown or manufacturer-specific OBIS code",
		long => ($language eq "de" ? "Für diesen Code ist kein belegter Standardname hinterlegt. " : "No verified standard name is recorded for this code. ") . $groups,
		unit => "", category => "unknown", source => "", match => "fallback", groups => $parsed,
		warning => $language eq "de" ? "Die Bedeutung ist am Zählerhandbuch zu prüfen." : "Check the meter documentation for its meaning.",
	};
}

sub _catalog_result
{
	my ($entry, $parsed, $language, $kind) = @_;
	my $result = {
		known => JSON::PP::true,
		short => $entry->{short}->{$language} || $entry->{short}->{en} || $parsed->{base},
		long => $entry->{long}->{$language} || $entry->{long}->{en} || "",
		unit => $entry->{unit} || "", category => $entry->{category} || "",
		source => $entry->{source} || "", match => $kind, groups => $parsed,
		recommended_aggmode => $entry->{recommended_aggmode} || "none",
	};
	$result->{output_name} = $entry->{output_name} if (defined($entry->{output_name}) && !ref($entry->{output_name}));
	if (defined($parsed->{f})) {
		$result->{long} .= $language eq "de" ? " Speicher-/Abrechnungsindex: $parsed->{f}." : " Storage/billing index: $parsed->{f}.";
	}
	$result->{long} .= " " . _groups_text($parsed, $language);
	$result->{warning} = $entry->{limitations}->{$language} if (ref($entry->{limitations}) eq "HASH");
	return $result;
}

sub _groups_text
{
	my ($p, $language) = @_;
	my $prefix = $language eq "de" ? "Gruppen:" : "Groups:";
	my $a = defined($p->{a}) ? $p->{a} : ($language eq "de" ? "nicht angegeben" : "not specified");
	my $b = defined($p->{b}) ? $p->{b} : ($language eq "de" ? "nicht angegeben" : "not specified");
	my $f = defined($p->{f}) ? $p->{f} : ($language eq "de" ? "nicht angegeben" : "not specified");
	return "$prefix A=$a, B=$b, C=$p->{c}, D=$p->{d}, E=$p->{e}, F=$f.";
}

sub validate_document
{
	my ($document) = @_;
	my @errors;
	return ("Channel definitions must be a JSON object.") if (ref($document) ne "HASH");
	push @errors, "Unsupported channel-definition version." if (($document->{version} || 0) != 1);
	push @errors, "The meters member must be an object." if (ref($document->{meters}) ne "HASH");
	return @errors if (@errors);
	my %global_uuids;
	foreach my $serial (sort keys %{$document->{meters}}) {
		my $channels = $document->{meters}->{$serial};
		if (ref($channels) ne "ARRAY") { push @errors, "$serial: channels must be an array."; next; }
		my (%uuids, %keys);
		foreach my $channel (@$channels) {
			if (ref($channel) ne "HASH") { push @errors, "$serial: invalid channel entry."; next; }
			my $uuid = $channel->{uuid} || "";
			push @errors, "$serial: invalid channel UUID." if ($uuid !~ /\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/i);
			push @errors, "$serial: duplicate channel UUID $uuid." if ($uuid && $uuids{lc($uuid)}++);
			push @errors, "$serial: channel UUID $uuid is duplicated across meters." if ($uuid && $global_uuids{lc($uuid)}++);
			push @errors, "$serial/$uuid: enabled must be a JSON boolean." if (!is_json_boolean($channel->{enabled}));
			push @errors, "$serial/$uuid: invalid channel origin." if (($channel->{origin} || "") !~ /\A(?:discovered|manual|migrated)\z/);
			my $identifier = compose_obis($channel->{obis}, $channel->{storage});
			push @errors, "$serial/$uuid: invalid OBIS identifier." if (!$identifier);
			my $base = parse_obis($channel->{obis});
			push @errors, "$serial/$uuid: obis must contain the base code without *F." if ($base && $channel->{obis} ne $base->{base});
			my $options_valid = ref($channel->{api_options}) eq "HASH" &&
				!grep { ref($channel->{api_options}->{$_}) ne "HASH" } qw(volkszaehler influxdb mysmartgrid);
			push @errors, "$serial/$uuid: invalid API option blocks." if (!$options_valid);
			my $output_valid = ref($channel->{plugin_output}) eq "HASH";
			push @errors, "$serial/$uuid: invalid plugin output block." if (!$output_valid);
			push @errors, "$serial/$uuid: plugin output enabled must be a JSON boolean."
				if ($output_valid && !is_json_boolean($channel->{plugin_output}->{enabled}));
			push @errors, "$serial/$uuid: display name must be a string no longer than 128 characters."
				if (defined($channel->{display_name}) && (ref($channel->{display_name}) || length($channel->{display_name}) > 128));
			my $api = $channel->{api} || "null";
			push @errors, "$serial/$uuid: unsupported API $api." if ($api !~ /\A(?:null|volkszaehler|influxdb|mysmartgrid)\z/);
			my $agg = $channel->{aggmode} || "none";
			push @errors, "$serial/$uuid: invalid aggregation mode." if ($agg !~ /\A(?:none|avg|max|sum)\z/);
			push @errors, "$serial/$uuid: duplicates must be a non-negative integer."
				if (!is_nonnegative_integer($channel->{duplicates}));
			if ($channel->{enabled} && $output_valid && $channel->{plugin_output}->{enabled}) {
				my $key = $channel->{plugin_output}->{key} || "";
				push @errors, "$serial/$uuid: invalid output key (required format: " . output_key_format() . ")." if (!valid_output_key($key));
				push @errors, "$serial: duplicate output key $key." if ($key && $keys{lc($key)}++);
			}
			next if (!$channel->{enabled} || !$options_valid || $api !~ /\A(?:null|volkszaehler|influxdb|mysmartgrid)\z/);
			my $options = $channel->{api_options}->{$api} || {};
			my %allowed_options = (
				volkszaehler => { map { $_ => 1 } qw(middleware timeout) },
				influxdb => { map { $_ => 1 } qw(version host token organization username password database measurement_name tags timeout max_batch_inserts max_buffer_size send_uuid ssl_verifypeer) },
				mysmartgrid => { map { $_ => 1 } qw(middleware secretKey device type interval scaler timeout name) },
				null => {},
			);
			foreach my $field (keys %$options) {
				push @errors, "$serial/$uuid: unsupported $api option $field." if (!$allowed_options{$api}->{$field});
			}
			if ($api eq "volkszaehler") {
				push @errors, "$serial/$uuid: Volkszaehler middleware must be a valid HTTP(S) URL."
					if (!is_http_url($options->{middleware}));
			}
			if ($api eq "influxdb") {
				push @errors, "$serial/$uuid: InfluxDB host is required." if (!is_nonempty_scalar($options->{host}));
				my $version = defined($options->{version}) && $options->{version} ne "" ? "$options->{version}" : "";
				push @errors, "$serial/$uuid: InfluxDB version must be 1 or 2." if ($version ne "" && $version !~ /\A[12]\z/);
				push @errors, "$serial/$uuid: InfluxDB database/bucket is required for version $version."
					if ($version ne "" && !is_nonempty_scalar($options->{database}));
				push @errors, "$serial/$uuid: InfluxDB organization is required for version 2."
					if ($version eq "2" && !is_nonempty_scalar($options->{organization}));
				push @errors, "$serial/$uuid: InfluxDB token is required for version 2."
					if ($version eq "2" && !is_nonempty_scalar($options->{token}));
				push @errors, "$serial/$uuid: InfluxDB tags must be a JSON object."
					if (exists($options->{tags}) && $options->{tags} ne "" && !is_json_object_value($options->{tags}));
				foreach my $field (qw(send_uuid ssl_verifypeer)) {
					push @errors, "$serial/$uuid: InfluxDB $field must be a JSON boolean."
						if (exists($options->{$field}) && !is_json_boolean($options->{$field}));
				}
			}
			if ($api eq "mysmartgrid") {
				foreach my $field (grep { !($options->{$_} || "") } qw(middleware secretKey device type)) {
					push @errors, "$serial/$uuid: MySmartGrid $field is required.";
				}
				push @errors, "$serial/$uuid: MySmartGrid middleware must be a valid HTTP(S) URL."
					if (is_nonempty_scalar($options->{middleware}) && !is_http_url($options->{middleware}));
				push @errors, "$serial/$uuid: MySmartGrid type must be device or sensor."
					if (is_nonempty_scalar($options->{type}) && $options->{type} !~ /\A(?:device|sensor)\z/);
			}
			foreach my $field (qw(timeout max_batch_inserts max_buffer_size interval)) {
				next if (!exists($options->{$field}) || $options->{$field} eq "");
				push @errors, "$serial/$uuid: $api $field must be a non-negative integer."
					if (!is_nonnegative_integer($options->{$field}));
			}
			if (exists($options->{scaler}) && $options->{scaler} ne "") {
				push @errors, "$serial/$uuid: MySmartGrid scaler must be a number."
					if (ref($options->{scaler}) || $options->{scaler} !~ /\A-?\d+(?:\.\d+)?\z/);
			}
		}
	}
	return @errors;
}

sub _channel_phrase
{
	my ($phrases, $key, %values) = @_;
	my $text = ref($phrases) eq "HASH" && defined($phrases->{$key}) ? $phrases->{$key} : "";
	foreach my $name (keys %values) {
		my $value = defined($values{$name}) ? $values{$name} : "";
		$text =~ s/\{\Q$name\E\}/$value/g;
	}
	return $text;
}

sub _localize_validation_error
{
	my ($message, $phrases) = @_;
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_DOCUMENT') if ($message eq "Channel definitions must be a JSON object.");
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_VERSION') if ($message eq "Unsupported channel-definition version.");
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_METERS') if ($message eq "The meters member must be an object.");
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_ENTRY', path => $1) if ($message =~ /\A([^:]+): invalid channel entry\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_UUID', path => $1) if ($message =~ /\A([^:]+): invalid channel UUID\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_UUID_DUPLICATE', path => $1, uuid => $2) if ($message =~ /\A([^:]+): duplicate channel UUID (.+)\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_UUID_GLOBAL', path => $1, uuid => $2) if ($message =~ /\A([^:]+): channel UUID (.+) is duplicated across meters\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_ARRAY', path => "$1.channels") if ($message =~ /\A([^:]+): channels must be an array\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_BOOLEAN', path => $1, field => $2) if ($message =~ /\A([^:]+): (.+) must be a JSON boolean\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_ORIGIN', path => $1) if ($message =~ /\A([^:]+): invalid channel origin\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_OBIS', path => $1) if ($message =~ /\A([^:]+): invalid OBIS identifier\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_OBIS_BASE', path => $1) if ($message =~ /\A([^:]+): obis must contain the base code without \*F\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_API_BLOCKS', path => $1) if ($message =~ /\A([^:]+): invalid API option blocks\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_OUTPUT_BLOCK', path => $1) if ($message =~ /\A([^:]+): invalid plugin output block\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_DISPLAY_NAME', path => $1) if ($message =~ /\A([^:]+): display name must be a string no longer than 128 characters\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_API', path => $1, api => $2) if ($message =~ /\A([^:]+): unsupported API (.+)\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_AGGREGATION', path => $1) if ($message =~ /\A([^:]+): invalid aggregation mode\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_OUTPUT_KEY', path => $1, format => $2) if ($message =~ /\A([^:]+): invalid output key \(required format: (.+)\)\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_OUTPUT_DUPLICATE', path => $1, key => $2) if ($message =~ /\A([^:]+): duplicate output key (.+)\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_OPTION', path => $1, api => $2, field => $3) if ($message =~ /\A([^:]+): unsupported (\S+) option (\S+)\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_URL', path => $1, target => $2) if ($message =~ /\A([^:]+): (.+) must be a valid HTTP\(S\) URL\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_INFLUX_VERSION', path => $1) if ($message =~ /\A([^:]+): InfluxDB version must be 1 or 2\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_JSON_OBJECT', path => $1, field => $2) if ($message =~ /\A([^:]+): (.+) must be a JSON object\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_TYPE', path => $1) if ($message =~ /\A([^:]+): MySmartGrid type must be device or sensor\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_NONNEGATIVE', path => $1, field => $2) if ($message =~ /\A([^:]+): (.+) must be a non-negative integer\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_NUMBER', path => $1, field => $2) if ($message =~ /\A([^:]+): (.+) must be a number\.\z/);
	return _channel_phrase($phrases, 'VZLOGGER.CHANNEL_VALID_REQUIRED', path => $1, field => $2) if ($message =~ /\A([^:]+): (.+) is required(?: for version \S+)?\.\z/);
	return $message;
}

sub localize_validation_errors
{
	my ($errors, $phrases) = @_;
	return [] if (ref($errors) ne "ARRAY");
	return [map { _localize_validation_error($_, $phrases) } @$errors];
}

sub is_json_boolean
{
	my ($value) = @_;
	return defined($value) && JSON::PP::is_bool($value) ? 1 : 0;
}

sub is_nonnegative_integer
{
	my ($value) = @_;
	return defined($value) && !ref($value) && "$value" =~ /\A\d+\z/;
}

sub is_nonempty_scalar
{
	my ($value) = @_;
	return defined($value) && !ref($value) && $value ne "";
}

sub is_http_url
{
	my ($value) = @_;
	return is_nonempty_scalar($value) && $value =~ m{\Ahttps?://[^\s/]+(?:/[^\s]*)?\z}i;
}

sub is_json_object_value
{
	my ($value) = @_;
	return 1 if (ref($value) eq "HASH");
	return 0 if (ref($value));
	my $decoded = eval { JSON::PP->new->decode($value) };
	return !$@ && ref($decoded) eq "HASH";
}

sub native_channel
{
	my ($definition, $aggtime) = @_;
	my $api = $definition->{api} || "null";
	my $native = {
		api => $api,
		uuid => $definition->{uuid},
		identifier => compose_obis($definition->{obis}, $definition->{storage}),
	};
	$native->{aggmode} = ($aggtime || 0) > 0 ? ($definition->{aggmode} || "none") : "none";
	$native->{duplicates} = int($definition->{duplicates} || 0) if ($api eq "volkszaehler" || $api eq "influxdb");
	my $options = $definition->{api_options}->{$api} || {};
	my %allowed = (
		volkszaehler => [qw(middleware timeout)],
		influxdb => [qw(version host token organization username password database measurement_name tags timeout max_batch_inserts max_buffer_size send_uuid ssl_verifypeer)],
		mysmartgrid => [qw(middleware secretKey device type interval scaler timeout name)],
	);
	foreach my $key (@{$allowed{$api} || []}) {
		next if (!exists($options->{$key}) || !defined($options->{$key}) || $options->{$key} eq "");
		my $value = $options->{$key};
		if ($key =~ /\A(?:timeout|max_batch_inserts|max_buffer_size|interval)\z/ && !ref($value) && $value =~ /\A-?\d+\z/) {
			$value = int($value);
		} elsif ($key eq "scaler" && !ref($value) && $value =~ /\A-?\d+(?:\.\d+)?\z/) {
			$value = 0 + $value;
		} elsif ($key eq "tags" && !ref($value)) {
			my $decoded = eval { JSON::PP->new->decode($value) };
			$value = $decoded if (!$@ && ref($decoded) eq "HASH");
		} elsif ($key =~ /\A(?:send_uuid|ssl_verifypeer)\z/) {
			$value = $value ? JSON::PP::true : JSON::PP::false;
		}
		$native->{$key} = $value;
	}
	return $native;
}

1;
