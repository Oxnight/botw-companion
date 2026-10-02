## Release candidate

RC 7 improves update handoffs on Windows and macOS. Repeated clicks cannot
start multiple installers, interrupted HTTP responses can be retried, and
download cleanup preserves installation diagnostics.

Windows assisted updates target the existing application folder. The macOS
relay reopens the installed application after an error before replacement,
stops the new instance before restoring a backup, and keeps that backup if
shutdown cannot be confirmed. Elevated replacement returns to the user's
session for relaunch.

The update panel keeps its existing appearance. The All and None filter
actions are lower and slightly wider.

No save-analysis, completion, map, guide, tracking, or JoyConDSU result has
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
