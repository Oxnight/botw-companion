# macOS distribution

The macOS application supports Apple Silicon Macs running macOS 14 or later.

Players download the file ending in `_macOS_arm64.dmg`, open it, and drag
**BOTW Companion** to **Applications**. The package includes Python, all offline
resources, arm64 JoyConDSU, and `libSDL3.0.dylib`. It does not depend on the
source checkout, `.venv`, Homebrew, or Xcode.

## Building

The official build runs on an Apple Silicon GitHub Actions runner:

```bash
./tools/build_macos_app.sh
./tools/test_macos_installation.sh
```

The first script builds arm64 JoyConDSU and SDL3, packages the application with
PyInstaller, applies an ad hoc signature, and creates the DMG. The second mounts
the DMG, copies the application as a player would, checks architectures and
dependencies, upgrades the version in `packaging/UPGRADE_BASELINE`, and verifies
that Application Support data survives.

This prerelease is not signed with a Developer ID certificate or notarized.
macOS may require the user to allow it through **System Settings > Privacy &
Security > Open Anyway** after the first launch attempt.
