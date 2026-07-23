# Release Process

Use this checklist when the user asks to create a release. Keep the process concise and avoid broad repo analysis unless a check fails.

## Scope

A release means:

- all intended changes are committed and pushed;
- plugin versions and update metadata are bumped;
- release notes are prepared in `CHANGELOG.md`;
- a Git tag is created and pushed;
- a GitHub Release is created with the release notes;
- the GitHub Release contains the generated plugin ZIP asset.

Official releases are created exclusively through GitHub. Do not build, rename, or upload a suffixless `Smartmeter-V<version>.zip` from a developer workstation. Local packages follow `docs/local-builds.md` and always contain `-local-` in their filename.

## Version Locations

Update the same version in:

- `plugin.cfg`: `PLUGIN.VERSION`
- `release.cfg`: `AUTOUPDATE.VERSION`, `ARCHIVEURL`, and `INFOURL`
- `prerelease.cfg`: `AUTOUPDATE.VERSION`, `ARCHIVEURL`, and `INFOURL` when publishing or aligning a prerelease

Current tag format:

```text
Smartmeter-V<version>
```

Example:

```text
smartmeter-ng.0.0.10
```

## Checklist

1. Confirm target version and whether this is a stable release or prerelease.
2. Check `git status --short`; do not include unrelated local changes.
3. Update version metadata in the files listed above.
   - Use the release asset URL for `ARCHIVEURL`, not the automatic GitHub source archive:

```text
https://github.com/mschlenstedt/LoxBerry-Plugin-Smartmeter/releases/download/Smartmeter-V<version>/Smartmeter-V<version>.zip
```

4. Confirm user documentation is current for changed behavior, setup, configuration, dependencies, and upgrade steps. Check `docs/Readme.md`, `docs/User-Guide.de.md`, and `docs/User-Guide.en.md` when user-facing behavior changed.
5. Move the relevant `CHANGELOG.md` entries from `Unreleased` to the target version and date.
6. Run cheap validation:
   - `tools/check-perl-syntax.ps1 <file>` for changed Perl files on Windows, or `perl -I .github/ci/perl-lib -c <file>` on Linux/macOS;
   - `php -l` for changed PHP files;
   - shell syntax checks where available;
   - inspect changed release metadata with `git diff`.
7. Ensure the required GitHub Actions `Perl and PHP syntax` check passes on the release pull request before merging to `master`.
8. Run the relevant lifecycle checks from `docs/lifecycle-test-expectations.md` on LoxBerry when the release changes installation, upgrade, uninstall, dependencies, services, cron jobs, or default configuration behavior.
9. Commit the release changes.
10. Push the branch.
11. Create an annotated tag on the pushed release commit:

```powershell
git tag -a Smartmeter-V<version> -m "Smartmeter V<version>"
git push origin Smartmeter-V<version>
```

12. Wait for the `Release asset` GitHub Actions workflow to finish. It builds `Smartmeter-V<version>.zip` from the tag with `git archive --worktree-attributes`, verifies `plugin.cfg`, creates a draft GitHub Release with the generated ZIP asset, and publishes it as a prerelease.
   - The workflow uploads the ZIP while the release is still a draft because published GitHub Releases can be immutable.
   - If the tag workflow did not run, dispatch `Release asset` manually with the same tag.
13. Verify the GitHub Release title, prerelease flag, release notes, and uploaded `Smartmeter-V<version>.zip` asset.
14. Verify the GitHub Release page and the ZIP URL referenced by `release.cfg` or `prerelease.cfg`.
15. If a release is broken after publishing, create a new patch release instead of rewriting or deleting the published tag.

## Token-Efficient Codex Guidance

- Use a small/fast model for checklist execution, version bumps, release note drafting, and simple Git commands.
- Use a stronger model only if release validation fails, install/upgrade logs need diagnosis, or conflicting local changes require code-level judgment.
- Avoid re-reading the whole repo. Read only `plugin.cfg`, `release.cfg`, `prerelease.cfg`, `CHANGELOG.md`, and changed files.
