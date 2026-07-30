function Resolve-TestDeviceSettings {
	param(
		[string] $Target,
		[string] $Transport,
		[string] $PluginFolder,
		[string] $IdentityFile
	)

	$configPath = Join-Path $env:APPDATA "LoxBerry-SmartMeter\test-device.psd1"
	$local = if (Test-Path -LiteralPath $configPath) {
		Import-PowerShellDataFile -LiteralPath $configPath
	} else {
		@{}
	}

	if ([string]::IsNullOrWhiteSpace($Target)) {
		$Target = if ($env:SMARTMETER_TEST_TARGET) { $env:SMARTMETER_TEST_TARGET } elseif ($local.Target) { $local.Target } else { "LoxBerry-Test" }
	}
	if ([string]::IsNullOrWhiteSpace($Transport)) {
		$Transport = if ($env:SMARTMETER_TEST_TRANSPORT) { $env:SMARTMETER_TEST_TRANSPORT } elseif ($local.Transport) { $local.Transport } else { "OpenSSH" }
	}
	if ([string]::IsNullOrWhiteSpace($PluginFolder)) {
		$PluginFolder = if ($env:SMARTMETER_TEST_PLUGIN_FOLDER) { $env:SMARTMETER_TEST_PLUGIN_FOLDER } elseif ($local.PluginFolder) { $local.PluginFolder } else { "smartmeter-v2" }
	}
	if ([string]::IsNullOrWhiteSpace($IdentityFile)) {
		$IdentityFile = if ($env:SMARTMETER_TEST_IDENTITY_FILE) { $env:SMARTMETER_TEST_IDENTITY_FILE } elseif ($local.IdentityFile) { $local.IdentityFile } else { $null }
	}

	if ($Target -notmatch "^[A-Za-z0-9][A-Za-z0-9._@:-]*$") {
		throw "Invalid test-device target or session name: $Target"
	}
	if ($Transport -notin "OpenSSH", "PuTTY") {
		throw "Invalid test-device transport: $Transport"
	}
	if ($PluginFolder -notmatch "^[a-z0-9][a-z0-9-]*$") {
		throw "Invalid plugin folder: $PluginFolder"
	}
	if ($IdentityFile -and $IdentityFile -match "[\r\n]") {
		throw "Invalid SSH identity-file path."
	}

	[pscustomobject]@{
		Target = $Target
		Transport = $Transport
		PluginFolder = $PluginFolder
		IdentityFile = $IdentityFile
		ConfigPath = $configPath
	}
}
