[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
	[Parameter(Mandatory = $true, Position = 0)]
	[string[]] $Files,

	[string] $Target,

	[string] $Transport,

	[string] $PluginFolder,

	[string] $IdentityFile,

	[switch] $AllowConfig,

	[switch] $Apply
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
. (Join-Path $PSScriptRoot "TestDeviceSettings.ps1")
$settings = Resolve-TestDeviceSettings -Target $Target -Transport $Transport -PluginFolder $PluginFolder -IdentityFile $IdentityFile
$Target = $settings.Target
$Transport = $settings.Transport
$PluginFolder = $settings.PluginFolder
$IdentityFile = $settings.IdentityFile
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$remoteStage = "/tmp/$PluginFolder-deploy-$timestamp-$PID"
$remoteBackup = "/tmp/$PluginFolder-deploy-backups/$timestamp-$PID"

function Invoke-Ssh {
	param([Parameter(Mandatory = $true)][string] $Command)

	if ($Transport -eq "PuTTY") {
		& plink.exe -batch -load $Target $Command
	} else {
		$identityArguments = if ($IdentityFile) { @("-i", $IdentityFile) } else { @() }
		& ssh.exe @identityArguments -o BatchMode=yes -- $Target $Command
	}
	if ($LASTEXITCODE -ne 0) {
		throw "Remote command failed with exit code $LASTEXITCODE."
	}
}

function Copy-ToTarget {
	param(
		[Parameter(Mandatory = $true)][string] $LocalPath,
		[Parameter(Mandatory = $true)][string] $RemotePath
	)

	if ($Transport -eq "PuTTY") {
		& pscp.exe -batch -load $Target -- $LocalPath "${Target}:$RemotePath"
	} else {
		$identityArguments = if ($IdentityFile) { @("-i", $IdentityFile) } else { @() }
		& scp.exe @identityArguments -q -- $LocalPath "${Target}:$RemotePath"
	}
	if ($LASTEXITCODE -ne 0) {
		throw "Upload failed with exit code $LASTEXITCODE."
	}
}

function Convert-ToRemoteDestination {
	param([Parameter(Mandatory = $true)][string] $RelativePath)

	$normalized = $RelativePath.Replace("\", "/")
	if ($normalized -notmatch "^[A-Za-z0-9._/-]+$") {
		throw "Unsupported characters in repository path: $RelativePath"
	}

	$routes = @(
		@{ Prefix = "webfrontend/htmlauth/"; Root = "/opt/loxberry/webfrontend/htmlauth/plugins/$PluginFolder" },
		@{ Prefix = "webfrontend/html/"; Root = "/opt/loxberry/webfrontend/html/plugins/$PluginFolder" },
		@{ Prefix = "templates/"; Root = "/opt/loxberry/templates/plugins/$PluginFolder" },
		@{ Prefix = "bin/"; Root = "/opt/loxberry/bin/plugins/$PluginFolder" },
		@{ Prefix = "config/"; Root = "/opt/loxberry/config/plugins/$PluginFolder" }
	)

	foreach ($route in $routes) {
		if ($normalized.StartsWith($route.Prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
			if ($route.Prefix -eq "config/" -and -not $AllowConfig) {
				throw "Configuration deployment is blocked. Re-run with -AllowConfig only when overwriting this file is intentional: $RelativePath"
			}
			$tail = $normalized.Substring($route.Prefix.Length)
			if ([string]::IsNullOrWhiteSpace($tail) -or $tail.Contains("../")) {
				throw "Invalid repository path: $RelativePath"
			}
			return "$($route.Root)/$tail"
		}
	}

	throw "File is outside the allowed runtime trees: $RelativePath"
}

$deployments = foreach ($item in $Files) {
	$resolved = (Resolve-Path -LiteralPath $item).Path
	if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
		throw "Not a file: $item"
	}
	$relative = [System.IO.Path]::GetRelativePath($repoRoot, $resolved)
	if ($relative.StartsWith("..")) {
		throw "File is outside the repository: $item"
	}
	[pscustomobject]@{
		Local = $resolved
		Relative = $relative.Replace("\", "/")
		Remote = Convert-ToRemoteDestination $relative
	}
}

Write-Host "Target: $Target ($Transport)"
Write-Host "Backup directory: $remoteBackup"
$deployments | Format-Table Relative, Remote -AutoSize

if (-not $Apply) {
	Write-Host "Preview only. Re-run with -Apply to deploy the listed files."
	exit 0
}

if (-not $PSCmdlet.ShouldProcess($Target, "Deploy $($deployments.Count) SmartMeter runtime file(s)")) {
	exit 0
}

Invoke-Ssh "set -eu; mkdir -p '$remoteStage' '$remoteBackup'"
try {
	for ($index = 0; $index -lt $deployments.Count; $index++) {
		$deployment = $deployments[$index]
		$staged = "$remoteStage/$index"
		Copy-ToTarget -LocalPath $deployment.Local -RemotePath $staged

		$extension = [System.IO.Path]::GetExtension($deployment.Remote).ToLowerInvariant()
		$newMode = if ($extension -in ".cgi", ".pl", ".pm", ".sh") { "0755" } else { "0644" }
		$remoteDirectory = [System.IO.Path]::GetDirectoryName($deployment.Remote).Replace("\", "/")
		$backupPath = "$remoteBackup/$($deployment.Relative)"
		$backupDirectory = [System.IO.Path]::GetDirectoryName($backupPath).Replace("\", "/")

		$installCommand = "set -eu; mkdir -p '$remoteDirectory' '$backupDirectory'; " +
			"if [ -e '$($deployment.Remote)' ]; then cp -p '$($deployment.Remote)' '$backupPath'; cp '$staged' '$($deployment.Remote)'; " +
			"else cp '$staged' '$($deployment.Remote)'; chmod $newMode '$($deployment.Remote)'; fi"
		Invoke-Ssh $installCommand

		switch ($extension) {
			".cgi" { Invoke-Ssh "perl -c '$($deployment.Remote)'" }
			".pl"  { Invoke-Ssh "perl -c '$($deployment.Remote)'" }
			".pm"  { Invoke-Ssh "perl -c '$($deployment.Remote)'" }
			".php" { Invoke-Ssh "php -l '$($deployment.Remote)'" }
			".sh"  { Invoke-Ssh "sh -n '$($deployment.Remote)'" }
		}
	}
} finally {
	Invoke-Ssh "rm -rf '$remoteStage'"
}

Write-Host "Deployment and target-side syntax checks completed."
Write-Host "Remote backups: $remoteBackup"
Write-Host "No services were restarted."
