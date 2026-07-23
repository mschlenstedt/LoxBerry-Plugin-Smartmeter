param(
	[Parameter(ValueFromRemainingArguments = $true)]
	[string[]] $Path
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$stubRoot = Join-Path $repoRoot ".github\ci\perl-lib"
$pluginBin = Join-Path $repoRoot "bin"

if (-not (Test-Path (Join-Path $stubRoot "LoxBerry\System.pm"))) {
	throw "Missing LoxBerry Perl stubs below $stubRoot"
}

if (-not $Path -or $Path.Count -eq 0) {
	$Path = Get-ChildItem -Path $repoRoot -Recurse -File |
		Where-Object { $_.Extension -in ".pl", ".pm", ".cgi" } |
		ForEach-Object { $_.FullName }
}

if ($Path.Count -eq 0) {
	Write-Host "No Perl files found."
	exit 0
}

$failed = $false
foreach ($item in $Path) {
	$resolved = Resolve-Path -LiteralPath $item
	foreach ($file in $resolved) {
		& perl -I $stubRoot -I $pluginBin -c $file.Path
		if ($LASTEXITCODE -ne 0) {
			$failed = $true
		}
	}
}

if ($failed) {
	exit 1
}
