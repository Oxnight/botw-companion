## Release candidate

RC 6 keeps the guided-tour category filters on the left, with their explanation
on the right when there is enough room. The All and None filter actions now
have a subtle border so they are easier to find.

The macOS launcher no longer mistakes recently closed HTTP connections for an
unrelated application occupying the local port. Relaunch can reuse that port
without waiting for the TCP cooldown, and the launchers briefly wait for an
instance already finishing shutdown. An unrelated listener is never stopped.

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
