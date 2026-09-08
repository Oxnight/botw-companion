#!/usr/bin/env python3
"""Contrôles reproductibles des licences, notices et paquets publiés."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUM_FILE = re.compile(r"^(?:sha(?:256)?sums?|checksums?)\.txt$", re.I)
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
PUBLIC_DOCUMENTS = (
    "README.md", "CHANGELOG.md", "CONTRIBUTING.md", "RELEASING.md",
    "SECURITY.md", "PRIVACY.md", "THIRD_PARTY_NOTICES.md", "DATA_SOURCES.md",
    "docs/INSTALLATION.md", "docs/DSU.md", "docs/TROUBLESHOOTING.md",
    "docs/DEVELOPMENT.md",
)


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _anchor(value: str) -> str:
    value = value.casefold().replace("`", "")
    value = re.sub(r"[^\w\- ]", "", value)
    return re.sub(r" +", "-", value.strip())


def documentation_errors(root: Path = ROOT) -> list[str]:
    """Valide les fichiers et ancres des liens Markdown internes publics."""
    findings: list[str] = []
    root = root.resolve()
    for relative in PUBLIC_DOCUMENTS:
        source = root / relative
        if not source.is_file():
            findings.append(f"document public absent : {relative}")
            continue
        content = source.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(content):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            path_part, separator, fragment = target.partition("#")
            destination = source if not path_part else source.parent / path_part
            destination = destination.resolve()
            if destination != root and root not in destination.parents:
                findings.append(f"lien hors dépôt dans {relative} : {raw_target}")
                continue
            if not destination.exists():
                findings.append(f"lien cassé dans {relative} : {raw_target}")
                continue
            if separator and fragment and destination.is_file():
                headings = {
                    _anchor(match.group(1))
                    for match in re.finditer(
                        r"^#{1,6}\s+(.+?)\s*#*\s*$",
                        destination.read_text(encoding="utf-8"),
                        re.MULTILINE,
                    )
                }
                if fragment.casefold() not in headings:
                    findings.append(f"ancre cassée dans {relative} : {raw_target}")
    return findings


def audit() -> list[str]:
    errors: list[str] = []
    required = (
        ".gitattributes", "LICENSE", *PUBLIC_DOCUMENTS,
        "licenses/PYTHON-3.12.txt", "licenses/SDL3-3.4.14.txt",
        "botw_companion/web/map-tiles/SOURCE.txt",
    )
    for relative in required:
        path = ROOT / relative
        if not path.is_file() or not path.stat().st_size:
            errors.append(f"document absent ou vide : {relative}")
    if errors:
        return errors

    checks = {
        ".gitattributes": ("*.sh text eol=lf", "licenses/*.txt text eol=lf"),
        "LICENSE": ("MIT License", "Permission is hereby granted"),
        "licenses/PYTHON-3.12.txt": (
            "PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2",
            "BEOPEN.COM LICENSE AGREEMENT FOR PYTHON 2.0",
            "CWI LICENSE AGREEMENT FOR PYTHON 0.9.0 THROUGH 1.2",
        ),
        "licenses/SDL3-3.4.14.txt": (
            "Copyright (C) 1997-2026 Sam Lantinga",
            "This software is provided 'as-is'",
            "The origin of this software must not be misrepresented",
        ),
        "THIRD_PARTY_NOTICES.md": (
            "CPython 3.12", "Simple DirectMedia Layer 3.4.14",
            "PyInstaller 6.22.2", "Inno Setup 6", "Playwright 1.62.0",
            "axe-core 4.13.0",
        ),
        "CHANGELOG.md": (
            "## [À venir]", "Keep a Changelog", "Semantic Versioning",
        ),
        "CONTRIBUTING.md": (
            "## Avant de commencer", "## Vérifier la contribution",
            "## Pull request", "docs/DEVELOPMENT.md",
        ),
        "docs/INSTALLATION.md": ("## Windows", "## macOS Apple Silicon", "## Mise à jour"),
        "docs/DSU.md": ("127.0.0.1", "26760", "## Dans l'émulateur"),
        "docs/TROUBLESHOOTING.md": ("## Aucune sauvegarde détectée", "## Le gyroscope ne fonctionne pas"),
        "docs/DEVELOPMENT.md": ("## Tests Python et audits", "## Construction Windows x64", "## Construction macOS Apple Silicon"),
        "DATA_SOURCES.md": (
            "projet de fans non officiel", "aucune autorisation de redistribution",
            "BOTW Object Map", "MrCheeze/botw-tools", "Zelda Wiki",
            "Zelda Dungeon", "Palais de Zelda",
        ),
        "botw_companion/web/map-tiles/SOURCE.txt": (
            "static.zeldamods.org/botw_map.png", "extrait des fichiers", "Nintendo",
        ),
    }
    for relative, markers in checks.items():
        content = _text(relative)
        for marker in markers:
            if marker not in content:
                errors.append(f"{relative} ne contient pas la mention : {marker}")
    errors.extend(documentation_errors())

    current_version = _text("botw_companion/VERSION").strip()
    if f"## [{current_version}]" not in _text("CHANGELOG.md"):
        errors.append("CHANGELOG.md ne contient pas la version courante")

    project = tomllib.loads(_text("pyproject.toml"))["project"]
    if project.get("license") != "MIT" or project.get("dependencies") != []:
        errors.append("le périmètre Python a changé sans audit")
    node = json.loads(_text("package.json"))
    expected_dev = {"axe-core": "4.13.0", "playwright": "1.62.0"}
    if node.get("devDependencies") != expected_dev or not node.get("private"):
        errors.append("le périmètre Node a changé sans audit")

    cmake = _text("third_party/JoyConDSU/CMakeLists.txt")
    if "release-3.4.14/SDL3-3.4.14.tar.gz" not in cmake:
        errors.append("SDL3 n'est plus épinglé à 3.4.14")
    if "SHA256=30d4aa2b3037718142b32dffd4e72f917ebb6cc5227150e7bb9c45efb2153aeb" not in cmake:
        errors.append("l'archive source SDL3 n'est plus authentifiée")

    packaging = {
        "windows/BOTW Companion.spec": ("licenses", "SDL3-LICENSE.txt"),
        "macos/BOTW Companion.spec": ("licenses", "CHANGELOG.md", "DATA_SOURCES.md", "PRIVACY.md", "SECURITY.md"),
        "tools/build_windows_app.ps1": ("CHANGELOG.md", "PYTHON-3.12.txt", "SDL3-3.4.14.txt", "DATA_SOURCES.md"),
        "tools/build_macos_app.sh": ("CHANGELOG.md", "PYTHON-3.12.txt", "SDL3-3.4.14.txt", "DATA_SOURCES.md"),
        "tools/test_windows_installation.ps1": ("CHANGELOG.md", "PYTHON-3.12.txt", "SDL3-3.4.14.txt", "PRIVACY.md"),
        "tools/test_macos_installation.sh": ("CHANGELOG.md", "PYTHON-3.12.txt", "SDL3-3.4.14.txt", "PRIVACY.md"),
    }
    for relative, markers in packaging.items():
        content = _text(relative)
        for marker in markers:
            if marker not in content:
                errors.append(f"{relative} n'assure pas la présence de {marker}")

    for path in ROOT.rglob("*"):
        if ".git" not in path.parts and path.is_file() and FORBIDDEN_SUM_FILE.fullmatch(path.name):
            errors.append(f"fichier de sommes interdit : {path.relative_to(ROOT)}")

    ignored_roots = {".git", "build", "dist", ".venv", "node_modules"}
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in ignored_roots for part in relative.parts):
            continue
        if path.name in {".DS_Store", "__MACOSX", ".idea"}:
            errors.append(f"résidu local interdit : {relative}")
        elif path.is_file() and path.suffix.casefold() in {".zip", ".dmg", ".rtf"}:
            errors.append(f"archive locale interdite : {relative}")

    workflow = _text(".github/workflows/release.yml")
    for marker in (
        "--notes-file RELEASE_NOTES.md",
        "release-assets/${{ steps.version.outputs.installer_name }}",
        "release-assets/${{ steps.version.outputs.dmg_name }}",
    ):
        if marker not in workflow:
            errors.append(f"publication incomplète : {marker}")
    return errors


def main() -> int:
    errors = audit()
    if errors:
        print("Audit de distribution échoué :", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Licences, provenances, documentation et actifs de release audités.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
