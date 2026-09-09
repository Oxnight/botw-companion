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

After the commit is pushed, Windows and macOS jobs run the test suite without
publishing installers. To validate both packages before tagging, run the
workflow manually with **Build and test installers** enabled. This run does not
publish a release.

When both jobs pass, create and push the matching annotated tag:

```bash
git tag -a vX.Y.Z-alpha.N -m "BOTW Companion X.Y.Z alpha N"
git push origin vX.Y.Z-alpha.N
```

The tag builds both native packages, tests clean installation and upgrade
paths, and then publishes the release. Alpha, beta, and release-candidate tags
become prereleases. A tag without a suffix, such as `v1.0.0`, becomes a stable
release.

The release must contain exactly the Windows installer and Apple Silicon DMG,
in addition to the source archives GitHub adds automatically. It must not
contain a checksum text file.

Any change to a runtime, native library, data source, image, font, or bundled
tool requires an update to the applicable notices, `licenses/` contents, and
distribution audit before tagging.

After publication, verify the title, prerelease or stable status, both
installers, and changelog links. Never move a published tag; issue a new
version for every correction.
