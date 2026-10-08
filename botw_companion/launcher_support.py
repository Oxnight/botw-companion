"""Launcher-owned logging and presentation, without global logging leaks."""
from __future__ import annotations

from contextlib import contextmanager
import json
import logging
from pathlib import Path

from .english import translate_text
from .persistence import atomic_write_json, read_json


def saved_language(data_root: Path) -> str:
    try:
        value = read_json(data_root / "presentation.json")
    except (OSError, json.JSONDecodeError):
        return "fr"
    language = value.get("language") if isinstance(value, dict) else None
    return language if language in ("fr", "en") else "fr"


def remember_language(data_root: Path, language: str) -> None:
    # Keep this outside the older, strict preferences schema: rollback to an
    # earlier release must still be able to read all functional preferences.
    if language not in ("fr", "en"):
        raise ValueError("Unsupported presentation language")
    atomic_write_json(data_root / "presentation.json", {"language": language})


@contextmanager
def launcher_log(path: Path, name: str):
    logger = logging.getLogger(name)
    previous_level, previous_propagate = logger.level, logger.propagate
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield logger
    finally:
        logger.removeHandler(handler)
        handler.close()
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


def launcher_error(error: Exception, log_path: Path, *, known: bool) -> str:
    # A broken preferences file must not prevent the startup error being shown.
    language = saved_language(log_path.parent)
    detail = str(error) if known else "Une erreur inattendue s’est produite. Consulte le journal pour les détails."
    if language == "en":
        detail = translate_text(detail)
        return f"BOTW Companion cannot start.\n\n{detail}\n\nLog: {log_path}"
    return f"BOTW Companion ne peut pas démarrer.\n\n{detail}\n\nJournal : {log_path}"
