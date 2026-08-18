from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import struct

from .resources import load_hashes
from .platforms import ryujinx_save_roots
from .emulators import EmulatorBackend, emulator_for_path, emulator_save_roots, running_emulators


class SaveError(ValueError):
    pass


@dataclass(frozen=True)
class SaveSlot:
    path: Path
    timestamp: int

    @property
    def date(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)


def _endian(data: bytes) -> str:
    marker = data[4:12]
    if marker == b"\xff\xff\xff\xff\x00\x00\x00\x01":
        return ">"
    if marker == b"\xff\xff\xff\xff\x01\x00\x00\x00":
        return "<"
    raise SaveError("Format de sauvegarde BOTW non reconnu")


def parse_data(data: bytes, source: str | Path = "mémoire") -> dict[str, object]:
    if len(data) < 16 or data[-4:] != b"\xff\xff\xff\xff":
        raise SaveError(f"Fichier incomplet ou invalide : {source}")
    endian = _endian(data)
    hashes = load_hashes()
    result: dict[str, object] = {}

    # Les entrées GameData sont alignées sur 8 octets : hash u32 + valeur.
    # Les scalaires suffisent au comparateur. Parcourir chaque bloc reste sûr
    # pour les chaînes/tableaux : leurs blocs de données ne correspondent en
    # pratique à aucun hash recherché et sont ignorés.
    for offset in range(12, len(data) - 4, 8):
        hash_id = struct.unpack_from(endian + "I", data, offset)[0]
        descriptor = hashes.get(hash_id)
        if descriptor is None:
            continue
        type_id, name = descriptor
        raw = data[offset + 4 : offset + 8]
        if type_id == 1:
            result[name] = struct.unpack(endian + "I", raw)[0] != 0
        elif type_id == 3:
            result[name] = struct.unpack(endian + "i", raw)[0]
        elif type_id == 5:
            result[name] = struct.unpack(endian + "f", raw)[0]
    return result


def parse_file(path: Path) -> dict[str, object]:
    return parse_data(path.read_bytes(), path)


_ITEMS_HASH = 0x5F283289
_ITEMS_QUANTITY_HASH = 0x6A09FC59
_ARMOR_RE = re.compile(r"Armor_\d{3}_(?:Head|Upper|Lower)$")


def _array_base(data: bytes, endian: str, hash_id: int) -> int:
    """Trouve le premier bloc d'un tableau GameData aligné sur 8 octets."""
    for offset in range(12, len(data) - 4, 8):
        if struct.unpack_from(endian + "I", data, offset)[0] == hash_id:
            return offset + 4
    raise SaveError(f"Tableau GameData 0x{hash_id:08x} introuvable")


def parse_inventory_data(data: bytes, source: str | Path = "mémoire") -> list[dict[str, object]]:
    """Lit les identifiants et quantités des emplacements d'inventaire BOTW."""
    if len(data) < 16 or data[-4:] != b"\xff\xff\xff\xff":
        raise SaveError(f"Fichier incomplet ou invalide : {source}")
    endian = _endian(data)
    names_base = _array_base(data, endian, _ITEMS_HASH)
    quantities_base = _array_base(data, endian, _ITEMS_QUANTITY_HASH)
    inventory: list[dict[str, object]] = []
    for slot in range(420):
        offset = names_base + slot * 0x80
        if offset + 0x80 > len(data):
            break
        raw = b"".join(data[offset + part * 8:offset + part * 8 + 4] for part in range(16))
        actor = raw.split(b"\0", 1)[0].decode("ascii", errors="ignore")
        if not actor:
            break
        quantity_offset = quantities_base + slot * 8
        quantity = struct.unpack_from(endian + "I", data, quantity_offset)[0]
        inventory.append({
            "slot": slot,
            "id": actor,
            "quantite": quantity,
            "armure": bool(_ARMOR_RE.fullmatch(actor)),
        })
    return inventory


def parse_inventory(path: Path) -> list[dict[str, object]]:
    return parse_inventory_data(path.read_bytes(), path)


def _candidate_slots(path: Path) -> list[Path]:
    path = path.expanduser().resolve()
    if (path / "caption.sav").is_file() and (path / "game_data.sav").is_file():
        return [path]
    if not path.is_dir():
        raise SaveError(f"Dossier introuvable : {path}")
    return sorted(
        child for child in path.iterdir()
        if child.is_dir()
        and (child / "caption.sav").is_file()
        and (child / "game_data.sav").is_file()
    )


def find_game_save_roots(search_roots: list[tuple[EmulatorBackend, Path]] | None = None) -> list[tuple[EmulatorBackend, Path]]:
    """Recense les sauvegardes BOTW de tous les émulateurs supportés."""
    roots = search_roots if search_roots is not None else emulator_save_roots()
    candidates: dict[Path, EmulatorBackend] = {}
    for backend, root in roots:
        try:
            if not root.is_dir():
                continue
            for filename in ("caption.sav", "game_data.sav"):
                for save_file in root.rglob(filename):
                    slot = save_file.parent
                    game_root = slot.parent if slot.parent != root and slot.parent.is_dir() else slot
                    candidates[game_root] = backend
        except OSError:
            continue
    return sorted(((backend, path) for path, backend in candidates.items()),
                  key=lambda item: (item[0].id, str(item[1]).casefold()))


