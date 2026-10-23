# Third-party notices

This document covers software used to build or run BOTW Companion. Data and
editorial sources are listed separately in
[`DATA_SOURCES.md`](DATA_SOURCES.md).

## Components included in distributed applications

### CPython 3.12

The Windows and macOS applications include a CPython 3.12 runtime. Python is
distributed under the Python Software Foundation License Version 2 and includes
material governed by the notices reproduced in the complete official text:
[`licenses/PYTHON-3.12.txt`](licenses/PYTHON-3.12.txt).

Copyright © 2001 Python Software Foundation. All Rights Reserved.

Official source: <https://docs.python.org/3/license.html>

### Simple DirectMedia Layer 3.4.14

JoyConDSU is distributed with SDL 3.4.14 under the zlib license. The complete
text is available in [`licenses/SDL3-3.4.14.txt`](licenses/SDL3-3.4.14.txt) and
next to the native library in each package.

Copyright © Sam Lantinga and the SDL contributors.

Official sources: <https://www.libsdl.org/license.php> and
<https://github.com/libsdl-org/SDL/tree/release-3.4.14>

### certifi 2025.8.3

The applications include certifi's Mozilla CA certificate bundle so update
checks and installer downloads can verify GitHub's TLS certificates
consistently in self-contained packages. The bundle is covered by the Mozilla
Public License 2.0; its notice is reproduced in
[`licenses/CERTIFI-MPL-2.0.txt`](licenses/CERTIFI-MPL-2.0.txt).

Official source: <https://github.com/certifi/python-certifi/tree/2025.08.03>

### BOTW Companion and JoyConDSU

Project-authored BOTW Companion code, including the JoyConDSU engine in this
repository, is distributed under the MIT License in [`LICENSE`](LICENSE).
JoyConDSU uses SDL3 but contains no code from the unrelated historical project
with the same name.

## Build-only tools

- **PyInstaller 6.22.2** creates the self-contained bundles. Its GPL 2.0
  license exception allows generated executables to retain the project's
  license and states that a PyInstaller notice is not required in the
  application: <https://pyinstaller.org/en/stable/license.html>.
- **Inno Setup 6** creates only the Windows installer. Its official terms
  allow this use and appreciate, but do not require, documentation credit:
  <https://jrsoftware.org/files/is/license.txt>.
- **CMake**, Apple Clang/MSVC, **setuptools**, and GitHub Actions are used only
  during builds and are not installed with BOTW Companion.
- **Playwright 1.62.0** (Apache-2.0) and **axe-core 4.13.0** (MPL-2.0) are used
  only by browser tests. Neither is included in the published applications.

`tools/audit_distribution.py` checks component versions and scope before every
build.

## Acorn

Acorn 8.15.0 is an MIT-licensed JavaScript parser used only to inspect shared
browser source and validate message contracts during development. Its parser and Node.js dependencies are not
bundled in the application. See [Acorn](https://github.com/acornjs/acorn).

## Shared offline localization

The shared Python/browser formatter uses Fluent rather than an application
parser or translation service. These tested pins are reproducible inputs, not
a statement that they are the latest available versions.

- **fluent.runtime 0.4.0**, **fluent.syntax 0.19.0**, and browser
  **@fluent/bundle 0.19.1**: Apache-2.0, Mozilla and Project Fluent contributors.
  The Python parser is also needed at runtime by FluentResource. The JavaScript
  runtime is bundled locally in `web/i18n.js`.
  Sources: <https://github.com/projectfluent/python-fluent> and
  <https://github.com/projectfluent/fluent.js>.
  [Apache license](licenses/FLUENT-APACHE-2.0.txt).
- **Babel 2.17.0** supplies Python CLDR formatting/plural data offline:
  [BSD license](licenses/BABEL-2.17.0.txt) and
  [Unicode data terms](licenses/UNICODE-CLDR.txt).
  Source: <https://github.com/python-babel/babel/tree/v2.17.0>.
- Fluent's Python dependencies are pinned as **attrs 25.3.0**
  ([MIT](licenses/ATTRS-25.3.0.txt)), **pytz 2025.2**
  ([MIT](licenses/PYTZ-2025.2.txt)), and **typing_extensions 4.15.0**
  ([PSF terms](licenses/TYPING-EXTENSIONS-4.15.0.txt)).
  Sources: <https://github.com/python-attrs/attrs>,
  <https://github.com/stub42/pytz>, <https://github.com/python/typing_extensions>.
- **esbuild 0.25.12** ([MIT](licenses/ESBUILD-0.25.12.txt)) is the development
  bundler. Installed applications use the bundled runtime and do not require
  esbuild or npm.
  Source: <https://github.com/evanw/esbuild/tree/v0.25.12>.

The supplied Fluent Python wheels and npm distributions omit a separate
license/NOTICE file. Their metadata declares Apache-2.0; the standard license
text is retained here, with the project attribution above. Upstream source
and metadata must be reviewed when updating these pins. Browser Intl data
comes from the installed browser; it is not downloaded by Companion.
