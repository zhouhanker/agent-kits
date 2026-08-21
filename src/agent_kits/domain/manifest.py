"""TOML readers with strict, dependency-free validation."""

from __future__ import annotations

import hashlib
import re
import tomllib
from pathlib import Path
from typing import Any

from agent_kits.domain.errors import NotFoundError, ValidationError
from agent_kits.domain.models import ComponentDefinition, KitManifest, KitTarget, Profile, SourceLock

IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")
PLATFORMS = frozenset({"macos", "windows", "linux"})
CLIENTS = frozenset({"codex", "claude-code"})
SCOPES = frozenset({"project", "user"})
COMPONENT_ALIAS_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,80}$")


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    except FileNotFoundError as error:
        raise NotFoundError(f"Missing declaration: {path}") from error
    except tomllib.TOMLDecodeError as error:
        raise ValidationError(f"Invalid TOML in {path}: {error}") from error
    if not isinstance(data, dict):
        raise ValidationError(f"Declaration must be a TOML table: {path}")
    return data


def _required_table(data: dict[str, Any], name: str, path: Path) -> dict[str, Any]:
    table = data.get(name)
    if not isinstance(table, dict):
        raise ValidationError(f"{path} must contain a [{name}] table")
    return table


def _required_string(table: dict[str, Any], key: str, path: Path) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{path}: {key} must be a non-empty string")
    return value


def _validate_identifier(value: str, label: str, path: Path) -> str:
    if not IDENTIFIER_RE.fullmatch(value):
        raise ValidationError(f"{path}: {label} must match {IDENTIFIER_RE.pattern}")
    return value


def _validate_version(value: str, path: Path) -> str:
    if not VERSION_RE.fullmatch(value):
        raise ValidationError(f"{path}: version must be major.minor.patch")
    return value


