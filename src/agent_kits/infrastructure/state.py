"""Plan, receipt, backup, and local state persistence."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from agent_kits.domain.errors import NotFoundError, ValidationError


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise ValidationError(f"Managed target must be a regular file: {path}")
    return sha256_bytes(path.read_bytes())


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json(value)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise NotFoundError(f"Missing state file: {path}") from error
    except json.JSONDecodeError as error:
        raise ValidationError(f"Invalid JSON state: {path}") from error
    if not isinstance(value, dict):
        raise ValidationError(f"State must be a JSON object: {path}")
    return value


def state_paths(state_root: Path) -> dict[str, Path]:
    return {
        "plans": state_root / "plans",
        "receipts": state_root / "receipts",
        "validations": state_root / "validations",
        "backups": state_root / "backups",
    }


def state_file(state_root: Path, kind: str, identifier: str) -> Path:
    paths = state_paths(state_root)
    if kind not in paths or Path(identifier).name != identifier:
        raise ValidationError("Invalid state kind or identifier")
    return paths[kind] / f"{identifier}.json"
