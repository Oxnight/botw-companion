#!/usr/bin/env python3
"""Run reproducible audits of licenses, public docs, and release contents."""

from __future__ import annotations

import ast
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tokenize
import tomllib

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUM_FILE = re.compile(r"^(?:sha(?:256)?sums?|checksums?)\.txt$", re.I)
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
PUBLIC_DOCUMENTS = (
    "README.md", "CHANGELOG.md", "CONTRIBUTING.md", "RELEASING.md",
    "SECURITY.md", "PRIVACY.md", "THIRD_PARTY_NOTICES.md", "DATA_SOURCES.md",
    "docs/INSTALLATION.md", "docs/DSU.md", "docs/TROUBLESHOOTING.md",
    "docs/DEVELOPMENT.md", "macos/README.md", "windows/README.md",
    "windows/TESTING.md", "third_party/JoyConDSU/README_WINDOWS.md",
    "botw_companion/web/map-tiles/SOURCE.txt",
)
LEGAL_DOCUMENTS = (
    "LICENSE", "licenses/PYTHON-3.12.txt", "licenses/SDL3-3.4.14.txt",
)
FORBIDDEN_PARTS = {
    ".idea", ".venv", "venv", "env", "__MACOSX", "__pycache__",
    ".pytest_cache", "node_modules", "build", "dist", "test-results",
}
FORBIDDEN_NAMES = {".DS_Store"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".log", ".zip", ".dmg", ".rtf", ".rtfd"}
FRENCH_PROSE = re.compile(
    r"\b(?:aucun|aucune|avec|cette|dans|des|doit|doivent|données|fichier|"
    r"la|le|les|mise|pour|sauvegarde|sans|sont|sur|télécharger|"
    r"une|vérifier)\b",
    re.IGNORECASE,
)
FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE = re.compile(r"`[^`]*`")
EMPHASIZED_UI = re.compile(r"\*\*[^*]+\*\*")
URL = re.compile(r"https?://\S+")
COMMENTABLE_SUFFIXES = {".js", ".css", ".html", ".c", ".h", ".ps1", ".sh", ".iss", ".yml", ".yaml"}
COMMENT_LINE = re.compile(r"^\s*(?://|/\*|\*|<!--|#|;)(.*)$")


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _anchor(value: str) -> str:
    value = value.casefold().replace("`", "")
    value = re.sub(r"[^\w\- ]", "", value)
    return re.sub(r" +", "-", value.strip())


def _public_document_paths(root: Path) -> list[Path]:
    """Discover project-authored Markdown and plain-text documents."""
    legal = {root / relative for relative in LEGAL_DOCUMENTS}
    paths: set[Path] = set()
    for pattern in ("*.md", "*.txt"):
        for path in root.rglob(pattern):
            if path in legal or path.name == "CMakeLists.txt":
                continue
            if any(part in FORBIDDEN_PARTS or part == ".git" for part in path.relative_to(root).parts):
                continue
            if path.is_file():
                paths.add(path)
    return sorted(paths)


def documentation_errors(root: Path = ROOT) -> list[str]:
    """Validate files and anchors in internal links from public documents."""
    findings: list[str] = []
    root = root.resolve()
    for source in _public_document_paths(root):
        relative = source.relative_to(root).as_posix()
        if not source.is_file():
            findings.append(f"missing public document: {relative}")
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
                findings.append(f"link outside repository in {relative}: {raw_target}")
                continue
            if not destination.exists():
                findings.append(f"broken link in {relative}: {raw_target}")
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
                    findings.append(f"broken anchor in {relative}: {raw_target}")
    return findings


def public_language_errors(root: Path = ROOT) -> list[str]:
    """Reject likely French prose while allowing quoted French UI labels."""
    findings: list[str] = []
    for path in _public_document_paths(root):
        relative = path.relative_to(root).as_posix()
        content = path.read_text(encoding="utf-8")
        prose = FENCED_CODE.sub("", content)
        prose = INLINE_CODE.sub("", prose)
        prose = EMPHASIZED_UI.sub("", prose)
        prose = URL.sub("", prose)
        for line_number, line in enumerate(prose.splitlines(), 1):
            if FRENCH_PROSE.search(line):
                findings.append(
                    f"possible French prose in {relative}:{line_number}: {line.strip()}"
                )
    return findings


def source_comment_language_errors(root: Path = ROOT) -> list[str]:
    """Reject likely French prose in source comments and Python docstrings."""
    findings: list[str] = []
    for path in _repository_files(root):
        if not path.is_file() or any(part in FORBIDDEN_PARTS for part in path.relative_to(root).parts):
            continue
        relative = path.relative_to(root).as_posix()
        if path.suffix == ".py":
            try:
                content = path.read_text(encoding="utf-8")
                tree = ast.parse(content)
                tokens = tokenize.generate_tokens(io.StringIO(content).readline)
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            for token in tokens:
                if token.type == tokenize.COMMENT and FRENCH_PROSE.search(token.string):
                    findings.append(f"possible French comment in {relative}:{token.start[0]}")
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                value = ast.get_docstring(node, clean=False)
                if value and FRENCH_PROSE.search(value):
                    findings.append(f"possible French docstring in {relative}:{getattr(node, 'lineno', 1)}")
        elif path.suffix.casefold() in COMMENTABLE_SUFFIXES or path.name == "CMakeLists.txt":
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for line_number, line in enumerate(lines, 1):
                match = COMMENT_LINE.match(line)
                if match and FRENCH_PROSE.search(match.group(1)):
                    findings.append(f"possible French comment in {relative}:{line_number}")
    return findings


