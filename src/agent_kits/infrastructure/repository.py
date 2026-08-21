"""Repository discovery and source-controlled declaration access."""

from __future__ import annotations

from pathlib import Path

from agent_kits.domain.errors import NotFoundError
from agent_kits.domain.manifest import load_component_definitions, load_kit_manifest, load_profile, load_source_lock
from agent_kits.domain.models import ComponentDefinition, KitManifest, Profile, SourceLock


def discover_repository(start: Path) -> Path:
    """Find the nearest directory containing the agent-kits project metadata."""

    candidate = start.resolve()
    for current in (candidate, *candidate.parents):
        metadata = current / "pyproject.toml"
        if metadata.is_file() and (current / "catalog").is_dir():
            return current
    raise NotFoundError("Could not find an agent-kits repository; pass --repository")


def list_kits(repository: Path) -> list[KitManifest]:
    """Return all kits, failing closed if any checked-in manifest is invalid."""

    manifests = sorted((repository / "catalog" / "kits").glob("*/manifest.toml"))
    return [load_kit_manifest(path) for path in manifests]


def load_kit(repository: Path, identifier: str) -> KitManifest:
    """Load one kit by stable ID."""

    path = repository / "catalog" / "kits" / identifier / "manifest.toml"
    return load_kit_manifest(path)


def load_repository_profile(repository: Path, identifier: str) -> Profile:
    """Load one profile by stable ID."""

    return load_profile(repository / "profiles" / identifier / "profile.toml")


def resolve_component(repository: Path, identifier: str) -> ComponentDefinition:
    """Resolve only a source-controlled reusable component ID or alias."""

    registry = repository / "catalog" / "components.toml"
    for component in load_component_definitions(registry):
        if identifier == component.identifier or identifier in component.aliases:
            return component
    raise NotFoundError(f"Unknown reusable component: {identifier}; use plan/apply for ordinary catalog kits")


def list_source_locks(repository: Path) -> list[SourceLock]:
    """Read external locks without accessing their upstreams."""

    locks = sorted((repository / "catalog" / "integrations" / "external").glob("*/source-lock.toml"))
    return [load_source_lock(path) for path in locks]
