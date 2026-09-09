# BOTW Companion

BOTW Companion reads local *The Legend of Zelda: Breath of the Wild* save
files from Ryujinx or Cemu and helps players track a complete playthrough.

This is an unofficial fan project. It is not affiliated with, endorsed by,
sponsored by, or supported by Nintendo.

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
- Optional release checks with a guided download for the current platform.
- Blood Moon timing estimated from the save counter.
- A Cemuhook/DSU motion server for Ryujinx and Cemu, with calibration and
  signal-quality diagnostics.
- Keyboard navigation, local help, and reduced-motion support.

## Completion metrics

The interface shows two independent metrics:

- the **official map percentage**, where every marker is worth `100 / 1207`
  in the base game or `100 / 1224` with the Expansion Pass;
- the **Companion completion profile**, calculated as
  `100 × unique automatic objectives completed / unique automatic objectives in the profile`.

The main profile contains 3,400 objectives for the base game and 3,565 with
the DLC. Activities without durable evidence in the save remain available for
manual tracking but do not block 100%. Amiibo are kept outside the main
profile. The interface lists every item that still prevents 100% completion.

The first Ganon victory is detected from the persistent `GameClear` marker,
not only from the temporary state of the final quest after the credits.

## Documentation

- [Installation and updates](docs/INSTALLATION.md)
- [DSU motion setup](docs/DSU.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Development and tests](docs/DEVELOPMENT.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Release process](RELEASING.md)

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
third parties.
