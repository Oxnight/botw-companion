import os
from pathlib import Path


project_root = Path(SPECPATH).parent
datas = [(str(project_root / "botw_companion" / "VERSION"), "botw_companion")]

a = Analysis(
    [str(project_root / "windows_updater_entry.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BOTW Companion Updater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(project_root / "windows" / "BOTW Companion.ico"),
    version=str(Path(os.environ["BOTW_WINDOWS_VERSION_FILE"])),
)
