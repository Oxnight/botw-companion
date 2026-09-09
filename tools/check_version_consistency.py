#!/usr/bin/env python3
"""Check that every platform uses the single version source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from botw_companion.versioning import CURRENT_VERSION, ReleaseVersion  # noqa: E402


def require(path: Path, needle: str, description: str) -> str | None:
    text = path.read_text(encoding="utf-8")
    if needle not in text:
        return f"{path}: configuration manquante pour {description}"
    return None


def errors(root: Path, tag: str | None = None) -> list[str]:
    version = CURRENT_VERSION
    findings: list[str] = []
    checks = (
        (root / "pyproject.toml", 'dynamic = ["version"]', "la version Python dynamique"),
        (root / "pyproject.toml", 'version = {file = ["botw_companion/VERSION"]}', "la source Python"),
        (root / "botw_companion" / "__init__.py", "CURRENT_VERSION.pep440", "le runtime"),
        (root / "windows" / "BOTW Companion.spec", "BOTW_WINDOWS_VERSION_FILE", "PyInstaller Windows"),
        (root / "windows" / "BOTW Companion.iss", "{#MyAppVersion}", "Inno Setup"),
        (root / "tools" / "build_windows_app.ps1", "tools\\release_metadata.py", "la construction Windows"),
        (root / "macos" / "BOTW Companion.spec", "CURRENT_VERSION.macos_bundle", "le bundle macOS"),
        (root / "tools" / "build_macos_app.sh", "--field dmg_name", "la construction macOS"),
        (root / ".github" / "workflows" / "release.yml", 'tags: ["v*"]', "les tags génériques"),
        (root / ".github" / "workflows" / "release.yml", "steps.version.outputs.installer_name", "l'asset Windows dynamique"),
        (root / ".github" / "workflows" / "release.yml", "steps.version.outputs.dmg_name", "l'asset macOS dynamique"),
        (root / ".github" / "workflows" / "release.yml", "RELEASE_NOTES.md", "les notes humaines"),
    )
    findings.extend(result for item in checks if (result := require(*item)))

    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
    if "version" in package or "version" in lock or "version" in lock.get("packages", {}).get("", {}):
        findings.append("package.json/package-lock.json: version applicative dupliquée")

    baseline = ReleaseVersion.parse(
        (root / "packaging" / "UPGRADE_BASELINE").read_text(encoding="utf-8")
    )
    if baseline.precedence >= version.precedence:
        findings.append("UPGRADE_BASELINE doit désigner une version publiée antérieure")
    if tag is not None and tag != version.tag:
        findings.append(f"Tag invalide : {tag!r}, attendu {version.tag!r}")

    workflow = (root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    if "SHA256" + "SUMS" in workflow or "sha256" + "sum" in workflow.casefold():
        findings.append("Le workflow ne doit publier aucun fichier de sommes de contrôle")
    if not (root / "RELEASE_NOTES.md").is_file():
        findings.append("RELEASE_NOTES.md est absent")

    # The current version must appear literally only in its source file.
    excluded = {
        root / "botw_companion" / "VERSION",
        # The changelog intentionally lists every published version. Build
        # scripts never use it as a version source.
        root / "CHANGELOG.md",
        root / ".git",
    }
    for path in root.rglob("*"):
        generated = any(
            part in {"build", "dist", "__pycache__", ".pytest_cache"}
            or part.endswith(".egg-info")
            for part in path.parts
        )
        if generated or not path.is_file() or path in excluded or any(parent in excluded for parent in path.parents):
            continue
        if path.suffix.lower() in {".png", ".webp", ".ico", ".icns", ".zip", ".dmg", ".exe", ".dll"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if version.display in text or re.search(rf"(?<![\w.]){re.escape(version.pep440)}(?![\w.])", text):
            findings.append(f"{path}: version courante dupliquée hors de botw_companion/VERSION")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag")
    args = parser.parse_args(argv)
    findings = errors(ROOT, args.tag)
    if findings:
        print("\n".join(findings), file=sys.stderr)
        return 1
    print(f"Version cohérente depuis une source unique : {CURRENT_VERSION.display}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