def discover_save_root(search_roots: list[tuple[EmulatorBackend, Path]] | None = None) -> tuple[EmulatorBackend, Path]:
    """Trouve la sauvegarde BOTW la plus récente entre Ryujinx et Cemu."""
    roots = search_roots if search_roots is not None else emulator_save_roots()
    candidates = find_game_save_roots(roots)
    active = {backend.id for backend in running_emulators()}
    if len(active) == 1:
        active_candidates = [item for item in candidates if item[0].id in active]
        if active_candidates:
            candidates = active_candidates
    readable: list[tuple[int, EmulatorBackend, Path]] = []
    for backend, candidate in candidates:
        try:
            readable.append((find_latest_slot(candidate).timestamp, backend, candidate))
        except (OSError, SaveError):
            continue
    if not readable:
        checked = ", ".join(f"{backend.label}: {path}" for backend, path in roots)
        raise SaveError(
            "Sauvegarde BOTW introuvable automatiquement dans Ryujinx ou Cemu. "
            f"Emplacements vérifiés : {checked}"
        )
    _timestamp, backend, path = max(readable, key=lambda item: (item[0], item[1].id, str(item[2]).casefold()))
    return backend, path


def detect_save_emulator(path: Path | str) -> EmulatorBackend | None:
    resolved = Path(path).expanduser().resolve()
    inferred = emulator_for_path(resolved)
    if inferred is not None:
        return inferred
    try:
        platform_name = identify_platform(resolved / "game_data.sav" if (resolved / "game_data.sav").is_file() else find_latest_slot(resolved).path / "game_data.sav")
    except (OSError, SaveError):
        return None
    from .emulators import CEMU, RYUJINX
    return CEMU if "Cemu" in platform_name else RYUJINX if "Ryujinx" in platform_name else None


def default_ryujinx_save_roots() -> list[Path]:
    """Emplacements connus, sans supposer lequel est utilisé par l'installation."""
    return ryujinx_save_roots()


def find_ryujinx_game_save_roots(search_roots: list[Path] | None = None) -> list[Path]:
    """Recense les dossiers de sauvegarde candidats, y compris en cours d'écriture."""
    roots = search_roots if search_roots is not None else default_ryujinx_save_roots()
    candidates: set[Path] = set()
    for root in roots:
        try:
            if not root.is_dir():
                continue
            for filename in ("caption.sav", "game_data.sav"):
                for save_file in root.rglob(filename):
                    slot = save_file.parent
                    if slot.parent != root and slot.parent.is_dir():
                        candidates.add(slot.parent)
        except OSError:
            continue
    return sorted(candidates, key=lambda path: str(path).casefold())


def discover_ryujinx_save_root(search_roots: list[Path] | None = None) -> Path:
    """Trouve la sauvegarde BOTW la plus récente dans l'arborescence Ryujinx."""
    roots = search_roots if search_roots is not None else default_ryujinx_save_roots()
    candidates = find_ryujinx_game_save_roots(roots)
    readable = []
    for candidate in candidates:
        try:
            readable.append((find_latest_slot(candidate).timestamp, candidate))
        except (OSError, SaveError):
            continue
    if not readable:
        checked = ", ".join(str(path) for path in roots)
        raise SaveError(
            "Sauvegarde BOTW introuvable automatiquement dans Ryujinx. "
            "Dans Ryujinx : clic droit sur le jeu > Open User Save Directory, "
            f"puis passe ce dossier au programme. Emplacements vérifiés : {checked}"
        )
    return max(readable, key=lambda item: (item[0], str(item[1]).casefold()))[1]


def find_latest_slot(path: Path | str | None = None) -> SaveSlot:
    resolved = discover_save_root()[1] if path is None else Path(path)
    candidates = _candidate_slots(resolved)
    if not candidates:
        raise SaveError("Aucun slot contenant caption.sav et game_data.sav")
    slots: list[SaveSlot] = []
    errors: list[str] = []
    for candidate in candidates:
        try:
            caption = parse_file(candidate / "caption.sav")
            timestamp = int(caption.get("LastSaveTime_Lower", 0))
            slots.append(SaveSlot(candidate, timestamp))
        except (OSError, SaveError) as exc:
            errors.append(f"{candidate.name}: {exc}")
    if not slots:
        raise SaveError("Aucun slot lisible. " + "; ".join(errors))
    return max(slots, key=lambda slot: (slot.timestamp, slot.path.name))


def load_save(path: Path | str | None = None) -> tuple[SaveSlot, dict[str, object], dict[str, object]]:
    slot = find_latest_slot(path)
    return slot, parse_file(slot.path / "caption.sav"), parse_file(slot.path / "game_data.sav")


def identify_platform_data(data: bytes) -> str:
    marker = data[4:12]
    if marker == b"\xff\xff\xff\xff\x01\x00\x00\x00":
        return "Nintendo Switch / Ryujinx (little-endian)"
    if marker == b"\xff\xff\xff\xff\x00\x00\x00\x01":
        return "Wii U / Cemu (big-endian)"
    return "format inconnu"


def identify_platform(path: Path) -> str:
    return identify_platform_data(path.read_bytes())