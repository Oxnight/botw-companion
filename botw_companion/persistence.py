from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from sys import platform as _platform


def _replace_file(source: Path, destination: Path) -> None:
    # Windows rename/delete sharing can briefly reject concurrent publishers
    # or readers. Keep the same complete temporary file and never unlink the
    # destination to work around it. Permanent errors still reach the caller.
    for attempt in range(8):
        try:
            os.replace(source, destination)
            return
        except OSError as exc:
            if (_platform != "win32" or getattr(exc, "winerror", None) not in (5, 32, 33)
                    or attempt == 7):
                raise
            time.sleep(min(0.01 * (2 ** attempt), 0.1))


def read_json(path: Path) -> object:
    try:
        return decode_json(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as exc:
        # Invalid encoding is a corrupt JSON file too. Every store must take
        # its existing recovery path without overwriting the damaged original.
        raise json.JSONDecodeError("Invalid UTF-8 JSON", "", 0) from exc


def decode_json(text: str) -> object:
    """Accept only JSON that can round-trip through a UTF-8 browser response."""
    try:
        payload = json.loads(text)
        pending = [(payload, 0)]
        while pending:
            value, depth = pending.pop()
            if depth > 64:
                raise ValueError("Excessive JSON nesting")
            if isinstance(value, dict):
                pending.extend((child, depth + 1) for child in value.values())
            elif isinstance(value, list):
                pending.extend((child, depth + 1) for child in value)
        # Python accepts non-finite numbers and isolated UTF-16 surrogates;
        # browsers reject the former and UTF-8 cannot encode the latter.
        json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return payload
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise json.JSONDecodeError("Invalid interoperable JSON", "", 0) from exc


def atomic_write_json(path: Path, payload: object) -> object:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _replace_file(temporary, path)
        _sync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return deepcopy(payload)


def copy_valid_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        shutil.copy2(source, temporary)
        temporary.chmod(0o600)
        with temporary.open("r+b") as stream:
            os.fsync(stream.fileno())
        _replace_file(temporary, destination)
        _sync_directory(destination.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def migration_backup_path(path: Path, source_version: int) -> Path:
    return path.with_name(f"{path.stem}.pre-migration-v{source_version}{path.suffix}")


def restore_bytes(path: Path, content: bytes | None) -> None:
    if content is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        _sync_directory(path.parent)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".restore.tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        _replace_file(temporary, path)
        _sync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
