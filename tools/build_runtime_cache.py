#!/usr/bin/env python3
"""Construit les données françaises statiques utilisées au démarrage."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "botw_companion" / "data"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from botw_companion.localization import localize_catalog  # noqa: E402


def _fingerprint(paths: list[Path]) -> str:
    digest = sha256()
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _write(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def main() -> int:
    catalog_sources = [
        DATA / "catalog.json",
        DATA / "localization_fr.json",
        DATA / "nomenclature_fr_reference.json",
        ROOT / "botw_companion" / "localization.py",
        ROOT / "botw_companion" / "nomenclature_fr.py",
    ]
    raw_catalog = json.loads((DATA / "catalog.json").read_text())
    localized_catalog = localize_catalog(raw_catalog)
    compiled_catalog = DATA / "catalog_fr_compiled.json"
    _write(compiled_catalog, {
        "schema_version": 1,
        "source_fingerprint": _fingerprint(catalog_sources),
        "catalog": localized_catalog,
    })

    cartography_sources = [
        DATA / "cartography_reference.json",
        DATA / "localization_fr.json",
        DATA / "nomenclature_fr_reference.json",
        ROOT / "botw_companion" / "localization.py",
    ]
    raw_cartography = json.loads((DATA / "cartography_reference.json").read_text())
    compiled_cartography = DATA / "cartography_reference_fr_compiled.json"
    _write(compiled_cartography, {
        "schema_version": 1,
        "source_fingerprint": _fingerprint(cartography_sources),
        "reference": localize_catalog(raw_cartography),
    })

    # Le fichier vient d'être créé : vider le cache si ce script est rappelé
    # depuis un processus ayant déjà chargé une version précédente.
    from botw_companion.resources import load_catalog, load_cartography_reference  # noqa: E402
    load_catalog.cache_clear()
    load_cartography_reference.cache_clear()
    from botw_companion.analyzer import analyze  # noqa: E402

    audit = analyze({}, use_precompiled_nomenclature_audit=False)["audit_nomenclature"]
    audit_sources = catalog_sources + [
        ROOT / "botw_companion" / "analyzer.py",
        ROOT / "botw_companion" / "guides.py",
        ROOT / "botw_companion" / "guide_enrichment.py",
    ]
    _write(DATA / "nomenclature_audit_compiled.json", {
        "schema_version": 1,
        "source_fingerprint": _fingerprint(audit_sources),
        "audit": audit,
    })
    print(f"Catalogue français précompilé : {compiled_catalog}")
    print(f"Cartographie française précompilée : {compiled_cartography}")
    print(f"Audit français précompilé : {DATA / 'nomenclature_audit_compiled.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())