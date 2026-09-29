## What's new

- Verified Apple Silicon updates can now replace the installed macOS
  application after confirmation.
- The updater validates the DMG and application bundle, keeps a temporary copy
  of the previous version, and restores it if the new local server cannot
  start.
- Updates preserve Application Support data and stop BOTW Companion and
  JoyConDSU before changing the application bundle.

## Installation

- Windows 10/11 x64: download the `Setup.exe` file.
- macOS 14 or later on Apple Silicon: download the `.dmg` file, then drag BOTW
  Companion to Applications.

Python, offline data, JoyConDSU, and SDL3 are included.

## Updating

After a download is verified, select **Installer et redémarrer**. Windows uses
the visible Setup assistant. macOS uses a detached relay and may display its
normal authorization or Gatekeeper prompts. Neither platform removes the
previous installation before a replacement is ready.

Updating from alpha 39 to alpha 40 on macOS still requires replacing the app
from the DMG once, because alpha 39 does not contain the macOS relay. Assisted
macOS updates are available from alpha 40 onward.

An unavailable connection does not affect save analysis, the offline map,
guides, tracking, or JoyConDSU.
