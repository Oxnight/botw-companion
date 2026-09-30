## Release candidate

RC 3 fixes update checks on slower connections. The previous build could stop
waiting before GitHub returned its release data, especially on macOS. Checks
now have a realistic time budget, retry one temporary network failure, and
report rate limits without repeatedly contacting GitHub. BOTW Companion still
starts and works normally when the network is unavailable.

The Windows updater now validates the saved release metadata as well as the
installer itself, both before the application closes and again in the detached
updater. macOS update-state files are restricted to the current user. Package
validation covers clean installs, upgrades from RC 2, and the legacy alpha 34
migration path on both supported platforms.

No save-analysis, completion, map, guide, tracking, or JoyConDSU behavior has
changed in this release candidate.

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

If a check or download is interrupted, use **Réessayer** after the connection
returns. Valid partial data is retained. An unavailable connection does not
affect save analysis, the offline map, guides, tracking, or JoyConDSU.

## Known limitations

- The Windows installer is not commercially signed, so SmartScreen may ask for
  confirmation.
- The macOS application is not notarized, so Gatekeeper may require **Open
  Anyway** on first launch.
- macOS support is limited to Apple Silicon and macOS 14 or later.