def _repository_files(root: Path) -> list[Path]:
    """Return tracked files when Git is available, otherwise all source files."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return [path for path in root.rglob("*") if path.is_file()]
    return [root / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def repository_hygiene_errors(root: Path = ROOT) -> list[str]:
    """Reject generated, personal, and release-output files from source control."""
    findings: list[str] = []
    for path in _repository_files(root):
        relative = path.relative_to(root)
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            findings.append(f"forbidden tracked directory: {relative}")
        elif path.name in FORBIDDEN_NAMES:
            findings.append(f"forbidden tracked local file: {relative}")
        elif path.suffix.casefold() in FORBIDDEN_SUFFIXES:
            findings.append(f"forbidden tracked generated file: {relative}")
        elif FORBIDDEN_SUM_FILE.fullmatch(path.name):
            findings.append(f"forbidden checksum file: {relative}")
    return findings


def audit() -> list[str]:
    errors: list[str] = []
    required = (".gitattributes", *LEGAL_DOCUMENTS, *PUBLIC_DOCUMENTS)
    for relative in required:
        path = ROOT / relative
        if not path.is_file() or not path.stat().st_size:
            errors.append(f"missing or empty document: {relative}")
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
        "CHANGELOG.md": ("## [Unreleased]", "Keep a Changelog", "Semantic Versioning"),
        "CONTRIBUTING.md": (
            "## Before you start", "## Verify your changes", "## Pull requests",
            "docs/DEVELOPMENT.md",
        ),
        "docs/INSTALLATION.md": ("## Windows", "## macOS Apple Silicon", "## Updating"),
        "docs/DSU.md": ("127.0.0.1", "26760", "## In the emulator"),
        "docs/TROUBLESHOOTING.md": (
            "## No save was detected", "## DSU motion controls do not work",
        ),
        "docs/DEVELOPMENT.md": (
            "## Python tests and audits", "## Building for Windows x64",
            "## Building for macOS Apple Silicon",
        ),
        "DATA_SOURCES.md": (
            "unofficial fan project", "no redistribution permission",
            "BOTW Object Map", "MrCheeze/botw-tools", "Zelda Wiki",
            "Zelda Dungeon", "Palais de Zelda",
        ),
        "botw_companion/web/map-tiles/SOURCE.txt": (
            "static.zeldamods.org/botw_map.png", "extracted from files", "Nintendo",
        ),
    }
    for relative, markers in checks.items():
        content = _text(relative)
        for marker in markers:
            if marker not in content:
                errors.append(f"{relative} is missing required text: {marker}")
    errors.extend(documentation_errors())
    errors.extend(public_language_errors())
    errors.extend(source_comment_language_errors())
    errors.extend(repository_hygiene_errors())

    current_version = _text("botw_companion/VERSION").strip()
    if f"## [{current_version}]" not in _text("CHANGELOG.md"):
        errors.append("CHANGELOG.md does not contain the current version")

    project = tomllib.loads(_text("pyproject.toml"))["project"]
    if project.get("license") != "MIT" or project.get("dependencies") != []:
        errors.append("Python dependency scope changed without an audit update")
    node = json.loads(_text("package.json"))
    expected_dev = {"axe-core": "4.13.0", "playwright": "1.62.0"}
    if node.get("devDependencies") != expected_dev or not node.get("private"):
        errors.append("Node dependency scope changed without an audit update")

    cmake = _text("third_party/JoyConDSU/CMakeLists.txt")
    if "release-3.4.14/SDL3-3.4.14.tar.gz" not in cmake:
        errors.append("SDL3 is no longer pinned to 3.4.14")
    if "SHA256=30d4aa2b3037718142b32dffd4e72f917ebb6cc5227150e7bb9c45efb2153aeb" not in cmake:
        errors.append("the SDL3 source archive is no longer authenticated")

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
                errors.append(f"{relative} does not ensure that {marker} is included")

    workflow = _text(".github/workflows/release.yml")
    for marker in (
        "--notes-file RELEASE_NOTES.md",
        "release-assets/${{ steps.version.outputs.installer_name }}",
        "release-assets/${{ steps.version.outputs.dmg_name }}",
    ):
        if marker not in workflow:
            errors.append(f"incomplete release publication rule: {marker}")
    return errors


def main() -> int:
    errors = audit()
    if errors:
        print("Distribution audit failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Licenses, provenance, public documentation, repository hygiene, and release assets passed the audit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
