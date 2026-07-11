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
my $json = read_live_json($port);
if ($cgi->param("json")) {
	print $cgi->header(-type => "application/json", -charset => "utf-8", -expires => "now");
	print $json;
	exit 0;
}
print $cgi->header(-type => "text/html", -charset => "utf-8", -expires => "now");
print <<'HTML';
<!doctype html><html lang="de"><head><meta charset="utf-8"><title>vzLogger Live-Daten</title>
<style>body{font-family:sans-serif;margin:1rem}table{border-collapse:collapse;width:100%}th,td{border:1px solid #bbb;padding:.45rem;text-align:left}th{background:#eee}.error{color:#a00}</style></head>
<body><h1>vzLogger Live-Daten</h1><p>Automatische Aktualisierung alle 2 Sekunden.</p><div id="state"></div>
<script>
function esc(s){return s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function rows(v,p,o){if(v!==null&&typeof v==='object'){Object.keys(v).forEach(k=>rows(v[k],p?p+'.'+k:k,o));return;}o.push('<tr><td>'+esc(p)+'</td><td>'+esc(String(v))+'</td></tr>');}
async function refresh(){try{const r=await fetch('?json=1',{cache:'no-store'}),d=await r.json(),o=[];rows(d,'',o);document.getElementById('state').innerHTML='<table><thead><tr><th>Feld / OBIS-Kanal</th><th>Wert</th></tr></thead><tbody>'+o.join('')+'</tbody></table>';}catch(e){document.getElementById('state').innerHTML='<p class="error">'+esc(e.message)+'</p>';}}
refresh();setInterval(refresh,2000);
</script></body></html>
HTML

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
