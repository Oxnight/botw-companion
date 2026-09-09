# Windows distribution

Players download the file ending in `_Setup.exe` from
[GitHub Releases](https://github.com/Oxnight/botw-companion/releases). The x64
installer includes Python, offline resources, JoyConDSU, and SDL3, and can
create desktop and Start menu shortcuts.

## Building

The official build runs on the `windows-2022` runner in
`.github/workflows/release.yml`. To reproduce it on Windows x64:

```powershell
.\tools\build_windows_app.ps1
.\tools\test_windows_installation.ps1
```

The installer is written to:

```text
dist\installer\BOTW_Companion_<version>_Setup.exe
```

It installs per user in `%LOCALAPPDATA%\Programs\BOTW Companion`. Personal data
remains separate in `%LOCALAPPDATA%\BOTW Companion`.

`Installer BOTW Companion.cmd`, `Installer BOTW Companion.ps1`, and
`BOTW Companion.vbs` remain available only for development from a checkout with
a `.venv` environment.
