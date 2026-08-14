from __future__ import annotations

from collections import deque
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import threading
import time
from typing import Callable

from .save import SaveError, find_latest_slot, parse_file


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _iso_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value).astimezone().isoformat(timespec="seconds")


class ReliableSaveSync:
    """Cache le dernier rapport valide et ne lit qu'un fichier devenu stable."""

    def __init__(self, save_path: str | Path | None, payload_factory: Callable[[], dict],
                 stability_checks: int = 3, stability_delay: float = 0.12,
                 event_limit: int = 12, max_wait_seconds: float = 15.0,
                 monotonic_clock: Callable[[], float] = time.monotonic) -> None:
        self.save_path = save_path
        self.payload_factory = payload_factory
        self.stability_checks = max(2, stability_checks)
        self.stability_delay = max(0.0, stability_delay)
        self.max_wait_seconds = max(0.0, max_wait_seconds)
        self.monotonic_clock = monotonic_clock
        self._lock = threading.Lock()
        self._report: dict | None = None
        self._quick_signature: tuple | None = None
        self._digest: str | None = None
        self._slot: str | None = None
        self._internal_timestamp: int | None = None
        self._known_timestamps: dict[str, int] = {}
        self._pending_since: dict[str, float] = {}
        self._revision = 0
        self._failures = 0
        self._events: deque[dict[str, str]] = deque(maxlen=event_limit)
        self._state: dict[str, object] = {
            "schema_version": 2,
            "status": "initialisation",
            "status_label": "Première lecture en attente",
            "last_check_at": None,
            "last_success_at": None,
            "last_change_at": None,
            "last_file_modified_at": None,
            "slot": None,
            "save_mode": None,
            "save_timestamp": None,
            "save_timestamp_at": None,
            "candidate_slot": None,
            "candidate_status": None,
            "candidate_since": None,
            "wait_deadline_at_seconds": self.max_wait_seconds,
            "ignored_slot": None,
            "fingerprint": None,
            "report_revision": 0,
            "consecutive_failures": 0,
            "error": None,
        }

    def _event(self, kind: str, message: str) -> None:
        self._events.appendleft({"at": _iso_now(), "kind": kind, "message": message})

    def _files(self) -> tuple[Path, tuple[Path, Path]]:
        slot = find_latest_slot(self.save_path)
        return slot.path, (slot.path / "caption.sav", slot.path / "game_data.sav")

    def _newest_filesystem_activity(self) -> tuple[Path, int] | None:
        """Repère aussi un nouveau slot dont le caption n'est pas encore lisible."""
        if self.save_path is None:
            return None
        root = Path(self.save_path).expanduser().resolve()
        candidates = ([root] if (root / "caption.sav").exists() or (root / "game_data.sav").exists()
                      else [child for child in root.iterdir() if child.is_dir()]
                      if root.is_dir() else [])
        activity = []
        for candidate in candidates:
            files = [candidate / name for name in ("caption.sav", "game_data.sav")]
            mtimes = [path.stat().st_mtime_ns for path in files if path.exists()]
            if mtimes:
                activity.append((candidate, max(mtimes)))
        return max(activity, key=lambda value: value[1]) if activity else None

    def _candidate_paths(self) -> list[Path]:
        if self.save_path is None:
            latest = find_latest_slot(None)
            root = latest.path.parent
        else:
            root = Path(self.save_path).expanduser().resolve()
        if (root / "caption.sav").exists() or (root / "game_data.sav").exists():
            return [root]
        if not root.is_dir():
            return []
        return sorted(child for child in root.iterdir() if child.is_dir() and any(
            (child / name).exists() for name in ("caption.sav", "game_data.sav")
        ))

    def _observations(self) -> list[dict[str, object]]:
        observations = []
        for slot in self._candidate_paths():
            files = (slot / "caption.sav", slot / "game_data.sav")
            existing = [path for path in files if path.exists()]
            mtimes = [path.stat().st_mtime_ns for path in existing]
            signature = None
            if len(existing) == 2:
                try:
                    signature = self._stats(slot, files)
                except OSError:
                    signature = None
            timestamp = None
            error = None
            if files[0].is_file():
                try:
                    timestamp = int(parse_file(files[0]).get("LastSaveTime_Lower", 0))
                    self._known_timestamps[slot.name] = timestamp
                except (OSError, SaveError, ValueError) as exc:
                    error = str(exc)
            else:
                error = "caption.sav absent"
            if not files[1].is_file():
                error = "game_data.sav absent"
            observations.append({
                "slot": slot, "files": files, "timestamp": timestamp,
                "mtime_ns": max(mtimes) if mtimes else 0,
                "signature": signature, "error": error,
            })
        return observations

    def _pending_expired(self, observation: dict[str, object]) -> bool:
        key = str(observation["slot"])
        now = self.monotonic_clock()
        self._pending_since.setdefault(key, now)
        return now - self._pending_since[key] >= self.max_wait_seconds

    def _clear_pending(self, slot: Path) -> None:
        self._pending_since.pop(str(slot), None)

    def _problem(self, status: str, label: str, observation: dict[str, object],
                 *, error: str | None = None, event_kind: str = "attente") -> None:
        slot = observation["slot"]
        previous = (self._state.get("status"), self._state.get("candidate_slot"),
                    self._state.get("status_label"))
        self._state.update({
            "status": status, "status_label": label,
            "candidate_slot": slot.name, "candidate_status": status,
            "candidate_since": _iso_timestamp(time.time() - max(
                0.0, self.monotonic_clock() - self._pending_since.get(str(slot), self.monotonic_clock())
            )),
            "error": error,
        })
        if previous != (status, slot.name, label):
            self._event(event_kind, label)

    @staticmethod
    def _save_mode(slot: Path) -> str:
        try:
            return "expert" if int(slot.name) in (6, 7) else "normal"
        except ValueError:
            return "inconnu"

    @staticmethod
    def _stats(slot: Path, files: tuple[Path, Path]) -> tuple:
        values = []
        for path in files:
            stat = path.stat()
            values.extend((path.name, stat.st_size, stat.st_mtime_ns, getattr(stat, "st_ino", 0)))
        return (str(slot), *values)

    def _stable_bytes(self, slot: Path, files: tuple[Path, Path]) -> tuple[str, tuple[tuple, str] | None, str | None]:
        try:
            signature = self._stats(slot, files)
        except OSError as exc:
            return "changing", None, str(exc)
        for _check in range(self.stability_checks - 1):
            if self.stability_delay:
                time.sleep(self.stability_delay)
            try:
                if self._stats(slot, files) != signature:
                    return "changing", None, None
            except OSError as exc:
                return "changing", None, str(exc)
        digest = sha256()
        try:
            for path in files:
                data = path.read_bytes()
                if len(data) < 16 or data[-4:] != b"\xff\xff\xff\xff":
                    return "invalid", None, f"Fichier incomplet ou invalide : {path.name}"
                digest.update(path.name.encode())
                digest.update(len(data).to_bytes(8, "big"))
                digest.update(data)
            if self._stats(slot, files) != signature:
                return "changing", None, None
        except OSError as exc:
            return "changing", None, str(exc)
        return "stable", (signature, digest.hexdigest()), None

    def _metadata(self, *, changed: bool = False) -> dict:
        return {**self._state, "changed": changed, "events": list(self._events)}

    def _cached_result(self, *, include_report: bool, changed: bool = False) -> dict:
        return {
            "changed": changed,
            "synchronisation": self._metadata(changed=changed),
            "report": self._report if include_report else None,
        }

    def check(self, force: bool = False, include_report: bool = False) -> dict:
        """Vérifie la source; conserve le dernier rapport si Ryujinx écrit encore."""
        with self._lock:
            self._state["last_check_at"] = _iso_now()
            try:
                observations = self._observations()
            except (OSError, SaveError) as exc:
                observations = []
                observation_error = str(exc)
            else:
                observation_error = "Aucun slot Ryujinx détecté"

            if observations:
                newest_mtime = max(int(item["mtime_ns"]) for item in observations)
                self._state["last_file_modified_at"] = _iso_timestamp(newest_mtime / 1_000_000_000)
            readable = [item for item in observations
                        if item["timestamp"] is not None and item["signature"] is not None]
            if not readable:
                observation = max(observations, key=lambda item: int(item["mtime_ns"])) if observations else {
                    "slot": Path("inconnu"), "error": observation_error,
                }
                expired = self._pending_expired(observation)
                status = "fichier_corrompu" if expired else "ecriture_en_cours"
                label = (f"Fichier corrompu ou incomplet dans le slot {observation['slot'].name}"
                         if expired else f"Écriture en cours dans le slot {observation['slot'].name}")
                self._failures += 1
                self._problem(status, label, observation,
                              error=str(observation.get("error") or observation_error),
                              event_kind="erreur" if expired else "attente")
                self._state["consecutive_failures"] = self._failures
                if self._report is not None:
                    return self._cached_result(include_report=include_report)
                raise SaveError(label)

            selected = max(readable, key=lambda item: (int(item["timestamp"]), item["slot"].name))
            slot = selected["slot"]
            files = selected["files"]
            timestamp = int(selected["timestamp"])
            quick = selected["signature"]
            self._state.update({
                "save_timestamp": timestamp,
                "save_timestamp_at": _iso_timestamp(timestamp),
                "save_mode": self._save_mode(slot),
            })

            # Un slot plus ancien ne doit jamais remplacer le dernier rapport valide.
            if self._report is not None and self._internal_timestamp is not None and timestamp < self._internal_timestamp:
                current = next((item for item in observations if item["slot"].name == self._slot), selected)
                expired = self._pending_expired(current)
                status = "fichier_corrompu" if expired else "ecriture_en_cours"
                label = (f"Slot courant {self._slot} illisible - dernier rapport valide conservé"
                         if expired else f"Écriture en cours dans le slot courant {self._slot}")
                self._problem(status, label, current, error=str(current.get("error") or "horodatage interne absent"),
                              event_kind="erreur" if expired else "attente")
                return self._cached_result(include_report=include_report)

            # La date système peut changer sur un ancien slot (copie, antivirus, Finder).
            # Elle est informative uniquement : l'horodatage interne décide du slot courant.
            hottest = max(observations, key=lambda item: int(item["mtime_ns"]))
            ignored = None
            unknown_new = None
            if hottest["slot"] != slot and int(hottest["mtime_ns"]) > int(selected["mtime_ns"]):
                known = hottest["timestamp"]
                if known is None:
                    known = self._known_timestamps.get(hottest["slot"].name)
                if known is not None and int(known) <= timestamp:
                    ignored = hottest
                else:
                    unknown_new = hottest

            if unknown_new is not None and self._report is not None:
                expired = self._pending_expired(unknown_new)
                status = "fichier_corrompu" if expired else "ecriture_en_cours"
                label = (f"Nouveau slot {unknown_new['slot'].name} corrompu ou incomplet"
                         if expired else f"Nouveau slot {unknown_new['slot'].name} en cours d’écriture")
                self._problem(status, label, unknown_new, error=str(unknown_new.get("error") or "slot incomplet"),
                              event_kind="erreur" if expired else "attente")
                return self._cached_result(include_report=include_report)

            if self._report is not None and quick == self._quick_signature and not force:
                self._failures = 0
                if ignored is not None:
                    label = f"Ancien slot {ignored['slot'].name} modifié - slot {slot.name} conservé"
                    self._state.update({"status": "ancien_slot_modifie", "status_label": label,
                                        "ignored_slot": ignored["slot"].name, "error": None})
                    self._event("information", label)
                else:
                    self._state.update({"status": "a_jour", "status_label": "À jour",
                                        "ignored_slot": None, "error": None})
                self._state.update({"slot": slot.name, "candidate_slot": None,
                                    "candidate_status": None, "candidate_since": None,
                                    "consecutive_failures": 0})
                return self._cached_result(include_report=include_report)

            old_slot = self._slot
            self._state.update({
                "status": "changement_detecte", "status_label": "Changement détecté",
                "last_change_at": _iso_now(), "slot": slot.name, "error": None,
            })
            self._event("changement", f"Modification détectée dans le slot {slot.name}.")
            stable_status, stable, stable_error = self._stable_bytes(slot, files)
            if stable_status != "stable" or stable is None:
                expired = self._pending_expired(selected)
                # Un fichier momentanément tronqué est indiscernable d'une écriture
                # Ryujinx : on ne le déclare corrompu qu'après l'attente maximale.
                status = "fichier_corrompu" if expired else "ecriture_en_cours"
                label = (f"Fichier corrompu ou incomplet dans le slot {slot.name}"
                         if status == "fichier_corrompu" else f"Écriture en cours dans le slot {slot.name}")
                self._problem(status, label, selected, error=stable_error,
                              event_kind="erreur" if status == "fichier_corrompu" else "attente")
                if self._report is not None:
                    return self._cached_result(include_report=include_report)
                raise SaveError(label)

            self._clear_pending(slot)
            stable_signature, digest = stable
            if self._report is not None and digest == self._digest and not force:
                self._quick_signature = stable_signature
                self._internal_timestamp = timestamp
                self._state.update({"status": "a_jour", "status_label": "À jour - contenu inchangé",
                                    "slot": slot.name, "candidate_slot": None,
                                    "candidate_status": None, "candidate_since": None})
                return self._cached_result(include_report=include_report)

            self._state.update({"status": "analyse", "status_label": "Analyse de la nouvelle sauvegarde"})
            try:
                report = self.payload_factory()
                current = self._observations()
                current_readable = [item for item in current
                                    if item["timestamp"] is not None and item["signature"] is not None]
                current_selected = max(current_readable,
                                       key=lambda item: (int(item["timestamp"]), item["slot"].name))
                if (current_selected["slot"] != slot or int(current_selected["timestamp"]) != timestamp
                        or self._stats(slot, files) != stable_signature):
                    raise SaveError("La sauvegarde a changé pendant l’analyse")
            except SaveError as exc:
                self._failures += 1
                status = "ecriture_en_cours" if "changé pendant" in str(exc) else "fichier_corrompu"
                self._problem(status,
                              "La sauvegarde a changé pendant l’analyse" if status == "ecriture_en_cours"
                              else "Sauvegarde corrompue ou non analysable",
                              selected, error=str(exc), event_kind="attente" if status == "ecriture_en_cours" else "erreur")
                self._state["consecutive_failures"] = self._failures
                if self._report is not None:
                    return self._cached_result(include_report=include_report)
                raise
            except Exception as exc:
                self._failures += 1
                self._problem("erreur_analyse", "Erreur interne pendant l’analyse", selected,
                              error=str(exc), event_kind="erreur")
                self._state["consecutive_failures"] = self._failures
                if self._report is not None:
                    return self._cached_result(include_report=include_report)
                raise

            self._report = report
            self._quick_signature = stable_signature
            self._digest = digest
            self._slot = slot.name
            self._internal_timestamp = timestamp
            self._revision += 1
            self._failures = 0
            changed_slot = old_slot is not None and old_slot != slot.name
            status = "nouveau_slot_valide" if changed_slot else "actualise"
            label = f"Nouveau slot {slot.name} analysé" if changed_slot else "Nouvelle sauvegarde analysée"
            self._state.update({
                "status": status, "status_label": label,
                "last_success_at": _iso_now(), "slot": slot.name,
                "save_timestamp": timestamp, "save_timestamp_at": _iso_timestamp(timestamp),
                "save_mode": self._save_mode(slot), "fingerprint": digest[:16],
                "report_revision": self._revision, "consecutive_failures": 0,
                "candidate_slot": None, "candidate_status": None, "candidate_since": None,
                "ignored_slot": ignored["slot"].name if ignored else None, "error": None,
            })
            message = f"Slot {slot.name} analysé avec succès."
            if changed_slot:
                message = f"Passage du slot {old_slot} au slot {slot.name}; nouvelle sauvegarde analysée."
            self._event("succes", message)
            report["synchronisation"] = self._metadata(changed=True)
            return self._cached_result(include_report=True, changed=True)

    def report(self, force: bool = False) -> dict:
        result = self.check(force=force, include_report=True)
        if result["report"] is None:
            raise SaveError("Aucun rapport valide n’est encore disponible")
        report = result["report"]
        report["synchronisation"] = result["synchronisation"]
        return report