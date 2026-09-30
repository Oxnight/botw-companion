# Release candidate validation

This document is the sign-off record for a release candidate. Automated checks
reduce risk but do not replace the native-hardware checks below. Leave an item
unchecked until it has been reproduced on the stated system.

## Release identity

- [ ] The candidate commit is frozen except for release-blocking fixes.
- [ ] `botw_companion/VERSION`, the tag, release title, package names, changelog,
  and release notes agree.
- [ ] The annotated tag identifies the commit that passed both native jobs.
- [ ] The Release contains one Windows Setup executable and one Apple Silicon
  DMG, plus GitHub's automatic source archives, and no checksum text file.
- [ ] GitHub shows the release as a prerelease.

## Automated gates

- [ ] Python tests, version checks, distribution audits, and language audits pass.
- [ ] Chromium, Firefox, and WebKit flows pass with axe-core, keyboard,
  responsive layout, 200% zoom, and reduced motion checks.
- [ ] Windows x64 and macOS arm64 packages build and pass their self-tests.
- [ ] Clean installation and upgrades from alpha 34 and the latest published alpha pass
  on both platforms while preserving user data.
- [ ] Simulated updates cover offline, slow, interrupted, resumed, corrupted,
  wrong-digest, restart-failure, and rollback paths.
- [ ] Save analysis, the offline map, guides, tracking, and JoyConDSU require no
  network connection.

## Windows 10 and Windows 11

Record the Windows version, computer model, emulator version, controller, and
tester beside each completed run.

| Check | Windows 10 1809+ x64 | Windows 11 x64 |
| --- | --- | --- |
| Clean PC without Python, Git, Node, Visual Studio, CMake, or SDL | [ ] | [ ] |
| Setup, Start menu shortcut, desktop shortcut, and first launch | [ ] | [ ] |
| Ryujinx save discovery, analysis, and live synchronization | [ ] | [ ] |
| Cemu save discovery, analysis, and live synchronization | [ ] | [ ] |
| Real-controller JoyConDSU input and emulator configuration | [ ] | [ ] |
| Assisted update, verified restart, and cancellation recovery | [ ] | [ ] |
| Upgrade and reinstall preserve Companion data | [ ] | [ ] |
| Uninstall preserves personal data and removes application files | [ ] | [ ] |

Windows 10 evidence:

- OS build:
- Computer:
- Ryujinx/Cemu versions:
- Controller:
- Tester and date:
- Notes or issue links:

Windows 11 evidence:

- OS build:
- Computer:
- Ryujinx/Cemu versions:
- Controller:
- Tester and date:
- Notes or issue links:

## macOS Apple Silicon

Use two physical Apple Silicon Macs and two supported macOS versions. Neither
test machine may depend on Python, Homebrew, or Xcode.

| Check | Mac and macOS A | Mac and macOS B |
| --- | --- | --- |
| DMG verification, drag to Applications, Gatekeeper, and first launch | [ ] | [ ] |
| Launch from Applications and from a user-writable folder | [ ] | [ ] |
| Ryujinx save discovery, analysis, and live synchronization | [ ] | [ ] |
| Cemu check recorded according to actual platform compatibility | [ ] | [ ] |
| Real-controller JoyConDSU input and emulator configuration | [ ] | [ ] |
| Assisted update, verified restart, and cancellation recovery | [ ] | [ ] |
| Forced restart failure restores the previous application | [ ] | [ ] |
| Upgrade and reinstall preserve Application Support data | [ ] | [ ] |

Mac A evidence:

- macOS and chip:
- Installation location:
- Ryujinx/Cemu versions or compatibility note:
- Controller:
- Tester and date:
- Notes or issue links:

Mac B evidence:

- macOS and chip:
- Installation location:
- Ryujinx/Cemu versions or compatibility note:
- Controller:
- Tester and date:
- Notes or issue links:

## Product review

- [ ] A real base-game save and a real DLC save produce the expected totals,
  categories, map markers, quest state, Ganon state, and important screens.
- [ ] Save synchronization and application actions are understandable without
  verbal instructions.
- [ ] A new user completes the tutorial and any unclear step is recorded.
- [ ] Every tested failure shows a concrete next action and leaves a useful log.
- [ ] Update, reinstall, and uninstall tests never silently remove personal data.
- [ ] French player-facing text and English public documentation were reviewed.

## Decision

- Candidate tag:
- Candidate commit:
- Blocking issues:
- Accepted known limitations:
- Windows sign-off:
- macOS sign-off:
- Product sign-off:
- Decision and date:
