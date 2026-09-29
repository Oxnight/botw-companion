## What's new

- Releases are now assembled as drafts and published only after GitHub reports
  the exact two expected assets with the same size and SHA-256 digest as the
  packages tested by the workflow.
- Release tags must be annotated, match the project version, and identify the
  exact commit tested on Windows and macOS.
- The release job uses a dedicated protected environment and is the only job
  granted write access to repository contents.
- A failed post-upload verification removes only the unverified release and
  keeps the annotated tag available for diagnosis.

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
