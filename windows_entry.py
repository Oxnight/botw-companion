import io
import os
import sys


# PyInstaller's windowed bootloader exposes these streams as None.
# Several CLI paths remain shared with the self-contained application.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# Redirected output uses the Windows code page even in a frozen application.
# Configure it before imports or startup messages can write to the server log.
for stream in (sys.stdout, sys.stderr):
    if isinstance(stream, io.TextIOWrapper):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")

from botw_companion.windows_app import main


if __name__ == "__main__":
    raise SystemExit(main())
