from __future__ import annotations

import hashlib
from importlib.resources import files
import json
import re


DATA_FILES = (
    "catalog_fr_compiled.json",
    "cartography_reference_fr_compiled.json",
    "nomenclature_audit_compiled.json",
    "completion_standard.json",
    "hashes.json",
    "solution_reference.json",
    "korok_reference.json",
    "chest_reference.json",
    "boss_reference.json",
)
WEB_FILES = (
    "index.html",
    "app.js",
    "route_planner.js",
    "style.css",
    "metrics.css",
    "armor.css",
    "hyrule-map.webp",
    "map-tiles/manifest.json",
)


def _resource(root, relative: str):
    return root.joinpath(*relative.split("/"))


def windows_dsu_errors(dsu_root) -> list[str]:
    """Valide la présence, le format et les empreintes du runtime DSU Windows."""
    errors = []
    required = ("JoyConDSU.exe", "SDL3.dll", "manifest.json", "SDL3-LICENSE.txt")
    for name in required:
        if not dsu_root.joinpath(name).is_file():
            errors.append(f"Ressource DSU Windows absente : {name}")
    manifest_path = dsu_root.joinpath("manifest.json")
    if not manifest_path.is_file():
        return errors
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"Manifeste DSU Windows invalide : {exc}")
        return errors
    expected = {
        "schema_version": 1,
        "architecture": "x64",
        "protocol": 1001,
        "port": 26760,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            errors.append(
                f"Manifeste DSU Windows incohérent : {key}={manifest.get(key)!r}"
            )
    for name, key in (
        ("JoyConDSU.exe", "executable_sha256"),
        ("SDL3.dll", "sdl_sha256"),
    ):
        resource = dsu_root.joinpath(name)
        if not resource.is_file():
            continue
        actual = hashlib.sha256(resource.read_bytes()).hexdigest()
        expected_hash = str(manifest.get(key, "")).casefold()
        if actual != expected_hash:
            errors.append(f"Empreinte DSU Windows invalide : {name}")
    return errors


def offline_resource_errors(*, windows_dsu: bool = False) -> list[str]:
    """Valide toutes les ressources nécessaires sans effectuer d'accès réseau."""
    data_root = files("botw_companion.data")
    web_root = files("botw_companion.web")
    errors = [
        f"Ressource absente : {name}"
        for root, names in ((data_root, DATA_FILES), (web_root, WEB_FILES))
        for name in names
        if not _resource(root, name).is_file()
    ]
    manifest_path = _resource(web_root, "map-tiles/manifest.json")
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text())
            for level in manifest.get("levels", []):
                for column in range(int(level["columns"])):
                    for row in range(int(level["rows"])):
                        name = f"map-tiles/{level['id']}/{column}_{row}.webp"
                        if not _resource(web_root, name).is_file():
                            errors.append(f"Tuile hors ligne absente : {name}")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"Manifeste des tuiles invalide : {exc}")
    if windows_dsu:
        dsu_root = files("botw_companion.dsu").joinpath("windows")
        errors.extend(windows_dsu_errors(dsu_root))
    return errors


def remote_runtime_dependencies() -> list[str]:
    """Détecte une ressource Web distante requise automatiquement par l'interface."""
    web_root = files("botw_companion.web")
    findings = []
    html = web_root.joinpath("index.html").read_text()
    for match in re.finditer(r"(?:src|href)=[\"'](https?://[^\"']+)", html, re.I):
        findings.append(match.group(1))
    for name in ("style.css", "metrics.css", "armor.css"):
        css = web_root.joinpath(name).read_text()
        for match in re.finditer(r"url\(\s*[\"']?(https?://[^\"')\s]+)", css, re.I):
            findings.append(match.group(1))
    for name in ("app.js", "route_planner.js"):
        script = web_root.joinpath(name).read_text()
        for match in re.finditer(r"fetch\(\s*[\"'`](https?://[^\"'`]+)", script, re.I):
            findings.append(match.group(1))
    return sorted(set(findings))
