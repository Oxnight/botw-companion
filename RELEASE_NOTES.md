## Release candidate

RC 4 fixes the update connection failure seen in the self-contained macOS
application. Windows and macOS now carry their own reviewed certificate store,
combine it with system trust for managed networks, use it for both release
checks and installer downloads, and run a real GitHub
HTTPS check from the packaged application during the release workflow.

The interface now shows save dates and times in the computer's current time
zone. Pointer clicks no longer leave keyboard-style yellow outlines, while
keyboard focus remains visible. The help center and guided tour cover the
left-hand category filters, and tour cards avoid the highlighted area. The
update action also remains on one line.

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
