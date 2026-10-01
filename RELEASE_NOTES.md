## Release candidate

RC 5 keeps the complete guided-tour target visible without letting the
explanation card cover it. When there is not enough room for both at their
original size, the tour shows a complete, proportionally scaled overview
beside or above the card. This visual overview does not change application data.

Moving between steps now uses a short fade transition. Devices requesting
reduced motion switch immediately. Repeated clicks during a transition cannot
skip steps, and closing the tour cancels any running animation.

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
