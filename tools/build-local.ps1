[CmdletBinding()]
param(
	[string] $Purpose
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pluginConfig = Join-Path $repoRoot "plugin.cfg"
$distDirectory = Join-Path $repoRoot "dist"

$versionLines = @(Get-Content -LiteralPath $pluginConfig |
	Where-Object { $_ -match "^VERSION=([0-9]+(?:\.[0-9]+)+)$" })
if ($versionLines.Count -ne 1 -or $versionLines[0] -notmatch "^VERSION=([0-9]+(?:\.[0-9]+)+)$") {
	throw "plugin.cfg must contain exactly one numeric VERSION entry."
}
$version = $Matches[1]

if ($Purpose) {
	$normalizedPurpose = $Purpose.Trim().ToLowerInvariant()
	$normalizedPurpose = $normalizedPurpose -replace "[^a-z0-9]+", "-"
	$normalizedPurpose = $normalizedPurpose.Trim("-")
	if (-not $normalizedPurpose) {
		throw "Purpose must contain at least one ASCII letter or digit."
	}
	if ($normalizedPurpose.Length -gt 40) {
		throw "Normalized purpose must not exceed 40 characters."
	}
}

$commit = (& git -C $repoRoot rev-parse --short=7 HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $commit -notmatch "^[0-9a-f]{7}$") {
	throw "Unable to determine the current Git commit."
}

$status = @(& git -C $repoRoot status --porcelain --untracked-files=normal)
if ($LASTEXITCODE -ne 0) {
	throw "Unable to determine the Git worktree status."
}
$isDirty = $status.Count -gt 0

$nameParts = @("Smartmeter-V$version", "local")
if ($normalizedPurpose) {
	$nameParts += $normalizedPurpose
}
$nameParts += $commit
if ($isDirty) {
	$nameParts += "dirty"
}
$archiveName = ($nameParts -join "-") + ".zip"
$archivePath = Join-Path $distDirectory $archiveName
$packageRootName = "LoxBerry-Plugin-Smartmeter-v2-" + ($nameParts -join "-")

$temporaryBase = Join-Path ([System.IO.Path]::GetTempPath()) "smartmeter-local-build-$PID"
$temporaryIndex = Join-Path $temporaryBase "index"
if (Test-Path -LiteralPath $temporaryBase) {
	throw "Temporary build directory already exists: $temporaryBase"
}

$previousIndexFile = $env:GIT_INDEX_FILE
try {
	New-Item -ItemType Directory -Path $temporaryBase -Force | Out-Null
	$env:GIT_INDEX_FILE = $temporaryIndex

	& git -C $repoRoot read-tree HEAD
	if ($LASTEXITCODE -ne 0) {
		throw "Unable to initialize the temporary Git index."
	}
	$addOutput = @(& git -C $repoRoot add -A -- . 2>&1)
	if ($LASTEXITCODE -ne 0) {
		throw "Unable to snapshot the current worktree in the temporary Git index: $($addOutput -join [Environment]::NewLine)"
	}
	$tree = (& git -C $repoRoot write-tree).Trim()
	if ($LASTEXITCODE -ne 0 -or $tree -notmatch "^[0-9a-f]{40,64}$") {
		throw "Unable to create a temporary Git tree for the local build."
	}

	New-Item -ItemType Directory -Path $distDirectory -Force | Out-Null
	& git -C $repoRoot archive --format=zip --worktree-attributes --prefix="$packageRootName/" -o $archivePath $tree
	if ($LASTEXITCODE -ne 0) {
		throw "git archive failed."
	}
} finally {
	if ($null -eq $previousIndexFile) {
		Remove-Item Env:GIT_INDEX_FILE -ErrorAction SilentlyContinue
	} else {
		$env:GIT_INDEX_FILE = $previousIndexFile
	}
	if (Test-Path -LiteralPath $temporaryBase) {
		Remove-Item -LiteralPath $temporaryBase -Recurse -Force
	}
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
try {
	foreach ($entry in $archive.Entries) {
		if (-not $entry.Name) {
			continue
		}
		$stream = $entry.Open()
		try {
			$stream.CopyTo([System.IO.Stream]::Null)
		} finally {
			$stream.Dispose()
		}
	}

	$pluginEntryName = "$packageRootName/plugin.cfg"
	$pluginEntry = $archive.Entries | Where-Object { $_.FullName -eq $pluginEntryName }
	if (-not $pluginEntry) {
		throw "Built archive does not contain $pluginEntryName."
	}
	$reader = [System.IO.StreamReader]::new($pluginEntry.Open())
	try {
		$archivedPluginConfig = $reader.ReadToEnd()
	} finally {
		$reader.Dispose()
	}
	if ($archivedPluginConfig -notmatch "(?m)^VERSION=$([regex]::Escape($version))\r?$") {
		throw "The archived plugin.cfg version does not match $version."
	}
} finally {
	$archive.Dispose()
}

$hash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
Write-Host "Local package: $archivePath"
Write-Host "Version: $version"
Write-Host "Commit: $commit"
Write-Host "Dirty: $isDirty"
Write-Host "SHA-256: $hash"
