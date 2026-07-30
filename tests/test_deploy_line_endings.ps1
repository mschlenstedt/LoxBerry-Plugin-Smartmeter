$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "..\tools\TestDeviceFileTransfer.ps1")

function Assert-BytesEqual {
	param(
		[byte[]] $Actual,
		[byte[]] $Expected,
		[string] $Message
	)

	if (-not [System.Linq.Enumerable]::SequenceEqual[byte]($Actual, $Expected)) {
		throw "$Message`nExpected: $($Expected -join ',')`nActual:   $($Actual -join ',')"
	}
}

$crlfScript = [Text.Encoding]::UTF8.GetBytes("#!/usr/bin/perl`r`nprint qq(ok);`r`n")
$lfScript = [Text.Encoding]::UTF8.GetBytes("#!/usr/bin/perl`nprint qq(ok);`n")
Assert-BytesEqual (ConvertTo-LfLineEndings $crlfScript) $lfScript "CRLF scripts must be normalized to LF"

$standaloneCr = [byte[]](65, 13, 66, 10)
Assert-BytesEqual (ConvertTo-LfLineEndings $standaloneCr) $standaloneCr "Standalone CR bytes must be preserved"

$utf8Bom = [byte[]](239, 187, 191, 65, 13, 10)
$expectedBom = [byte[]](239, 187, 191, 65, 10)
Assert-BytesEqual (ConvertTo-LfLineEndings $utf8Bom) $expectedBom "UTF-8 BOM bytes must remain unchanged"

Write-Output "Test-device line-ending normalization tests passed."
