## Release candidate

This build freezes the feature set planned for 1.0. It is intended for final
installation, upgrade, accessibility, save-analysis, and hardware testing.

RC 2 corrects draft-asset verification in the publication pipeline. GitHub's
temporary draft URLs are now checked before publication and the final tagged
URLs are checked immediately afterwards. Application behavior is unchanged.

Automated package validation now covers clean installation and upgrades from
both alpha 34 and the latest published alpha on Windows and macOS. No player-facing
features or completion rules have changed since alpha 41.

## Installation

- Windows 10/11 x64: download the `Setup.exe` file.
- macOS 14 or later on Apple Silicon: download the `.dmg` file, then drag BOTW
  Companion to Applications.

Python, offline data, JoyConDSU, and SDL3 are included.

## Updating

After a download is verified, select **Installer et redémarrer**. Windows uses
the visible Setup assistant. macOS uses the detached relay introduced in alpha
40 and may display its normal authorization or Gatekeeper prompts. Neither
platform removes the previous installation before a replacement is ready.

An unavailable connection does not affect save analysis, the offline map,
guides, tracking, or JoyConDSU.

## Known limitations

- The Windows installer is not commercially signed, so SmartScreen may ask for
  confirmation.
- The macOS application is not notarized, so Gatekeeper may require **Open
  Anyway** on first launch.
- macOS support is limited to Apple Silicon and macOS 14 or later.
