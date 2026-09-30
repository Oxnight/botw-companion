# Changelog

All notable changes to BOTW Companion are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0-rc.2] - 2026-09-30

### Fixed

- Accept GitHub's repository-scoped temporary download URLs while a Release is
  still a draft, then require the final immutable tag URLs after publication.
- Bind draft verification to the exact Release and asset database IDs in
  addition to names, media types, sizes, and GitHub-provided SHA-256 digests.
- Wait for all three linked stylesheets to load before running browser
  accessibility audits, without relying on platform-dependent computed colors
  or native control dimensions.

## [1.0.0-rc.1] - 2026-09-29

### Changed

- Froze the planned 1.0 feature set for final validation.
- Validate clean installation and upgrades from both alpha 34 and the latest
  published alpha on Windows and macOS Apple Silicon.
- Track draft publication by its immutable GitHub Release database ID so asset
  verification does not depend on the public tag endpoint.

### Quality

- Added a release-candidate sign-off record for native hardware, emulators,
  real controllers, update recovery, data retention, and product review.
- Made 200% browser zoom, reduced motion, offline operation, and simulated slow
  update transfers explicit release gates, using the effective CSS viewport for
  standards-compliant reflow validation.

## [0.40.0-alpha.41] - 2026-09-29

### Changed

- Build releases only from an annotated version tag that identifies the exact
  commit tested by both native jobs.
- Upload packages to a draft first and publish it only after verifying the
  exact asset set, sizes, URLs, media types, and GitHub-provided SHA-256
  digests against the local build outputs.
- Route the only write-enabled job through the dedicated `github-release`
  environment and disable persisted checkout credentials in every job.
- Remove a release created by a failed verification run while preserving its
  annotated tag for diagnosis.

### Security

- Added automated policy tests for full-SHA action pins, least-privilege token
  permissions, immutable tag validation, and verified draft publication.
- Documented release and client-update trust boundaries, mitigations, recovery
  paths, and residual signing limitations.
- Added explicit update-channel tests for prerelease-to-prerelease,
  prerelease-to-stable, stable-to-stable, and stable rejection of prereleases.

## [0.40.0-alpha.40] - 2026-09-29

### Added

- Assisted Apple Silicon updates using a detached, packaged relay after the
  verified DMG download.
- A transactional application replacement with a temporary backup, automatic
  restart health check, and rollback when the new bundle cannot start.

### Security

- Revalidate the DMG name, size, GitHub-provided SHA-256 digest, disk image,
  bundle identifier, version fields, ad hoc signature, arm64 Mach-O slices,
  and linked paths before replacing the installed application.
- Mount update images read-only in a private location, request normal macOS
  authorization when Applications is not writable, and leave Gatekeeper
  protections enabled.

## [0.40.0-alpha.39] - 2026-09-10

### Added

- Assisted Windows updates that hand a verified installer to an external,
  self-contained relay before the running application exits.
- Visible Setup, installation diagnostics, cancellation recovery, and a
  verified application restart after a successful upgrade.

### Security

- Revalidate the installer path, name, size, and GitHub-provided SHA-256
  digest immediately before execution.
- Stop the local server and JoyConDSU cleanly, forbid forced application
  closure and Windows restarts, and delete the installer only after the new
  version answers its local health check.

## [0.40.0-alpha.38] - 2026-09-09

### Added

- Managed update downloads with progress, cancellation, bounded retries, and
  HTTP range resumption.
- Recovery of verified downloads after the Companion restarts.

### Security

- Validate the release repository, version, platform asset, media type, size,
  redirect hosts, and GitHub-provided SHA-256 digest before accepting a
  package.
- Keep partial and verified packages in the user data directory and publish a
  completed download only through an atomic rename.

## [0.40.0-alpha.37] - 2026-09-09

### Changed

- Rewrote public project documentation in concise American English.
- Translated existing comments and docstrings while keeping the application
  and player-facing messages in French.

### Security

- Added repository hygiene and public-language checks to the distribution
  audit.

## [0.40.0-alpha.36] - 2026-09-09

### Added

- Twelve-chapter offline help covering every major Companion feature.
- Nine-step guided tour that highlights real controls without triggering
  actions or changing data.
- Tour resume support, contextual help by chapter, and completed tutorial
  version tracking.

### Accessibility

