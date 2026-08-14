from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os
import re
import struct

from .resources import load_hashes


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


def parse_file(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    if len(data) < 16 or data[-4:] != b"\xff\xff\xff\xff":
        raise SaveError(f"Fichier incomplet ou invalide : {path}")
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


_ITEMS_HASH = 0x5F283289
_ITEMS_QUANTITY_HASH = 0x6A09FC59
_ARMOR_RE = re.compile(r"Armor_\d{3}_(?:Head|Upper|Lower)$")


def _array_base(data: bytes, endian: str, hash_id: int) -> int:
    """Trouve le premier bloc d'un tableau GameData aligné sur 8 octets."""
    for offset in range(12, len(data) - 4, 8):
        if struct.unpack_from(endian + "I", data, offset)[0] == hash_id:
            return offset + 4
    raise SaveError(f"Tableau GameData 0x{hash_id:08x} introuvable")


def parse_inventory(path: Path) -> list[dict[str, object]]:
    """Lit les identifiants et quantités des emplacements d'inventaire BOTW."""
    data = path.read_bytes()
    if len(data) < 16 or data[-4:] != b"\xff\xff\xff\xff":
        raise SaveError(f"Fichier incomplet ou invalide : {path}")
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


def default_ryujinx_save_roots() -> list[Path]:
    """Emplacements connus, sans supposer lequel est utilisé par l'installation."""
    home = Path.home()
    roots = [
        home / "Library/Application Support/Ryujinx/bis/user/save",
        home / ".config/Ryujinx/bis/user/save",
    ]
    custom = os.environ.get("RYUJINX_DATA_DIR")
    if custom:
        roots.insert(0, Path(custom).expanduser() / "bis/user/save")
    return roots


def discover_ryujinx_save_root(search_roots: list[Path] | None = None) -> Path:
    """Trouve la sauvegarde BOTW la plus récente dans l'arborescence Ryujinx."""
    roots = search_roots if search_roots is not None else default_ryujinx_save_roots()
    candidates: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for game_data in root.rglob("game_data.sav"):
            slot = game_data.parent
            if (slot / "caption.sav").is_file():
                candidates.add(slot.parent)
    if not candidates:
        checked = ", ".join(str(path) for path in roots)
        raise SaveError(
            "Sauvegarde BOTW introuvable automatiquement dans Ryujinx. "
            "Dans Ryujinx : clic droit sur le jeu > Open User Save Directory, "
            f"puis passe ce dossier au programme. Emplacements vérifiés : {checked}"
        )
    return max(candidates, key=lambda root: find_latest_slot(root).timestamp)


def find_latest_slot(path: Path | str | None = None) -> SaveSlot:
    resolved = discover_ryujinx_save_root() if path is None else Path(path)
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


def identify_platform(path: Path) -> str:
    marker = path.read_bytes()[4:12]
    if marker == b"\xff\xff\xff\xff\x01\x00\x00\x00":
        return "Nintendo Switch / Ryujinx (little-endian)"
    if marker == b"\xff\xff\xff\xff\x00\x00\x00\x01":
        return "Wii U / Cemu (big-endian)"
    return "format inconnu"