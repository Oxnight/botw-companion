# Building JoyConDSU on Windows

The engine uses DSU protocol version 1001 on `127.0.0.1:26760`, timestamped SDL
events, robust calibration, bias correction, an unfiltered motion path, and the
same telemetry as the macOS engine.

The network layer selects native APIs automatically: POSIX sockets on macOS and
Winsock 2.2 on Windows. CRC32 is implemented in the engine and checked
byte-for-byte against the same vectors as the earlier implementation, so no
zlib DLL is required.

## Windows x64 build

Requirements: Windows 10 or 11 and Visual Studio 2022 Build Tools with C++ and
CMake.

From the repository root:

```powershell
.\tools\build_joycon_dsu_windows.ps1
```

CMake downloads the official SDL 3.4.14 source archive using a pinned SHA-256
digest, builds the engine, and produces:

```text
windows\native-dsu\JoyConDSU.exe
windows\native-dsu\SDL3.dll
windows\native-dsu\manifest.json
```

Players do not install SDL3 separately; the DLL is placed next to the
executable in the Windows package.

The script also copies these files to `botw_companion\dsu\windows`. The DSU
manager starts `JoyConDSU.exe` without a console, keeps `SDL3.dll` beside it,
and uses a named local Windows event for cooperative shutdown. Controls and
visible states match macOS.
