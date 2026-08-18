import json
from functools import lru_cache
from importlib.resources import files

@lru_cache(maxsize=1)
def load_hashes() -> dict[int, tuple[int, str]]:
    raw = json.loads(files("botw_companion.data").joinpath("hashes.json").read_text(encoding="utf-8"))
    return {int(key): (value[0], value[1]) for key, value in raw.items()}


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    """Charge le catalogue français déjà validé pendant la construction."""
    payload = json.loads(
        files("botw_companion.data").joinpath("catalog_fr_compiled.json").read_text(encoding="utf-8")
    )
    if payload.get("schema_version") != 1 or not isinstance(payload.get("catalog"), dict):
        raise ValueError("Catalogue français précompilé invalide")
    return payload["catalog"]


@lru_cache(maxsize=1)
def load_runtime_nomenclature_audit() -> dict:
    """Charge le résultat statique de l'audit français validé par les tests."""
    payload = json.loads(
        files("botw_companion.data").joinpath("nomenclature_audit_compiled.json").read_text(encoding="utf-8")
    )
    if payload.get("schema_version") != 1 or not isinstance(payload.get("audit"), dict):
        raise ValueError("Audit français précompilé invalide")
    return payload["audit"]


@lru_cache(maxsize=1)
def load_completion_standard() -> dict:
    return json.loads(
        files("botw_companion.data").joinpath("completion_standard.json").read_text(encoding="utf-8")
    )


@lru_cache(maxsize=1)
def load_cartography_reference() -> dict:
    """Charge les données cartographiques françaises préparées à la construction."""
    payload = json.loads(
        files("botw_companion.data").joinpath(
            "cartography_reference_fr_compiled.json"
        ).read_text(encoding="utf-8")
    )
    if payload.get("schema_version") != 1 or not isinstance(payload.get("reference"), dict):
        raise ValueError("Référence cartographique française précompilée invalide")
    return payload["reference"]


@lru_cache(maxsize=1)
def load_solution_reference() -> dict:
    return json.loads(
        files("botw_companion.data").joinpath("solution_reference.json").read_text(encoding="utf-8")
    )


@lru_cache(maxsize=1)
def load_nomenclature_reference() -> dict:
    return json.loads(
        files("botw_companion.data").joinpath("nomenclature_fr_reference.json").read_text(encoding="utf-8")
    )