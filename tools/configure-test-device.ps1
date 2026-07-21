[CmdletBinding()]
param(
	[Parameter(Mandatory = $true)]
	[ValidatePattern("^[A-Za-z0-9][A-Za-z0-9._@:-]*$")]
	[string] $Target,

	[Parameter(Mandatory = $true)]
	[ValidateSet("OpenSSH", "PuTTY")]
	[string] $Transport,

	[ValidatePattern("^[a-z0-9][a-z0-9-]*$")]
	[string] $PluginFolder = "smartmeter-v2",

	[string] $IdentityFile
)

$ErrorActionPreference = "Stop"
if ($IdentityFile) {
	$IdentityFile = (Resolve-Path -LiteralPath $IdentityFile).Path
	if ($Transport -ne "OpenSSH") {
		throw "-IdentityFile is supported only with the OpenSSH transport. Configure the key in the saved PuTTY session instead."
	}
}
$configDirectory = Join-Path $env:APPDATA "LoxBerry-SmartMeter"
$configPath = Join-Path $configDirectory "test-device.psd1"
New-Item -ItemType Directory -Path $configDirectory -Force | Out-Null

$escapedIdentityFile = if ($IdentityFile) { $IdentityFile.Replace("'", "''") } else { "" }
$content = @"
@{
	Target = '$Target'
	Transport = '$Transport'
	PluginFolder = '$PluginFolder'
	IdentityFile = '$escapedIdentityFile'
}
"@
Set-Content -LiteralPath $configPath -Value $content -Encoding utf8NoBOM

Write-Host "Saved local test-device settings to: $configPath"
Write-Host "No password or private-key content was stored."
