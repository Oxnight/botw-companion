from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


MIN_CAPTION_BYTES = 128
MAX_CAPTION_BYTES = 10 * 1024 * 1024


class SaveCaptionError(ValueError):
    """Raised when the selected save has no safe, stable JPEG preview."""


@dataclass(frozen=True)
class SaveCaption:
    data: bytes
    etag: str


def read_selected_caption(report: object) -> SaveCaption:
    if not isinstance(report, dict):
        raise SaveCaptionError("Rapport de sauvegarde invalide")
    save = report.get("sauvegarde")
    if not isinstance(save, dict) or not isinstance(save.get("chemin"), str):
        raise SaveCaptionError("Slot sélectionné indisponible")

    slot = Path(save["chemin"]).expanduser()
    try:
        resolved_slot = slot.resolve(strict=True)
    except OSError as exc:
        raise SaveCaptionError("Dossier du slot sélectionné indisponible") from exc
    if not resolved_slot.is_dir():
        raise SaveCaptionError("Dossier du slot sélectionné invalide")

    caption = resolved_slot / "caption.jpg"
    if caption.is_symlink():
        raise SaveCaptionError("Aperçu symbolique refusé")
    try:
        resolved_caption = caption.resolve(strict=True)
        if resolved_caption.parent != resolved_slot or not resolved_caption.is_file():
            raise SaveCaptionError("Aperçu du slot invalide")
        before = resolved_caption.stat()
        if not MIN_CAPTION_BYTES <= before.st_size <= MAX_CAPTION_BYTES:
            raise SaveCaptionError("Taille de l’aperçu du slot invalide")
        data = resolved_caption.read_bytes()
        after = resolved_caption.stat()
    except SaveCaptionError:
        raise
    except OSError as exc:
        raise SaveCaptionError("Aperçu du slot indisponible") from exc

    stable_fields = ("st_size", "st_mtime_ns", "st_ctime_ns", "st_dev", "st_ino")
    if any(getattr(before, field, None) != getattr(after, field, None)
           for field in stable_fields) or len(data) != after.st_size:
        raise SaveCaptionError("Aperçu du slot en cours d’écriture")
    image_end = data.rfind(b"\xff\xd9")
    if (not data.startswith(b"\xff\xd8\xff") or image_end < 4
            or any(data[image_end + 2:])):
        raise SaveCaptionError("Aperçu du slot non reconnu comme JPEG")
    jpeg = data[:image_end + 2]
    return SaveCaption(data=jpeg, etag=sha256(jpeg).hexdigest())