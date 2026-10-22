# Developing BOTW Companion

This guide is for source checkouts. Players should use the packages described
in [`INSTALLATION.md`](INSTALLATION.md).

## Requirements

- Git
- Python 3.10 or later; Python 3.12 is recommended
- Node.js and npm for browser tests and locale generation

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

Activate `.venv` in each new terminal before using `python`.

On macOS/Linux with bash or zsh:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

After activation, `python` and `python -m pip` use this environment. The commands
in [TRANSLATING.md](TRANSLATING.md) assume it is active.

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

Only the maintainer prepares releases. See [RELEASE_PROCESS.md](RELEASE_PROCESS.md).

## Shared localization resources

Follow [TRANSLATING.md](TRANSLATING.md) for source roles, complete locale
addition, Fluent messages, official terms and review requirements. Install the
pinned runtime and development dependencies, then build/check all enabled locales:

```bash
python -m pip install -r requirements-runtime.txt
npm ci --ignore-scripts
python tools/i18n.py build
python tools/i18n.py check
python tools/i18n.py coverage
python tools/audit_localization.py
node --test tests/*.cjs
```

Generated locale resources are tracked product inputs to offline/native builds.
The compatibility English build command delegates to the generic builder.
Installed applications use bundled Fluent and CLDR data without npm, a network
service or a development checkout. Keep API identifiers and personal content
outside translation. Run the full Python and browser suites after changes.

## Repository tools

- `audit_distribution.py`, version/ref/asset checks, and browser helpers enforce
  repository and distribution rules.
- `build_windows_app.ps1` and `build_macos_app.sh` produce native packages;
  `test_*_installation` validates them on the corresponding operating system.
- `build_joycon_dsu_*` builds the project-authored engine and pinned SDL3 source.
- Catalog, geography, localization, and reference builders maintain offline
  data from explicit source inputs. They are not startup dependencies and must
  not be run against private saves for public output.
- `benchmark_report.py` compares report transport size and functional identity
  without changing the application.

Platform entry points remain at the root because the PyInstaller specifications
reference them directly. `third_party/JoyConDSU` contains project-authored native
source; its name does not imply a vendored upstream executable. Native binaries
and their manifests are generated by the platform build scripts.
