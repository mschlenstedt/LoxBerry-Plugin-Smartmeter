# LoxBerry Test Device Workflow

This workflow applies to implementation tasks that change installed Smartmeter-NG behavior. It does not authorize remote writes for analysis-only or review-only tasks.

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
| `bin/` | `/opt/loxberry/bin/plugins/smartmeter-ng/` |
| `templates/` | `/opt/loxberry/templates/plugins/smartmeter-ng/` |
| `webfrontend/html/` | `/opt/loxberry/webfrontend/html/plugins/smartmeter-ng/` |
| `webfrontend/htmlauth/` | `/opt/loxberry/webfrontend/htmlauth/plugins/smartmeter-ng/` |

Files below `config/` are protected because they may overwrite user configuration. Deploying one requires both an explicit file path and `-AllowConfig`. Generated configuration, logs, cache files, databases, credentials, and other runtime data must not be copied from the repository or between systems.

Before overwriting a file, the script copies the remote version to a timestamped backup directory below `/tmp/smartmeter-ng-deploy-backups/`. These backups normally disappear on reboot. Existing file modes are retained; new CGI, Perl, and shell files receive mode `0755`, while other new files receive `0644`.

After upload, the script runs target-side syntax checks for Perl/CGI, PHP, and shell files. It does not restart services. Restart only the service affected by the change and only when the test requires it.

The deployment script normalizes uploaded Perl, CGI, module, and shell files to LF in a temporary local copy. This is required even with `.gitattributes`, because a Windows working tree may still contain CRLF and `perl -c file.cgi` does not exercise the executable shebang used by Apache.

## Verification and cleanup

Record the initial state before a destructive test:

- Expert Mode and active implementation
- checksums of `vzlogger.conf`, `vzlogger_expert.conf`, and relevant plugin configuration
- `vzlogger` and `smartmeter-ng-vzlogger-bridge` service states

After deployment:

1. Run `tools/check-test-device.ps1` again.
2. Exercise the changed UI or endpoint and inspect the relevant plugin log.
3. Confirm that untouched configuration checksums have not changed.
4. Test service restart behavior when runtime loading is part of the change.
5. Restore the initial Expert Mode, configuration, and service states after tests that deliberately changed them.

For CGI or navigation changes, also test the installed page through an authenticated browser session, preferably the developer's existing Chrome session:

1. Open the normal plugin entry page instead of invoking the CGI only from SSH.
2. Use the visible navigation or action that reaches the changed CGI so jQuery Mobile/AJAX behavior is included.
3. Confirm that the destination page renders and does not show `Error 500` or `Internal Server Error`.
4. If it fails, open LoxBerry's **Log Manager → Apache Log** in the same browser session. If the Log Manager cannot read the file, check `/var/log/apache2/error.log` ownership and mode separately rather than changing them as part of the plugin test.

The browser check complements target-side syntax checks; it is required when executable CGI behavior changed because calling `perl script.cgi` bypasses the shebang.

### Desktop and mobile UI acceptance

For UI, template, CSS, navigation, or user-facing text changes, test the installed vzLogger page at these CSS viewport sizes:

| Profile | Viewport | Required use |
| --- | --- | --- |
| Desktop | `1280x800` | Full desktop workflow and changed interactions |
| Mobile primary | `390x844` | Full mobile workflow and changed interactions |
| Mobile compact | `360x800` | Layout, navigation, forms, and long labels |
| Mobile minimum | `320x568` | Graceful layout only; no clipped or unreachable plugin functions |

Use an authenticated browser session and reach both pages through the visible implementation tabs so jQuery Mobile/AJAX navigation is exercised. At Desktop and Mobile primary sizes, check the initial render and every changed interaction, including relevant collapsibles, dialogs, validation, and action buttons. Use the compact and minimum sizes whenever layout, controls, navigation, or text lengths changed.

Acceptance requires:

- identical available functions and information on desktop and mobile;
- no plugin-caused horizontal page scrolling (`document.documentElement.scrollWidth <= document.documentElement.clientWidth`), excluding closed off-canvas LoxBerry side/help panels;
- no clipped or overlapping labels, controls, status text, paths, identifiers, or URLs;
- usable implementation tabs, navigation, forms, collapsibles, dialogs, and action buttons without zooming;
- safe wrapping or stacking of tables and multi-column form rows; and
- successful rendering without HTTP 500 or browser-console errors introduced by the plugin.

Test the longer German labels when only one language can be exercised. If translated UI text changed, verify both German and English views.

For installation or upgrade changes, install the built plugin archive through the normal LoxBerry plugin manager and validate the complete install log. Direct file deployment is not a substitute for lifecycle testing.
