# Windows validation

The Windows job in `.github/workflows/release.yml` runs:

1. Python tests and version checks;
2. browser flows in Chrome, Edge, and Firefox;
3. a native JoyConDSU and SDL3 build;
4. PyInstaller and Inno Setup packaging;
5. a real silent installation in a clean directory;
6. package self-tests, server startup without Python in `PATH`, and
   uninstallation.

Commits and pull requests run tests only. A `v*` tag publishes a release only
after both Windows and macOS jobs pass. The workflow first installs the version
in `packaging/UPGRADE_BASELINE`, performs the upgrade, and checks shortcuts and
persistent data. Hardware testing on Windows 10/11 remains recommended for
Joy-Con and emulator integration.
