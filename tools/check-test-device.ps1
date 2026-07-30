[CmdletBinding()]
param(
	[string] $Target,

	[string] $Transport,

	[string] $PluginFolder,

	[string] $IdentityFile
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "TestDeviceSettings.ps1")
$settings = Resolve-TestDeviceSettings -Target $Target -Transport $Transport -PluginFolder $PluginFolder -IdentityFile $IdentityFile
$Target = $settings.Target
$Transport = $settings.Transport
$PluginFolder = $settings.PluginFolder
$IdentityFile = $settings.IdentityFile
$remoteCommand = @"
set -u
plugin_config='/opt/loxberry/config/plugins/$PluginFolder'
printf 'Host: '; hostname
printf 'User: '; id -un
printf 'Plugin config: %s\n' "`$plugin_config"
for service in vzlogger smartmeter-v2-vzlogger-bridge; do
    if systemctl list-unit-files "`$service.service" --no-legend 2>/dev/null | grep -q .; then
        printf '%s: ' "`$service"
        systemctl is-active "`$service.service" 2>/dev/null || true
    else
        printf '%s: not installed\n' "`$service"
    fi
done
for file in smartmeter.json vzlogger.conf vzlogger_expert.conf vzlogger_channels.json; do
    path="`$plugin_config/`$file"
    if [ -f "`$path" ]; then
        if command -v sha256sum >/dev/null 2>&1; then
            checksum=`$(sha256sum "`$path" | awk '{print `$1}')
        else
            checksum='sha256sum-unavailable'
        fi
        printf '%s: present, %s bytes, sha256 %s\n' "`$file" "`$(wc -c < "`$path")" "`$checksum"
    else
        printf '%s: missing\n' "`$file"
    fi
done
for file in vzlogger.conf vzlogger_expert.conf vzlogger_channels.json; do
    path="`$plugin_config/`$file"
    if [ -f "`$path" ]; then
        if python3 -m json.tool "`$path" >/dev/null 2>&1; then
            printf '%s JSON: valid\n' "`$file"
        else
            printf '%s JSON: INVALID\n' "`$file"
        fi
    fi
done
"@

Write-Host "Read-only test-device check: $Target ($Transport)"
if ($Transport -eq "PuTTY") {
	& plink.exe -batch -load $Target $remoteCommand
} else {
	$identityArguments = if ($IdentityFile) { @("-i", $IdentityFile) } else { @() }
	& ssh.exe @identityArguments -o BatchMode=yes -- $Target $remoteCommand
}
if ($LASTEXITCODE -ne 0) {
	throw "Test-device check failed with exit code $LASTEXITCODE."
}
