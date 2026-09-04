from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


project_root = Path(SPECPATH).parent
package_root = project_root / "botw_companion"
dsu_root = package_root / "dsu" / "macos"
datas = collect_data_files(
    "botw_companion",
    excludes=[
        "data/catalog.json",
        "dsu/windows/*",
        "dsu/macos/JoyConDSU",
        "dsu/macos/libSDL3.0.dylib",
    ],
)
datas.extend([
    (str(project_root / "LICENSE"), "."),
    (str(project_root / "THIRD_PARTY_NOTICES.md"), "."),
])
binaries = [
    (str(dsu_root / "JoyConDSU"), "botw_companion/dsu/macos"),
    (str(dsu_root / "libSDL3.0.dylib"), "botw_companion/dsu/macos"),
]

a = Analysis(
    [str(project_root / "macos_entry.py")],
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
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch="arm64",
    codesign_identity=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="BOTW Companion",
)
app = BUNDLE(
    coll,
    name="BOTW Companion.app",
    icon=str(project_root / "macos" / "BOTW Companion.icns"),
    bundle_identifier="fr.oxnight.botw-companion",
    version="0.40.0-alpha.24",
    info_plist={
        "CFBundleDisplayName": "BOTW Companion",
        "CFBundleShortVersionString": "0.40.0-alpha.24",
        "CFBundleVersion": "24",
        "LSMinimumSystemVersion": "14.0",
        "LSArchitecturePriority": ["arm64"],
        "NSHighResolutionCapable": True,
    },
    target_arch="arm64",
    codesign_identity=None,
)
