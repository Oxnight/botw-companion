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

A download starts only after a user action and requests the Windows Setup or
Apple Silicon DMG published on GitHub. Release checks use `api.github.com`;
downloads start on `github.com` and may redirect to `objects.githubusercontent.com`
or `release-assets.githubusercontent.com`. GitHub receives ordinary connection
metadata such as the device's public IP address, not save or tracking data.

DSU traffic stays on `127.0.0.1:26760`. Opening a source link in a guide or the
Releases page uses the browser and contacts that external site. These links are
not fetched to display offline guides.

Logs remain local and can include filesystem paths, device diagnostics, and
update errors. Exports include the notes and route names entered by the user.
Redact personal content before sharing either. There is no remote crash-report
upload.
