# Releasing BOTW Companion

Update these three files when preparing a release:

1. `botw_companion/VERSION`, the single source of the project version;
2. `RELEASE_NOTES.md`, a concise player-facing summary;
3. `CHANGELOG.md`, moving **Unreleased** entries under the new version and an
   ISO `YYYY-MM-DD` date.

Supported versions are `X.Y.Z`, `X.Y.Z-alpha.N`, `X.Y.Z-beta.N`, and
`X.Y.Z-rc.N`. Python metadata, native application versions, installer names,
and the GitHub release title are derived from this value.

Before committing, run:

```bash
python tools/audit_distribution.py
python tools/check_version_consistency.py
python -m unittest discover -s tests
```

The workflow uses a `github-release` environment for the only job with
`contents: write`. In repository settings, restrict that environment to version
tags and enable a required reviewer when the repository plan supports it. Do
not store signing keys in repository variables or make them available to pull
request jobs.

After the commit is pushed, Windows and macOS jobs run the test suite without
publishing installers. To validate both packages before tagging, run the
workflow manually with **Build and test installers** enabled. This run does not
publish a release.

When both jobs pass, create and push the matching annotated tag:

```bash
git tag -a vX.Y.Z-alpha.N -m "BOTW Companion X.Y.Z alpha N"
git push origin vX.Y.Z-alpha.N
```

The workflow rejects lightweight tags and annotated tags that do not identify
the exact tested commit. The tag builds both native packages and tests clean
installation and upgrade paths. It then uploads the two packages to a draft,
compares their size and SHA-256 digest with GitHub's asset metadata, and only
then publishes the Release. A failed verification removes the release created
by that run without deleting the annotated tag, instead of exposing partially
checked files. Alpha, beta, and release-candidate
tags become prereleases. A tag without a suffix, such as `v1.0.0`, becomes a
stable release.

The release must contain exactly the Windows installer and Apple Silicon DMG,
in addition to the source archives GitHub adds automatically. It must not
contain a checksum text file.

For a release candidate, complete
[`docs/RELEASE_CANDIDATE_VALIDATION.md`](docs/RELEASE_CANDIDATE_VALIDATION.md).
The automatic package run must validate upgrades from both the legacy baseline
in `packaging/LEGACY_UPGRADE_BASELINE` and the most recent published version in
`packaging/UPGRADE_BASELINE`. Do not tag `v1.0.0` until every applicable human
check is signed off and no release-blocking or data-loss issue remains.

Any change to a runtime, native library, data source, image, font, or bundled
tool requires an update to the applicable notices, `licenses/` contents, and
distribution audit before tagging.

After publication, verify the title, prerelease or stable status, both
installers, and changelog links. Never move a published tag; issue a new
version for every correction.

The complete trust boundaries, failure cases, and operator checks are recorded
in [`docs/UPDATE_THREAT_MODEL.md`](docs/UPDATE_THREAT_MODEL.md).
