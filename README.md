# BOTW Companion

BOTW Companion reads local *The Legend of Zelda: Breath of the Wild* save
files from Ryujinx or Cemu and helps players track a complete playthrough.

This is an unofficial fan project. It is not affiliated with, endorsed by,
sponsored by, or supported by Nintendo.

The offline interface is available in French and English. Choose a language
from the Application controls; help, the guided tour, and game guides follow
that selection. Personal notes and route names retain the text you entered.

## Download

Download the current version from
[GitHub Releases](https://github.com/Oxnight/botw-companion/releases).

| Platform | Download |
| --- | --- |
| Windows 10/11 x64 | the file ending in `_Setup.exe` |
| macOS 14 or later on Apple Silicon | the file ending in `_macOS_arm64.dmg` |

Both packages are self-contained. They include Python, the offline data and
map, JoyConDSU, SDL3, icons, and the launcher. Players do not need to clone the
repository or install development tools.

See the [installation and update guide](docs/INSTALLATION.md) for complete
instructions, including SmartScreen and Gatekeeper warnings.

## Features

- Automatic discovery of the newest BOTW save from Ryujinx or Cemu.
- Save-slot summary with mode, date, emulator, and platform.
- Tracking for the official map percentage, shrines, quests, Koroks, gear,
  bosses, DLC, and other objectives.
- Offline solutions for 152 quests, 900 Koroks, chests, shrines, and bosses.
- Filters and markers on a high-resolution offline map.
- Persistent manual tracking, notes, and route planning.
- Import, export, and local backups of Companion data.
- Optional release checks with verified downloads and assisted installation.
- Blood Moon timing estimated from the save counter.
- A Cemuhook/DSU motion server for Ryujinx and Cemu, with calibration and
  signal-quality diagnostics.
- Keyboard navigation, local help, and reduced-motion support.

## Documentation

- [Installation and updates](docs/INSTALLATION.md)
- [DSU motion setup](docs/DSU.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Development and tests](docs/DEVELOPMENT.md)
- [Update security](docs/UPDATE_SECURITY.md)
- [Release process](docs/RELEASE_PROCESS.md)
- [Contributing](CONTRIBUTING.md)

## Data and privacy

The server listens only on `127.0.0.1`. Saves and progress data are never sent
to a remote service. BOTW Companion may briefly query the public GitHub
Releases endpoint to report an available update. After explicit consent, the
local server can download the matching installer into the application data
directory, resume an interrupted transfer, and verify GitHub's SHA-256 digest.
These operations never block offline use.

Personal data is stored outside the application:

```text
Windows: %LOCALAPPDATA%\BOTW Companion
macOS:   ~/Library/Application Support/BOTW Companion
```

Upgrades and uninstallations leave this data in place. See
[`PRIVACY.md`](PRIVACY.md) for details.

## Security and licensing

- [`SECURITY.md`](SECURITY.md) explains how to report a vulnerability without
  exposing sensitive data.
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) lists bundled components
  and build tools.
- [`DATA_SOURCES.md`](DATA_SOURCES.md) records the sources of the data and map.
- [`licenses/`](licenses/) contains the required full license texts.

Project-authored code is available under the MIT License. That license does not
grant rights to trademarks, assets, or content owned by Nintendo or other
third parties. Redistribution permission for the game-extracted offline map
has not been established; see the [data source register](DATA_SOURCES.md).
