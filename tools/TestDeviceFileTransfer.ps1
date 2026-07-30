function ConvertTo-LfLineEndings {
	param(
		[Parameter(Mandatory = $true)]
		[byte[]] $Bytes
	)

	$buffer = [byte[]]::new($Bytes.Length)
	$writeIndex = 0
	for ($readIndex = 0; $readIndex -lt $Bytes.Length; $readIndex++) {
		if ($Bytes[$readIndex] -eq 13 -and
			$readIndex + 1 -lt $Bytes.Length -and
			$Bytes[$readIndex + 1] -eq 10) {
			continue
		}
		$buffer[$writeIndex] = $Bytes[$readIndex]
		$writeIndex++
	}

	$result = [byte[]]::new($writeIndex)
	[Array]::Copy($buffer, $result, $writeIndex)
	return ,$result
}
