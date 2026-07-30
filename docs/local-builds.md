# Local Build Packages

Use local packages for development, installation checks, and focused tests on a disposable LoxBerry. They are not release artifacts and must never be uploaded as an official release.

## Build commands

Build the current worktree:

```powershell
tools/build-local.ps1
```

Add a short reason when the package exists for a particular test:

```powershell
tools/build-local.ps1 -Purpose mapping-test
```

The script reads the version from `plugin.cfg`, writes the package below `dist/`, and prints its SHA-256 checksum. Like the GitHub release workflow, it builds with `git archive --worktree-attributes`, checks every ZIP entry, and verifies the exact `VERSION` line in the archived `plugin.cfg`. A temporary Git index captures the current worktree without changing the developer's real staging area. Files ignored by Git and paths marked `export-ignore` are not packaged, while Git file modes required by LoxBerry are retained.

## Naming

Local package names always use this form:

```text
Smartmeter-V<version>-local[-<purpose>]-<short-git-hash>[-dirty].zip
```

Examples:

```text
smartmeter-ng.0.0.33-local-781af34.zip
smartmeter-ng.0.0.33-local-mapping-test-781af34.zip
smartmeter-ng.0.0.33-local-mapping-test-781af34-dirty.zip
```

The purpose is normalized to lowercase ASCII words separated by hyphens. `dirty` means the package contains tracked modifications or non-ignored untracked files that were not part of the named commit. Build only after reviewing `git status --short`, because non-ignored untracked files are included so newly added plugin files can be tested before commit.

## Official releases

The suffixless name is reserved for official GitHub release assets:

```text
smartmeter-ng.0.0.33.zip
```

Official release ZIPs are created only by the GitHub Actions `Release asset` workflow from a pushed `Smartmeter-V<version>` tag. Developers must not create, rename, or publish an official-looking ZIP locally. Follow `docs/release-process.md` for releases.
