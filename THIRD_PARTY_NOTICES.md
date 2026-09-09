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
