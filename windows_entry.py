import os
import sys


# PyInstaller's windowed bootloader exposes these streams as None.
# Several CLI paths remain shared with the self-contained application.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from botw_companion.windows_app import main


if __name__ == "__main__":
    raise SystemExit(main())