def _safe_relative_path(value: str, label: str, path: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or not value:
        raise ValidationError(f"{path}: {label} must be a safe relative path")
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_kit_manifest(path: Path) -> KitManifest:
    """Load a kit manifest and prove its payload declarations are intact."""

    data = _read_toml(path)
    kit = _required_table(data, "kit", path)
    if kit.get("schema_version") != 1:
        raise ValidationError(f"{path}: unsupported kit schema_version")
    identifier = _validate_identifier(_required_string(kit, "id", path), "kit.id", path)
    version = _validate_version(_required_string(kit, "version", path), path)
    description = _required_string(kit, "description", path)
    risk = _required_string(kit, "risk", path)
    if risk not in {"low", "medium", "high"}:
        raise ValidationError(f"{path}: unsupported risk {risk!r}")
    platforms_raw = kit.get("platforms")
    if not isinstance(platforms_raw, list) or not platforms_raw:
        raise ValidationError(f"{path}: kit.platforms must be a non-empty array")
    platforms = tuple(platforms_raw)
    if not all(isinstance(item, str) and item in PLATFORMS for item in platforms):
        raise ValidationError(f"{path}: kit.platforms contains an unsupported platform")

    targets_raw = data.get("targets")
    if not isinstance(targets_raw, list) or not targets_raw:
        raise ValidationError(f"{path}: at least one [[targets]] table is required")
    targets: list[KitTarget] = []
    for index, raw_target in enumerate(targets_raw):
        if not isinstance(raw_target, dict):
            raise ValidationError(f"{path}: targets[{index}] must be a table")
        client = _required_string(raw_target, "client", path)
        if client not in CLIENTS:
            raise ValidationError(f"{path}: targets[{index}].client is unsupported")
        target_path = _safe_relative_path(
            _required_string(raw_target, "path", path), "target path", path
        )
        payload_path = _safe_relative_path(
            _required_string(raw_target, "payload", path), "payload path", path
        )
        payload_sha256 = _required_string(raw_target, "payload_sha256", path)
        if not SHA256_RE.fullmatch(payload_sha256):
            raise ValidationError(f"{path}: targets[{index}].payload_sha256 is invalid")
        resolved_payload = (path.parent / payload_path).resolve()
        try:
            resolved_payload.relative_to(path.parent.resolve())
        except ValueError as error:
            raise ValidationError(f"{path}: payload escapes the kit directory") from error
        if resolved_payload.is_symlink() or not resolved_payload.is_file():
            raise ValidationError(f"{path}: payload does not exist: {payload_path}")
        if _sha256(resolved_payload) != payload_sha256:
            raise ValidationError(f"{path}: payload SHA-256 does not match: {payload_path}")
        strategy = _required_string(raw_target, "strategy", path)
        if strategy not in {"managed_markdown_block", "replace_file", "managed_json_hook", "managed_toml_bool"}:
            raise ValidationError(f"{path}: targets[{index}].strategy is unsupported")
        block_id = _validate_identifier(
            _required_string(raw_target, "block_id", path), "targets.block_id", path
        )
        scopes_raw = raw_target.get("scopes")
        if not isinstance(scopes_raw, list) or not scopes_raw:
            raise ValidationError(f"{path}: targets[{index}].scopes must be a non-empty array")
        scopes = tuple(scopes_raw)
        if not all(isinstance(scope, str) and scope in SCOPES for scope in scopes):
            raise ValidationError(f"{path}: targets[{index}].scopes contains an unsupported scope")
        targets.append(
            KitTarget(
                client=client,
                path=str(target_path),
                payload=str(payload_path),
                payload_sha256=payload_sha256,
                strategy=strategy,
                block_id=block_id,
                scopes=scopes,
            )
        )
    return KitManifest(identifier, version, description, risk, platforms, tuple(targets), path.parent)


def load_profile(path: Path) -> Profile:
    """Load a profile that selects source-controlled kits."""

    data = _read_toml(path)
    profile = _required_table(data, "profile", path)
    if profile.get("schema_version") != 1:
        raise ValidationError(f"{path}: unsupported profile schema_version")
    identifier = _validate_identifier(_required_string(profile, "id", path), "profile.id", path)
    description = _required_string(profile, "description", path)
    kits_raw = profile.get("kits")
    if not isinstance(kits_raw, list) or not kits_raw:
        raise ValidationError(f"{path}: profile.kits must be a non-empty array")
    kits = tuple(kits_raw)
    if not all(isinstance(kit, str) and IDENTIFIER_RE.fullmatch(kit) for kit in kits):
        raise ValidationError(f"{path}: profile.kits contains an invalid identifier")
    return Profile(identifier, description, kits)


def load_component_definitions(path: Path) -> list[ComponentDefinition]:
    """Load reusable component declarations without interpreting payload code."""

    data = _read_toml(path)
    if data.get("schema_version") != 1 or set(data) - {"schema_version", "components"}:
        raise ValidationError(f"{path}: unsupported component registry schema")
    entries = data.get("components")
    if not isinstance(entries, list) or not entries:
        raise ValidationError(f"{path}: components must be a non-empty array")
    definitions: list[ComponentDefinition] = []
    known_names: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) - {"id", "kit", "aliases", "scopes", "validator"}:
            raise ValidationError(f"{path}: components[{index}] has unsupported fields")
        identifier = _validate_identifier(_required_string(entry, "id", path), "components.id", path)
        kit_id = _validate_identifier(_required_string(entry, "kit", path), "components.kit", path)
        validator = _validate_identifier(_required_string(entry, "validator", path), "components.validator", path)
        aliases_raw = entry.get("aliases", [])
        if not isinstance(aliases_raw, list) or not all(isinstance(alias, str) and COMPONENT_ALIAS_RE.fullmatch(alias) for alias in aliases_raw):
            raise ValidationError(f"{path}: components[{index}].aliases contains an invalid alias")
        aliases = tuple(aliases_raw)
        scopes_raw = entry.get("scopes")
        if not isinstance(scopes_raw, list) or not scopes_raw or not all(isinstance(scope, str) and scope in SCOPES for scope in scopes_raw):
            raise ValidationError(f"{path}: components[{index}].scopes contains an unsupported scope")
        names = (identifier, *aliases)
        if len(set(names)) != len(names) or any(name in known_names for name in names):
            raise ValidationError(f"{path}: component IDs and aliases must be unique")
        known_names.update(names)
        definitions.append(ComponentDefinition(identifier, kit_id, aliases, tuple(scopes_raw), validator))
    return definitions


def load_source_lock(path: Path) -> SourceLock:
    """Load an external source lock without fetching or executing its source."""

    data = _read_toml(path)
    source = _required_table(data, "source", path)
    if source.get("schema_version") != 1:
        raise ValidationError(f"{path}: unsupported source schema_version")
    identifier = _validate_identifier(_required_string(source, "id", path), "source.id", path)
    version = _validate_version(_required_string(source, "version", path), path)
    upstream_url = _required_string(source, "upstream_url", path)
    if not upstream_url.startswith("https://"):
        raise ValidationError(f"{path}: upstream_url must use HTTPS")
    commit_sha = _required_string(source, "commit_sha", path)
    if not COMMIT_RE.fullmatch(commit_sha):
        raise ValidationError(f"{path}: commit_sha must be a full 40-character SHA")
    release_status = _required_string(source, "release_status", path)
    install_policy = _required_string(source, "install_policy", path)
    if release_status not in {"source-pinned", "release-pinned"}:
        raise ValidationError(f"{path}: unsupported release_status")
    if install_policy not in {"manual-only", "verified-release"}:
        raise ValidationError(f"{path}: unsupported install_policy")
    return SourceLock(
        identifier, version, upstream_url, commit_sha, release_status, install_policy, path
    )
