from __future__ import annotations

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
        for name in ("JoyConDSU.exe", "SDL3.dll", "manifest.json"):
            if not dsu_root.joinpath(name).is_file():
                errors.append(f"Ressource DSU Windows absente : {name}")
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