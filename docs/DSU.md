# Setting up DSU motion controls

BOTW Companion includes a Cemuhook/DSU-compatible server. It sends motion data
from a supported controller to Ryujinx or Cemu on `127.0.0.1:26760`.

## Controllers

The engine uses SDL3 and offers only sources that provide both a gyroscope and
an accelerometer. A Joy-Con pair is grouped as one grip-style source. Actual
support depends on the hardware, connection, operating system, and SDL3 driver.

## In BOTW Companion

1. Connect the controller over Bluetooth or USB.
2. Open **Gyroscope universel**.
3. Select an available source.
4. Choose **Activer**.
5. Keep the controller still during calibration.
6. Wait for **Gyroscope prêt**.

Diagnostics include sample rate, jitter, sample age, calibration quality,
anomalies, and network state.

## In the emulator

Configure a Cemuhook/DSU motion source with:

```text
Host: 127.0.0.1
Port: 26760
Slot: 1
```

Menu names vary by emulator version. In Cemu, the source is in the Wii U
GamePad input or motion settings. Ryujinx versions with Cemuhook support expose
it in controller motion settings.

DSU carries motion only. Configure buttons and sticks normally in the emulator.

## Shutdown and local data

The DSU engine is disabled by default and starts only after an action in the
interface. Its log is stored as `joycon-dsu.log` in the BOTW Companion data
directory; the interface shows the exact path.

For controller detection or port errors, see
[DSU motion controls do not work](TROUBLESHOOTING.md#dsu-motion-controls-do-not-work).
