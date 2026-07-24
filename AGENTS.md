# Project Instructions

This repository contains the LoxBerry Smartmeter-NG plugin. Keep changes small, compatible with the LoxBerry plugin layout, and focused on the existing shell, Perl, PHP, CGI, template, and configuration files.

The normative product and engineering contracts are consolidated in `docs/developer-requirements.md`. Read the relevant sections before changing configuration behavior, mode switching, data models, outputs, permissions, lifecycle handling, or UI behavior.

## Working Rules

- Preserve the LoxBerry plugin structure and metadata contracts in `plugin.cfg`, `release.cfg`, and `prerelease.cfg`.
- Treat `PLUGIN.NAME`, `PLUGIN.FOLDER`, and `AUTHOR` identity fields as stable update identifiers.
- Keep developer-facing comments and documentation in English unless editing German user-facing language files or German documentation.
- For UI text, update the matching language/template files together so German and English views stay consistent.
- Update user documentation and `CHANGELOG.md` whenever behavior, setup, configuration, dependencies, or upgrade steps change.
- Prefer existing scripts and helper patterns over adding new frameworks or dependencies.
- Do not remove or overwrite user configuration defaults in `config/smartmeter.json` without a migration path.

## LoxBerry-Specific Checks

- The LoxBerry v4 plugin-management documentation button is driven by `PLUGIN.WEBSITE`, not `AUTHOR.WEBSITE`.
- Upgrade success should include cron removal followed by restoring automatic meter polling in `postupgrade.sh`.
- Generic LoxBerry system warnings in install logs are not automatically plugin failures; check the surrounding plugin success markers first.
- Installation and upgrade scripts should be POSIX-shell compatible for the target LoxBerry environment.

## Responsive UI Requirements

- Every plugin page must provide the same functions and information in desktop and mobile browsers; do not maintain a reduced mobile-only workflow.
- Design for `1280x800` desktop and `390x844` mobile portrait as the primary viewports. Support `360x800` compact phones and degrade cleanly at the `320x568` minimum viewport; wider desktop screens must not stretch controls into unreadable layouts.
- Plugin content must not create horizontal page scrolling, clipped text or controls, overlapping sections, or unreachable navigation. Tables and multi-column forms must stack or wrap on narrow screens, and long paths, identifiers, and URLs must wrap safely.
- Keep controls readable and touch-usable. Primary plugin buttons should be at least 40 CSS pixels high; existing compact LoxBerry/jQuery Mobile widgets may retain framework sizing only when their enhanced visible control remains clearly usable.

## Verification

- After Perl script changes on Windows, run `tools/check-perl-syntax.ps1 <file>` so the checked-in LoxBerry stubs in `.github/ci/perl-lib` are on `@INC`. Use `perl -c` directly only on a LoxBerry system with the real LoxBerry Perl modules available. For PHP files, run `php -l`.
- For install or upgrade behavior, validate against the relevant install log rather than relying only on static review.
- For implementation tasks that affect installed plugin behavior, deploy only the changed runtime files to the configured disposable LoxBerry test target after local checks, then verify syntax, configuration, and relevant service state on the target. Follow `docs/test-device-workflow.md`.
- Do not write to the test target for analysis-only or review-only tasks unless the user explicitly requests it.
- Never store or print test-device passwords or private keys. Use a local SSH configuration or PuTTY saved-session name.
- Resolve the test target through `tools/TestDeviceSettings.ps1`; developers configure it outside the repository with `tools/configure-test-device.ps1`.
- Preserve remote user configuration and runtime data. Back up affected remote files, preserve their modes, and restore the initial configuration and service state after destructive tests.
- After UI, template, CSS, navigation, or user-facing text changes, test the vzLogger page in an authenticated desktop browser and with mobile viewport emulation on the disposable LoxBerry. Use the viewport matrix and checks in `docs/test-device-workflow.md`.
- Before committing, check `git status --short` and avoid reverting unrelated local changes.

## Release Work

- Build local test packages only with `tools/build-local.ps1`. Local ZIP names must contain `-local-`, the short Git commit, an optional purpose, and `-dirty` for an uncommitted worktree; see `docs/local-builds.md`.
- Never create or publish a suffixless `Smartmeter-V<version>.zip` locally. Official releases and their ZIP assets are created exclusively by the GitHub `Release asset` workflow.
- When asked to create a release, follow `docs/release-process.md`.
