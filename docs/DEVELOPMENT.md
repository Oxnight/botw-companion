# Developing BOTW Companion

This guide is for source checkouts. Players should use the packages described
in [`INSTALLATION.md`](INSTALLATION.md).

## Requirements

- Git
- Python 3.10 or later; Python 3.12 is recommended
- Node.js and npm only for browser tests

Clone the project:

```bash
git clone https://github.com/Oxnight/botw-companion.git
cd botw-companion
```

Create the environment with `uv`:

```bash
uv sync
```

Or use Python directly:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
```

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

## Running from source

```bash
.venv/bin/python -m botw_companion interface
```

To use a specific save directory:

```bash
.venv/bin/python -m botw_companion interface "/path/to/slot"
```

Other commands:

```bash
.venv/bin/python -m botw_companion analyse
.venv/bin/python -m botw_companion reste --categorie sanctuaires
.venv/bin/python -m botw_companion surveille --intervalle 3
.venv/bin/python -m botw_companion --help
```

Command names remain French because they are part of the player-facing
application.

## Python tests and audits

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python tools/audit_distribution.py
.venv/bin/python tools/check_version_consistency.py
```

Tests use synthetic data. Never add a personal save to the repository.

## Browser tests

```bash
npm ci --ignore-scripts
npx playwright install chromium firefox webkit
python3 tools/browser_test_server.py --port 18765
```

In another terminal:

```bash
node tools/browser_smoke.js http://127.0.0.1:18765 chromium
node tools/browser_smoke.js http://127.0.0.1:18765 firefox
node tools/browser_smoke.js http://127.0.0.1:18765 webkit
```

On Windows, `tools/run_browser_smoke.ps1` uses Chrome, Edge, and Firefox as
installed or prepared by the workflow. axe-core covers automatable WCAG checks;
manual accessibility review is still required.

## Building for Windows x64

Install Visual Studio 2022 Build Tools with C++ and CMake, Python 3.12 x64, and
Inno Setup 6. Then run:

```powershell
.\tools\build_windows_app.ps1
```

The script builds JoyConDSU and SDL3, packages the application with PyInstaller,
runs its self-test, and writes the `Setup.exe` to `dist\installer`.

## Building for macOS Apple Silicon

Use an Apple Silicon Mac with macOS 14 or later, Xcode Command Line Tools,
CMake, and arm64 Python 3.12:

```bash
xcode-select --install
brew install cmake
./tools/build_macos_app.sh
```

The script builds arm64 JoyConDSU and SDL3, checks Mach-O dependencies, applies
an ad hoc signature, and writes the DMG to `dist/`.

## Generated data

Compiled files in `botw_companion/data` improve offline startup and are part of
the product. When a source changes, run the applicable `tools/build_*.py`
script, review the diff, and run the full suite before committing.

Declare every new library, font, image, or data source in
`THIRD_PARTY_NOTICES.md`, `DATA_SOURCES.md`, or `licenses/` as appropriate, and
add it to `tools/audit_distribution.py`.

## Publishing a release

Only the maintainer prepares releases. See [`RELEASING.md`](../RELEASING.md)
for the complete process.
