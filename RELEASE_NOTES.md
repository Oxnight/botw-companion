## What's new

- On Windows, a verified update can now be installed directly from the update
  banner.
- BOTW Companion and JoyConDSU stop cleanly before the visible Windows Setup
  assistant opens.
- After Setup finishes, BOTW Companion restarts and confirms that the new
  version is running before the downloaded installer is removed.

## Installation

- Windows 10/11 x64: download the `Setup.exe` file.
- macOS 14 or later on Apple Silicon: download the `.dmg` file, then drag BOTW
  Companion to Applications.

Python, offline data, JoyConDSU, and SDL3 are included.

## Updating

On Windows, select **Installer et redémarrer** after the download has been
verified. Setup remains visible, never forces a Windows restart, and keeps the
installer and its diagnostic log if the installation is cancelled or fails.

On macOS, the verified DMG is still installed manually. Assisted Apple Silicon
installation is planned for the next alpha.

An unavailable connection does not affect save analysis, the offline map,
guides, tracking, or JoyConDSU.
