# Privacy

BOTW Companion runs locally. It has no account system, advertising,
telemetry, or analytics.

## Data read by the application

The application searches for local Ryujinx or Cemu saves, then reads the
selected BOTW slot and its thumbnail. The motion engine reads sensors from the
selected controller only while DSU is enabled.

## Data written by the application

Manual tracking, routes, preferences, backups, and logs remain in:

- Windows: `%LOCALAPPDATA%\BOTW Companion\`
- macOS: `~/Library/Application Support/BOTW Companion/`

Uninstalling the application intentionally leaves this directory in place. To
remove all Companion data, close the application and delete that directory
manually. This does not affect emulator saves.

## Network access

The local server listens only on `127.0.0.1`. Save analysis, maps, guides, and
tracking data are never sent over the Internet.

At startup, BOTW Companion may query the public release list for
`github.com/Oxnight/botw-companion`. The request contains no save data,
progress, or personal preference. It has a short timeout, and a failure never
disables offline features. The user can retry with **Vérifier les mises à
jour**.

A download starts only after a user action and points directly to the Windows
Setup or Apple Silicon DMG published on GitHub.
