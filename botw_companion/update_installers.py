"""Select the assisted updater for the packaged operating system."""

from __future__ import annotations

import platform

from .macos_updates import MacOSUpdateError, MacOSUpdateInstaller
from .windows_updates import WindowsUpdateError, WindowsUpdateInstaller


INSTALLATION_ERRORS = (MacOSUpdateError, WindowsUpdateError)


def default_update_installer():
    if platform.system() == "Darwin":
        return MacOSUpdateInstaller()
    return WindowsUpdateInstaller()
