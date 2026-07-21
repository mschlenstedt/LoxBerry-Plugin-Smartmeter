# LoxBerry Test Device Workflow

This workflow applies to implementation tasks that change installed SmartMeter v2 behavior. It does not authorize remote writes for analysis-only or review-only tasks.

## Local connection setup

Keep the target and credentials outside the repository. Configure the repository tools once for the current Windows user. This creates `%APPDATA%\LoxBerry-SmartMeter\test-device.psd1`, which is outside the repository and contains only the connection target, transport, plugin folder, and optional local key-file path:

```powershell
tools/configure-test-device.ps1 -Target LoxBerry-Test -Transport OpenSSH
```

An OpenSSH key whose filename is not one of the client defaults can be selected explicitly. The settings store only its local path, never its contents:

```powershell
tools/configure-test-device.ps1 -Target loxberry@test-device -Transport OpenSSH -IdentityFile C:\Users\me\.ssh\loxberry_test_ed25519
```

The recommended OpenSSH setup uses the same host alias in the local SSH configuration:

```sshconfig
Host LoxBerry-Test
    HostName <test-device-address>
    User loxberry
    IdentityFile <local-private-key-path>
```

A PuTTY saved session can also be selected. Each developer chooses their own saved-session name without changing the repository:

```powershell
tools/configure-test-device.ps1 -Target My-LoxBerry-Test -Transport PuTTY
```

Do not put passwords, private-key contents, host addresses, or session exports into this repository. The scripts deliberately use non-interactive batch mode, so configure key authentication and an SSH agent, an OpenSSH identity file, or a saved session that obtains its credentials securely. Passwords must never be passed on the command line.

For temporary overrides, pass `-Target`, `-Transport`, `-PluginFolder`, or `-IdentityFile` directly. Automation can instead set `SMARTMETER_TEST_TARGET`, `SMARTMETER_TEST_TRANSPORT`, `SMARTMETER_TEST_PLUGIN_FOLDER`, and `SMARTMETER_TEST_IDENTITY_FILE`. Resolution order is explicit parameters, environment variables, the per-user settings file, then the neutral `LoxBerry-Test`/OpenSSH defaults.

Use another alias with `-Target <alias>` when needed. Verify the selected target before allowing a write:

```powershell
tools/check-test-device.ps1
```

## Deployment

Run the appropriate local syntax and automated tests first. Preview the mapping for every changed runtime file:

```powershell
tools/deploy-test-device.ps1 -Files bin/example.pl,webfrontend/htmlauth/example.cgi
```

Perform the displayed deployment only after checking the target and destination paths:

```powershell
tools/deploy-test-device.ps1 -Files bin/example.pl,webfrontend/htmlauth/example.cgi -Apply
```

The script accepts only files below these plugin runtime trees:

| Repository path | Test-device path |
| --- | --- |
| `bin/` | `/opt/loxberry/bin/plugins/smartmeter-v2/` |
| `templates/` | `/opt/loxberry/templates/plugins/smartmeter-v2/` |
| `webfrontend/html/` | `/opt/loxberry/webfrontend/html/plugins/smartmeter-v2/` |
| `webfrontend/htmlauth/` | `/opt/loxberry/webfrontend/htmlauth/plugins/smartmeter-v2/` |

Files below `config/` are protected because they may overwrite user configuration. Deploying one requires both an explicit file path and `-AllowConfig`. Generated configuration, logs, cache files, databases, credentials, and other runtime data must not be copied from the repository or between systems.

Before overwriting a file, the script copies the remote version to a timestamped backup directory below `/tmp/smartmeter-v2-deploy-backups/`. These backups normally disappear on reboot. Existing file modes are retained; new CGI, Perl, and shell files receive mode `0755`, while other new files receive `0644`.

After upload, the script runs target-side syntax checks for Perl/CGI, PHP, and shell files. It does not restart services. Restart only the service affected by the change and only when the test requires it.

## Verification and cleanup

Record the initial state before a destructive test:

- Expert Mode and active implementation
- checksums of `vzlogger.conf`, `vzlogger_expert.conf`, and relevant plugin configuration
- `vzlogger` and `smartmeter-v2-vzlogger-bridge` service states

After deployment:

1. Run `tools/check-test-device.ps1` again.
2. Exercise the changed UI or endpoint and inspect the relevant plugin log.
3. Confirm that untouched configuration checksums have not changed.
4. Test service restart behavior when runtime loading is part of the change.
5. Restore the initial Expert Mode, configuration, and service states after tests that deliberately changed them.

For installation or upgrade changes, install the built plugin archive through the normal LoxBerry plugin manager and validate the complete install log. Direct file deployment is not a substitute for lifecycle testing.
