# Troubleshooting

First confirm that both BOTW Companion and its installer came from the
[official Releases page](https://github.com/Oxnight/botw-companion/releases).

## The application does not open

### Windows

- Start BOTW Companion again from the Start menu.
- If SmartScreen appears, verify the file's source before selecting the option
  to run it.
- Check `%LOCALAPPDATA%\BOTW Companion\launcher.log`.
- Reinstall the same version over the current installation. Personal data is
  preserved.

### macOS

- Confirm that the application is in Applications, not still inside the DMG.
- After the first blocked launch, use **System Settings > Privacy & Security >
  Open Anyway**.
- Check `~/Library/Application Support/BOTW Companion/launcher.log`.
- Replace the application with a fresh copy from the DMG.

## The interface does not appear

The interface normally uses `http://127.0.0.1:8765`. A second launch reuses the
running server. If no browser window appears:

1. open that address manually;
2. close any older BOTW Companion instance;
3. start the application again;
4. check `launcher.log` for a port conflict or server failure.

Do not expose this port to the network or replace `127.0.0.1` with a remote
address.

## No save was detected

1. Run BOTW in Ryujinx or Cemu and create a recent in-game save.
2. Confirm that the emulator uses its normal data directory or a portable
   location available to the current account.
3. In Ryujinx, use the menu action that opens the game's user save directory
   and confirm that it exists.
4. In Cemu, check the `mlc_path` in `settings.xml` when using a custom path.

A development checkout can pass a specific path to the `interface` command.
The installed application uses automatic discovery to avoid storing a fragile
save path.

## Progress appears out of date

- Create an in-game save; an emulator save state is not sufficient.
- Check the slot, normal or Master Mode, emulator, and path shown in the save
  summary.
- When multiple emulators are installed, BOTW Companion selects the newest
  valid source.
- Do not edit `.sav` files directly.

## An update download stops

- Keep BOTW Companion open and select **Réessayer** after the connection
  returns. A valid partial download is retained.
- If the banner reports insufficient disk space, free space on the volume that
  contains the application data directory before retrying.
- A security verification failure removes the rejected package. Download it
  again only from the update banner or the official Releases page.
- Save analysis, maps, guides, tracking, and JoyConDSU remain available while
  update checks or downloads are unavailable.

## DSU motion controls do not work

- Confirm that the selected source reports both a gyroscope and accelerometer.
- Keep the controller still until calibration completes.
- Use exactly `127.0.0.1` and port `26760` in the emulator.
- Close other DSU servers that may already use port 26760.
- Reconnect the controller over USB or Bluetooth, then refresh the source list.
- Review the diagnostics and the `joycon-dsu.log` path shown in the interface.

A controller may expose buttons without exposing motion sensors to SDL3. BOTW
Companion will not list it as a compatible motion source in that case.

## Preparing a bug report

Include:

- the exact BOTW Companion version;
- the operating system and version;
- Ryujinx or Cemu;
- minimal reproduction steps;
- the displayed error and relevant final log lines.

Remove usernames and personal paths. Never publish a save or vulnerability
details. Follow [`SECURITY.md`](../SECURITY.md) for security reports.
