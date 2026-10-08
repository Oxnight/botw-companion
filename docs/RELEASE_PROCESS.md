# Release process

`botw_companion/VERSION` is the single application version source. Supported
formats are `X.Y.Z`, `X.Y.Z-alpha.N`, `X.Y.Z-beta.N`, and `X.Y.Z-rc.N`.
Python metadata, bundle versions, installer filenames, and release titles are
derived by `tools/release_metadata.py`.

## Prepare the source

Update the version and the published reference in `packaging/UPGRADE_BASELINE`.
The reference must be a stable release at or after the first stable version,
and older than the build. Once newer stable releases exist, advance this file
to the latest supported stable release. The original stable release remains
the minimum compatibility reference and is also tested when it differs.

The first stable build is the only exception: its baseline equals its version,
and no previous release is downloaded. Native validation installs the built
package and replaces it with itself, retaining the same restart, data,
rollback and interruption checks. This is bootstrap validation, not evidence
of upgrading an older executable. Missing references on later releases fail
validation; they do not activate bootstrap mode.

Run the checks in [DEVELOPMENT.md](DEVELOPMENT.md), including the complete
Python suite, generated English assets, localization, and browser flows. Review
changes to dependencies, bundled material, and licenses before distribution.
The unresolved map rights in [DATA_SOURCES.md](../DATA_SOURCES.md) require a
maintainer decision; passing tests does not resolve them.

Release history and descriptions live only in GitHub Releases. The workflow
uses GitHub's generated release notes; maintainers can edit the description
directly on the Release. No tracked changelog or release-note file is required.

## Validate native packages

Ordinary pushes and pull requests run tests without building installers. Before
tagging a reviewed commit, run the existing workflow with package validation:

```bash
gh workflow run release.yml --ref master -f validate_packages=true
```

This dispatch builds and tests Windows x64 and macOS Apple Silicon packages
without starting the publish job. Both native jobs must pass. They validate
clean installation, package replacement, restart, rollback where supported,
and preservation of Companion data. Subsequent builds also validate upgrades
from the selected stable release and the minimum stable reference.

Both native scripts use a shared synthetic user-data fixture for tracking,
routes, preferences and an export. Its schemas match the established data
formats and need no old executable or network. These tests preserve data
compatibility alongside the native package replacement and update checks.

Also test the actual packages on supported hardware: launch and reopen from
shortcuts or Dock, both languages, offline use, emulator saves, motion controls,
and update recovery. Hosted tests cannot validate physical controllers,
Gatekeeper or SmartScreen decisions, or every filesystem and permission setup.

## Publication controls

The `github-release` environment belongs to the tag-only publish job.
Publication requires a pushed version tag; manual dispatches never publish.
Restrict the environment to version tags and configure required review where
available. Other jobs use `contents: read`; only publication uses
`contents: write`. Keep signing credentials out of pull-request jobs.

Once the matching commit has passed validation, create an annotated version
tag. For example, with the intended version substituted:

```bash
git tag -a vX.Y.Z -m "BOTW Companion X.Y.Z"
git push origin refs/tags/vX.Y.Z
```

The tag workflow requires the version, annotated tag, checked-out commit, and
workflow commit to agree. It rebuilds and validates both native packages before
creating a draft with exactly two assets: the Windows Setup executable and
Apple Silicon DMG. Their sizes and SHA-256 digests must match GitHub metadata
before publication. No checksum text file is published. GitHub provides source
archives separately.

Alpha, beta, and release-candidate versions are prereleases. Versions without a
suffix are stable and become the latest release. A failed verification removes
only the release created by that run and leaves its tag in place.

Never move a published tag or replace its assets. Publish a new version when
bytes change. After publication, confirm the release status and download both
assets. Current packages use an ad hoc macOS signature and no commercial
Windows signature; notarization and trusted signing are not provided.

See [UPDATE_SECURITY.md](UPDATE_SECURITY.md) for the release and client trust
boundaries.