- Full keyboard navigation, focus trapping and restoration, step
  announcements, and reduced-motion support.

## [0.40.0-alpha.35] - 2026-09-09

### Changed

- Split save synchronization controls from general application actions.
- Enlarged progress rings and made their type responsive to long values and
  narrow screens.

## [0.40.0-alpha.34] - 2026-09-09

### Added

- Non-blocking checks for new GitHub releases.
- Guided Windows Setup or Apple Silicon DMG download and a manual update check.

### Fixed

- Read persistent Ganon victory state from `caption.sav`.
- Detect the final Champions' Ballad map marker from durable save evidence.
- Removed the three red strands beneath the Blood Moon.

## [0.40.0-alpha.33] - 2026-09-08

### Added

- Separate installation, DSU, troubleshooting, and development guides.
- Contribution instructions and a public release history.
- Automated documentation structure and link checks.

### Changed

- Refocused the README on the project and quick start.
- Bundled player documentation in the self-contained applications.

## [0.40.0-alpha.32] - 2026-09-08

### Added

- Full Python 3.12 and SDL3 license texts in both applications.
- Data provenance, privacy, and security policies.
- Blocking audits of bundled components and release assets.

## [0.40.0-alpha.31] - 2026-09-08

### Added

- A first-launch guide that can be reopened from the interface.
- Keyboard navigation, visible focus, screen-reader announcements, and
  reduced-motion support.
- Automated WCAG 2.2 AA checks in browser tests.

## [0.40.0-alpha.30] - 2026-09-08

### Changed

- Made the workflow independent of a specific version number.
- Derived tags, release titles, and installer names from one version source.
- Limited commits and pull requests to tests; releases require a tag.

## [0.40.0-alpha.29] - 2026-09-08

### Changed

- Validated clean installs and upgrades from alpha 24 on Windows and macOS.
- Verified preservation of manual tracking, routes, preferences, and
  shortcuts.

## [0.40.0-alpha.28] - 2026-09-08

### Changed

- Rebuilt the Blood Moon visual states and animation.
- Added automated visual references to browser tests.

## [0.40.0-alpha.27] - 2026-09-08

### Security

- Required a session token for sensitive local actions.
- Validated request host, origin, and context.
- Added security headers and rejected remote origins.

## [0.40.0-alpha.26] - 2026-09-08

### Changed

- Completed the French localization and recursive terminology audit.
- Precompiled French resources to retain fast offline startup.

## [0.40.0-alpha.25] - 2026-09-08

### Fixed

- Detected persistent Ganon victory through `GameClear`.
- Kept official map and Companion completion formulas independent and
  deduplicated.
- Listed items still preventing 100% completion.

## [0.40.0-alpha.24] - 2026-09-07

### Added

- Self-contained application and DMG for macOS 14 or later on Apple Silicon.
- Bundled Python, JoyConDSU, and SDL3 without requiring Homebrew or Xcode on a
  player's Mac.

## [0.40.0-alpha.23] - 2026-09-02

### Added

- Self-contained Windows x64 installer with Python, JoyConDSU, and SDL3.
- Desktop and Start menu shortcuts with user-data preservation on upgrade.

[Unreleased]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.37...HEAD
[0.40.0-alpha.37]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.36...v0.40.0-alpha.37
[0.40.0-alpha.36]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.35...v0.40.0-alpha.36
[0.40.0-alpha.35]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.34...v0.40.0-alpha.35
[0.40.0-alpha.34]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.33...v0.40.0-alpha.34
[0.40.0-alpha.33]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.32...v0.40.0-alpha.33
[0.40.0-alpha.32]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.31...v0.40.0-alpha.32
[0.40.0-alpha.31]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.30...v0.40.0-alpha.31
[0.40.0-alpha.30]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.29...v0.40.0-alpha.30
[0.40.0-alpha.29]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.28...v0.40.0-alpha.29
[0.40.0-alpha.28]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.27...v0.40.0-alpha.28
[0.40.0-alpha.27]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.26...v0.40.0-alpha.27
[0.40.0-alpha.26]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.25...v0.40.0-alpha.26
[0.40.0-alpha.25]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.24...v0.40.0-alpha.25
[0.40.0-alpha.24]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.23...v0.40.0-alpha.24
[0.40.0-alpha.23]: https://github.com/Oxnight/botw-companion/releases/tag/v0.40.0-alpha.23
