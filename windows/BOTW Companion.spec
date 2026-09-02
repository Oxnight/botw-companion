from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


project_root = Path(SPECPATH).parent
package_root = project_root / "botw_companion"
dsu_root = package_root / "dsu" / "windows"
datas = collect_data_files(
    "botw_companion",
    excludes=[
        "data/catalog.json",
        "dsu/JoyConDSU",
        "dsu/*.sh",
        "dsu/*.md",
        "dsu/windows/*",
    ],
)
datas.append((str(dsu_root / "manifest.json"), "botw_companion/dsu/windows"))
datas.append((str(dsu_root / "SDL3-LICENSE.txt"), "botw_companion/dsu/windows"))
binaries = [
    (str(dsu_root / "JoyConDSU.exe"), "botw_companion/dsu/windows"),
    (str(dsu_root / "SDL3.dll"), "botw_companion/dsu/windows"),
]

a = Analysis(
    [str(project_root / "windows_entry.py")],
    pathex=[str(project_root)],
    binaries=binaries,
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
    [],
    exclude_binaries=True,
    name="BOTW Companion",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(project_root / "windows" / "BOTW Companion.ico"),
    version=str(project_root / "windows" / "version_info.txt"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BOTW Companion",
)
