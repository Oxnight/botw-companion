# Installing and updating BOTW Companion

Players should use the files published on
[GitHub Releases](https://github.com/Oxnight/botw-companion/releases). Cloning
the repository and installing development tools are not required.

## Compatibility

| Platform | Package | Supported configuration |
| --- | --- | --- |
| Windows | `_Setup.exe` | Windows 10 version 1809 or later, Windows 11, x64 processor |
| macOS | `_macOS_arm64.dmg` | macOS 14 or later, Apple Silicon only |

The packages include Python, offline data and maps, JoyConDSU, SDL3, licenses,
icons, and the launcher. Python, Git, Node.js, CMake, Homebrew, Xcode, Visual
Studio, and PyCharm are not required.

## Windows

1. Download the file ending in `_Setup.exe`.
2. Run the installer. Keep the desktop-shortcut option enabled if desired.
3. Open **BOTW Companion** from the desktop or Start menu.

The per-user installation requires no administrator privileges and is stored
in:

```text
%LOCALAPPDATA%\Programs\BOTW Companion
```

The prerelease is not signed with a commercial certificate. If SmartScreen
shows a warning, confirm that the file came from
`github.com/Oxnight/botw-companion/releases` before using the additional
information option to run it.

## macOS Apple Silicon

1. Download the file ending in `_macOS_arm64.dmg`.
2. Open the DMG.
3. Drag **BOTW Companion** onto the **Applications** shortcut in the window.
4. Open BOTW Companion from Applications.

The prerelease uses an ad hoc signature and is not notarized. If macOS blocks
it, attempt to open it once, confirm that the DMG came from the official
Releases page, then use **System Settings > Privacy & Security > Open Anyway**.

## First launch

The launcher opens the local interface in the default browser. The initial
guide explains the detected save and optional motion controls. Use **Aide** to
open the complete help center or restart the guided tour.

If no save is found, see
[No save was detected](TROUBLESHOOTING.md#no-save-was-detected).

## Updating

BOTW Companion briefly checks GitHub Releases at startup. When a newer
compatible version is available, a banner offers the correct package. Use
**Vérifier les mises à jour** to retry manually.

When offline, the check times out quickly and silently. Save analysis, maps,
guides, tracking, and motion controls remain available. A download never starts
without a user action.

Install the new package over the existing version:

- on Windows, run the new `Setup.exe`;
- on macOS, replace the application in Applications with the copy from the new
  DMG.

There is no need to uninstall first. The package can also be downloaded
manually from Releases.

Manual tracking, routes, preferences, and backups remain in a separate user
directory:

```text
Windows: %LOCALAPPDATA%\BOTW Companion
macOS:   ~/Library/Application Support/BOTW Companion
```

Before publication, the workflow tests both a clean installation and an
upgrade from the reference version.

## Uninstalling

- Windows: use **Installed apps > BOTW Companion > Uninstall**.
- macOS: move **BOTW Companion.app** from Applications to the Trash.

Personal data is intentionally preserved. Export it first if needed, then
delete the user directory above to remove it.
