"""Immutable data models shared by commands and infrastructure adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KitTarget:
    """One client-specific destination declared by a kit."""

    client: str
    path: str
    payload: str
    payload_sha256: str
    strategy: str
    block_id: str
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class KitManifest:
    """Validated, source-controlled kit declaration."""

    identifier: str
    version: str
    description: str
    risk: str
    platforms: tuple[str, ...]
    targets: tuple[KitTarget, ...]
    root: Path


@dataclass(frozen=True)
class Profile:
    """A non-sensitive selection of source-controlled kits."""

    identifier: str
    description: str
    kits: tuple[str, ...]


@dataclass(frozen=True)
class SourceLock:
    """A declarative external integration lock, never executable source."""

    identifier: str
    version: str
    upstream_url: str
    commit_sha: str
    release_status: str
    install_policy: str
    path: Path
