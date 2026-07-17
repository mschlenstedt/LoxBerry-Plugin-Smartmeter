#!/usr/bin/perl
use strict;
use warnings;
use CGI;
use Config::Simple;
use IO::Socket::INET;
use JSON::PP;
use LoxBerry::System;

my $cgi = CGI->new;
my $cfg = Config::Simple->new("$lbpconfigdir/smartmeter.cfg");
my $port = $cfg ? ($cfg->param("VZLOGGER.LOCALPORT") || 18080) : 18080;
my $mapping_file = "$lbpconfigdir/vzlogger_channels.json";
my $metadata_version = metadata_version($mapping_file, "$lbpconfigdir/smartmeter.cfg");
if ($cgi->param("meta")) {
	print $cgi->header(-type => "application/json", -charset => "utf-8", -expires => "now");
	print JSON::PP->new->utf8->canonical->encode(read_channel_metadata($mapping_file, $cfg, $metadata_version));
	exit 0;
}
if ($cgi->param("json")) {
	my $json = read_live_json($port);
	print $cgi->header(
		-type => "application/json",
		-charset => "utf-8",
		-expires => "now",
		-X_Smartmeter_Metadata_Version => $metadata_version,
	);
	print $json;
	exit 0;
}
print $cgi->header(-type => "text/html", -charset => "utf-8", -expires => "now");
print <<'HTML';
<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>vzLogger Live-Daten</title>
<style>
:root{color-scheme:light;--border:#c8cdd2;--muted:#5f6872;--head:#eef1f3;--channel:#f7f8f9;--error:#a32020}
*{box-sizing:border-box}
body{font-family:Arial,sans-serif;margin:0;color:#202428;background:#fff}
main{width:min(1100px,100%);margin:0 auto;padding:1.25rem}
h1{font-size:1.55rem;margin:0 0 .35rem;letter-spacing:0}
h2{font-size:1.15rem;margin:1.6rem 0 .55rem;padding-bottom:.4rem;border-bottom:2px solid #454b50;letter-spacing:0}
.serial{display:block;margin-top:.2rem;color:var(--muted);font-size:.82rem;font-weight:normal}
.status{min-height:1.4rem;margin-bottom:1rem;color:var(--muted);font-size:.9rem}
.error{color:var(--error)}
.table-wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;table-layout:fixed}
th,td{border:1px solid var(--border);padding:.48rem .6rem;text-align:left;vertical-align:top;overflow-wrap:anywhere}
thead th{background:var(--head);font-size:.85rem}
.channel-heading th{background:var(--channel);padding:.62rem}
.channel-title{font-size:.98rem;font-weight:700}
.channel-meta{display:block;margin-top:.18rem;color:var(--muted);font-size:.78rem;font-weight:normal}
.time{width:48%}.raw-time{color:var(--muted);font-variant-numeric:tabular-nums}.value{font-variant-numeric:tabular-nums}
.empty{padding:.8rem;border:1px solid var(--border);color:var(--muted)}
@media(max-width:620px){main{padding:.85rem}h1{font-size:1.3rem}.time{width:58%}th,td{padding:.42rem;font-size:.86rem}}
</style>
</head>
<body><main><h1>vzLogger Live-Daten</h1><div id="status" class="status">Daten werden geladen...</div><div id="state"></div></main>
<script>
let metadataVersion='';
let metadata={channels:{}};

function esc(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function readableName(value){return String(value||'Unbenannter Kanal').replace(/_/g,' ');}
function displayValue(value,meta){
	const numeric=Number(value);
	const factor=Number(meta.display_factor??1);
	const unit=String(meta.unit||'');
	if(!Number.isFinite(numeric)||!Number.isFinite(factor))return esc(value)+(unit?' '+esc(unit):'');
	const scaled=numeric*factor;
	const formatted=new Intl.NumberFormat('de-DE',{maximumFractionDigits:6,useGrouping:false}).format(scaled);
	const title=factor!==1?' title="vzLogger-Rohwert: '+esc(value)+'"':'';
	return '<span'+title+'>'+esc(formatted)+(unit?' '+esc(unit):'')+'</span>';
}
function channelUuid(channel){return String(channel.uuid||channel.id||'').toLowerCase();}
function channelNumber(meta,index){return Number.isInteger(meta.channel_index)?meta.channel_index:index;}
function timestampText(value){
	const numeric=Number(value);
	if(!Number.isFinite(numeric))return esc(value);
	const milliseconds=Math.abs(numeric)<100000000000?numeric*1000:numeric;
	const date=new Date(milliseconds);
	const readable=Number.isNaN(date.getTime())?'ungueltige Zeit':date.toLocaleString('de-DE',{dateStyle:'medium',timeStyle:'medium'});
	return '<span class="raw-time">'+esc(value)+'</span> ('+esc(readable)+')';
}

async function loadMetadata(){
	const response=await fetch('?meta=1',{cache:'no-store'});
	if(!response.ok)throw new Error('Kanal-Metadaten konnten nicht geladen werden.');
	metadata=await response.json();
	metadata.channels=metadata.channels||{};
	metadataVersion=String(metadata.version||'');
}

function render(data){
	if(data&&data.error)throw new Error(data.error);
	const channels=Array.isArray(data&&data.data)?data.data:(Array.isArray(data)?data:[]);
	if(!channels.length){document.getElementById('state').innerHTML='<div class="empty">Keine vzLogger-Kanaldaten verfuegbar.</div>';return;}

	const groups=new Map();
	channels.forEach((channel,index)=>{
		const uuid=channelUuid(channel);
		const meta=metadata.channels[uuid]||{};
		const serial=meta.serial||'unknown';
		if(!groups.has(serial))groups.set(serial,{name:meta.head_name||serial,serial,channels:[]});
		groups.get(serial).channels.push({channel,meta,index,uuid});
	});

	const output=[];
	groups.forEach(group=>{
		output.push('<section><h2>'+esc(group.name)+'<span class="serial">I/R-Lesekopf: '+esc(group.serial)+'</span></h2>');
		output.push('<div class="table-wrap"><table><thead><tr><th class="time">Timestamp (lokale Zeit)</th><th>Wert</th></tr></thead><tbody>');
		group.channels.sort((a,b)=>channelNumber(a.meta,a.index)-channelNumber(b.meta,b.index)).forEach(item=>{
			const number=channelNumber(item.meta,item.index);
			const identifier=item.meta.identifier||item.channel.identifier||'';
			const name=item.meta.display_name||item.meta.catalog_name_de||readableName(item.meta.name||identifier||item.uuid);
			output.push('<tr class="channel-heading"><th colspan="2"><span class="channel-title">Kanal '+esc(number)+' - '+esc(name)+'</span><span class="channel-meta">OBIS: '+esc(identifier||'-')+' | UUID: '+esc(item.uuid||'-')+'</span></th></tr>');
			const tuples=Array.isArray(item.channel.tuples)?item.channel.tuples:[];
			if(!tuples.length){output.push('<tr><td colspan="2" class="empty">Noch kein Messwert vorhanden.</td></tr>');return;}
			tuples.forEach(tuple=>{
				const timestamp=Array.isArray(tuple)?tuple[0]:'';
				const value=Array.isArray(tuple)?tuple[1]:tuple;
				output.push('<tr><td>'+timestampText(timestamp)+'</td><td class="value">'+displayValue(value,item.meta)+'</td></tr>');
			});
		});
		output.push('</tbody></table></div></section>');
	});
	output.push('<p class="status">vzLogger '+esc(data.version||'')+(data.generator?' | '+esc(data.generator):'')+'</p>');
	document.getElementById('state').innerHTML=output.join('');
}

async function refresh(){
	try{
		const response=await fetch('?json=1',{cache:'no-store'});
		if(!response.ok)throw new Error('Live-Daten konnten nicht geladen werden.');
		const currentVersion=response.headers.get('X-Smartmeter-Metadata-Version')||'';
		if(currentVersion&&currentVersion!==metadataVersion)await loadMetadata();
		render(await response.json());
		document.getElementById('status').className='status';
		document.getElementById('status').textContent='Letzte Aktualisierung: '+new Date().toLocaleString('de-DE');
	}catch(error){
		document.getElementById('status').className='status error';
		document.getElementById('status').textContent=error.message;
	}
}

(async()=>{try{await loadMetadata();await refresh();}catch(error){document.getElementById('status').className='status error';document.getElementById('status').textContent=error.message;}setInterval(refresh,2000);})();
</script></body></html>
HTML

sub metadata_version {
	my (@files) = @_;
	return join("-", map {
		my @stat = stat($_);
		@stat ? "$stat[9]:$stat[7]" : "0:0";
	} @files);
}

sub read_channel_metadata {
	my ($file, $plugin_cfg, $version) = @_;
	my %channels;
	if (-e $file && open(my $fh, "<", $file)) {
		local $/;
		my $text = <$fh> || "";
		close($fh);
		my $mapping = eval { JSON::PP->new->utf8->decode($text) };
		if (!$@ && ref($mapping) eq "HASH") {
			foreach my $uuid (keys %$mapping) {
				my $entry = $mapping->{$uuid};
				next if (ref($entry) ne "HASH");
				my $serial = $entry->{serial} || "unknown";
				$channels{lc($uuid)} = {
					serial => $serial,
					head_name => $plugin_cfg ? ($plugin_cfg->param("$serial.NAME") || $serial) : $serial,
					name => $entry->{name} || "",
					display_name => $entry->{display_name} || "",
					catalog_name_de => $entry->{catalog_name_de} || "",
					catalog_name_en => $entry->{catalog_name_en} || "",
					unit => $entry->{unit} || "",
					display_factor => defined($entry->{display_factor}) ? 0 + $entry->{display_factor} : 1,
					identifier => $entry->{identifier} || "",
					channel => $entry->{channel} || "",
					channel_index => defined($entry->{channel_index}) ? int($entry->{channel_index}) : 0,
				};
			}
		}
	}
	return {
		version => $version,
		channels => \%channels,
	};
}

sub read_live_json {
	my ($port) = @_;
	my $socket = IO::Socket::INET->new(PeerHost => "127.0.0.1", PeerPort => $port, Proto => "tcp", Timeout => 3);
	return JSON::PP->new->encode({ error => "vzLogger HTTP service is unavailable" }) if (!$socket);
	print $socket "GET / HTTP/1.0\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n";
	local $/;
	my $response = <$socket> || "";
	close($socket);
	$response =~ s/\A.*?\r?\n\r?\n//s;
	return $response =~ /^\s*[\[{]/ ? $response : JSON::PP->new->encode({ error => "Invalid vzLogger response" });
}
