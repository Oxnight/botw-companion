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

## Local release validation

[The local validation entry point](../tools/validate_local.py) calls the same
version, distribution, locale, browser, build and installation tools as the
release workflow. It also runs the complete Node unit suite. It performs no
publication, Git mutation, workflow dispatch or artifact upload.

Use Python 3.12 with the environment activated, Node/npm and Git. Install
`actionlint` for workflow syntax/expression validation. The browser and native
phases require macOS 15 or later on Apple Silicon, or Windows x64. Windows also
needs PowerShell 7, Chrome and Edge; package builds need the native prerequisites
listed above and verified Inno Setup 6. Run Windows installer validation in a
disposable Windows x64 VM/user account: the existing installer tests exercise
per-user registration and Desktop/Start Menu shortcuts as well as temporary
installation and synthetic data paths. They must not share a player's account.

On macOS, from a normal terminal that permits loopback sockets:

```bash
python tools/validate_local.py --prepare --phase all
```

On Windows x64, in PowerShell 7 with the disposable test account:

```powershell
python tools/validate_local.py --prepare --phase all
```

`--prepare` installs the pinned runtime/Node dependencies and Playwright's
Chromium, Firefox and WebKit. Omit it once those prerequisites are installed.
The Windows browser phase retains Chrome/Edge/Firefox coverage and additionally
runs Playwright Chromium/WebKit. The macOS browser phase uses the shell helper
shared with Actions, including its original deadlines and per-engine fixtures.

Phases can be run separately on either supported OS:

```bash
python tools/validate_local.py --phase checks
python tools/validate_local.py --phase browsers
python tools/validate_local.py --phase packages
```

The command stops and propagates the first failure. An unavailable `actionlint`
is reported as unexecuted. Existing browser watchdogs, installation checks and
recovery assertions retain their limits. Local success does not establish
GitHub runner, artifact-transfer, environment-protection or publication success.

Native builds run from a source copy under the ignored
`test-results/codex-handoff/results/local-run-*/source`, including new source
files, without `.git`, local agent instructions, environments or build outputs.
The installed application and the working checkout's `build/` and `dist/` stay
outside that copy. Package output and synthetic native-test diagnostics are
retained there; `RUNNER_TEMP` points to this run's own `native-temp` directory.
The installation scripts retain replacement, restart and synthetic-data
preservation checks. macOS also exercises rollback and interruption. Windows
exercises installer recovery/reinstallation rather than transactional rollback.

The first stable version validates same-version replacement and recovery;
this is not evidence of an upgrade. Later candidates require published stable
references selected by `release_metadata.py`. Download the exact assets using
the read-only commands in the workflow, then pass their local paths:

```bash
python tools/validate_local.py --phase packages \
  --previous-package "/path/to/latest-stable.dmg" \
  --minimum-package "/path/to/minimum-stable.dmg"
```

```powershell
python tools/validate_local.py --phase packages `
  --previous-package "C:\references\latest-stable-Setup.exe" `
  --minimum-package "C:\references\minimum-stable-Setup.exe"
```

Only pass `--minimum-package` when a separate minimum reference is required.
Missing required references fail validation; they never select bootstrap mode.
Neither reference downloads nor application version changes are automatic.
