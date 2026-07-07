# Release Process

Use this checklist when the user asks to create a release. Keep the process concise and avoid broad repo analysis unless a check fails.

## Scope

A release means:

- all intended changes are committed and pushed;
- plugin versions and update metadata are bumped;
- release notes are prepared in `CHANGELOG.md`;
- a Git tag is created and pushed;
- a GitHub Release is created with the release notes.

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
Smartmeter-V2.0.0.10
```

## Checklist

1. Confirm target version and whether this is a stable release or prerelease.
2. Check `git status --short`; do not include unrelated local changes.
3. Update version metadata in the files listed above.
4. Confirm user documentation is current for changed behavior, setup, configuration, dependencies, and upgrade steps. Check `docs/Readme.md`, `docs/User-Guide.de.md`, and `docs/User-Guide.en.md` when user-facing behavior changed.
5. Move the relevant `CHANGELOG.md` entries from `Unreleased` to the target version and date.
6. Run cheap validation:
   - `perl -c` for changed Perl files;
   - `php -l` for changed PHP files;
   - shell syntax checks where available;
   - inspect changed release metadata with `git diff`.
7. Ensure the required GitHub Actions `Perl and PHP syntax` check passes on the release pull request before merging to `master`.
8. Run a plugin install or upgrade smoke test on LoxBerry when the release changes installation, upgrade, dependencies, services, cron jobs, or core runtime behavior.
9. Commit the release changes.
10. Push the branch.
11. Create an annotated tag on the pushed release commit:

```powershell
git tag -a Smartmeter-V<version> -m "Smartmeter V<version>"
git push origin Smartmeter-V<version>
```

12. Create the GitHub Release for the tag:
   - title: `Smartmeter V<version>`;
   - stable releases must not be marked as prerelease;
   - prereleases must be marked as prerelease;
   - paste the matching `CHANGELOG.md` version entry as release notes.
13. Verify the GitHub Release page and the tag ZIP URL referenced by `release.cfg`.
14. If a release is broken after publishing, create a new patch release instead of rewriting or deleting the published tag.

## Token-Efficient Codex Guidance

- Use a small/fast model for checklist execution, version bumps, release note drafting, and simple Git commands.
- Use a stronger model only if release validation fails, install/upgrade logs need diagnosis, or conflicting local changes require code-level judgment.
- Avoid re-reading the whole repo. Read only `plugin.cfg`, `release.cfg`, `prerelease.cfg`, `CHANGELOG.md`, and changed files.
