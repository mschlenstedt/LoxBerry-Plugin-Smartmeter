# Project Instructions

This repository contains the LoxBerry SmartMeter v2 plugin. Keep changes small, compatible with the LoxBerry plugin layout, and focused on the existing shell, Perl, PHP, CGI, template, and configuration files.

## Working Rules

- Preserve the LoxBerry plugin structure and metadata contracts in `plugin.cfg`, `release.cfg`, and `prerelease.cfg`.
- Treat `PLUGIN.NAME`, `PLUGIN.FOLDER`, and `AUTHOR` identity fields as stable update identifiers.
- Keep developer-facing comments and documentation in English unless editing German user-facing language files or German documentation.
- For UI text, update the matching language/template files together so German and English views stay consistent.
- Update user documentation and `CHANGELOG.md` whenever behavior, setup, configuration, dependencies, or upgrade steps change.
- Prefer existing scripts and helper patterns over adding new frameworks or dependencies.
- Do not remove or overwrite user configuration defaults in `config/smartmeter.cfg` without a migration path.

## LoxBerry-Specific Checks

- The LoxBerry v4 plugin-management documentation button is driven by `PLUGIN.WEBSITE`, not `AUTHOR.WEBSITE`.
- Upgrade success should include cron removal followed by restoring automatic meter polling in `postupgrade.sh`.
- Generic LoxBerry system warnings in install logs are not automatically plugin failures; check the surrounding plugin success markers first.
- Installation and upgrade scripts should be POSIX-shell compatible for the target LoxBerry environment.

## Verification

- After Perl script changes on Windows, run `tools/check-perl-syntax.ps1 <file>` so the checked-in LoxBerry stubs in `.github/ci/perl-lib` are on `@INC`. Use `perl -c` directly only on a LoxBerry system with the real LoxBerry Perl modules available. For PHP files, run `php -l`.
- For install or upgrade behavior, validate against the relevant install log rather than relying only on static review.
- For implementation tasks that affect installed plugin behavior, deploy only the changed runtime files to the configured disposable LoxBerry test target after local checks, then verify syntax, configuration, and relevant service state on the target. Follow `docs/test-device-workflow.md`.
- Do not write to the test target for analysis-only or review-only tasks unless the user explicitly requests it.
- Never store or print test-device passwords or private keys. Use a local SSH configuration or PuTTY saved-session name.
- Resolve the test target through `tools/TestDeviceSettings.ps1`; developers configure it outside the repository with `tools/configure-test-device.ps1`.
- Preserve remote user configuration and runtime data. Back up affected remote files, preserve their modes, and restore the initial configuration and service state after destructive tests.
- Before committing, check `git status --short` and avoid reverting unrelated local changes.

## Release Work

- When asked to create a release, follow `docs/release-process.md`.
