from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


DISPLAY_VERSION = "0.40.0-alpha.24"
PEP440_VERSION = "0.40.0a24"
NUMERIC_VERSION = "0.40.0.24"
RELEASE_TAG = f"v{DISPLAY_VERSION}"
INSTALLER_NAME = f"BOTW_Companion_{DISPLAY_VERSION}_Setup.exe"
DMG_NAME = f"BOTW_Companion_{DISPLAY_VERSION}_macOS_arm64.dmg"
MACOS_BUNDLE_VERSION = "0.40.0"


def require(path: Path, pattern: str, description: str) -> str | None:
    text = path.read_text(encoding="utf-8")
    if re.search(pattern, text, re.MULTILINE) is None:
        return f"{path}: version incohérente pour {description}"
    return None


def errors(root: Path, tag: str | None = None) -> list[str]:
    checks = (
        (root / "pyproject.toml", rf'^version = "{re.escape(PEP440_VERSION)}"$', "pyproject"),
        (root / "uv.lock", rf'^version = "{re.escape(PEP440_VERSION)}"$', "verrou uv"),
        (root / "botw_companion" / "__init__.py", rf'__version__ = "{re.escape(PEP440_VERSION)}"', "runtime"),
        (root / "windows" / "BOTW Companion.iss", rf'#define MyAppVersion "{re.escape(DISPLAY_VERSION)}"', "Inno Setup"),
        (root / "windows" / "BOTW Companion.iss", rf'VersionInfoVersion={re.escape(NUMERIC_VERSION)}', "version numérique Inno Setup"),
        (root / "windows" / "version_info.txt", rf'filevers=\(0, 40, 0, 24\)', "ressource EXE"),
        (root / "windows" / "version_info.txt", re.escape(DISPLAY_VERSION), "texte EXE"),
        (root / "tools" / "build_windows_app.ps1", re.escape(INSTALLER_NAME), "construction Windows"),
        (root / "tools" / "test_windows_installation.ps1", re.escape(INSTALLER_NAME), "test d'installation"),
        (root / "tools" / "test_windows_installation.ps1", re.escape(PEP440_VERSION), "test du serveur installé"),
        (root / "macos" / "BOTW Companion.spec", rf'version="{re.escape(MACOS_BUNDLE_VERSION)}"', "version courte macOS"),
        (root / "macos" / "BOTW Companion.spec", r'"CFBundleVersion": "24"', "numéro de build macOS"),
        (root / "tools" / "build_macos_app.sh", re.escape(DMG_NAME), "construction macOS"),
        (root / "tools" / "test_macos_installation.sh", re.escape(PEP440_VERSION), "test macOS"),
        (root / ".github" / "workflows" / "release.yml", re.escape(RELEASE_TAG), "workflow de publication"),
        (root / "README.md", re.escape(DISPLAY_VERSION), "README"),
        (root / "windows" / "README.md", re.escape(INSTALLER_NAME), "documentation Windows"),
        (root / "macos" / "README.md", re.escape(DMG_NAME), "documentation macOS"),
    )
    findings = [result for item in checks if (result := require(*item))]
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    if package.get("version") != DISPLAY_VERSION:
        findings.append("package.json: version incohérente")
    if tag is not None and tag != RELEASE_TAG:
        findings.append(
            f"Tag de publication invalide : {tag!r}, attendu {RELEASE_TAG!r}"
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    findings = errors(root, args.tag)
    if findings:
        print("\n".join(findings), file=sys.stderr)
        return 1
    print(f"Versions cohérentes : {DISPLAY_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
