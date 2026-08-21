"""CLI use cases. This layer owns policy orchestration, not platform details."""

from __future__ import annotations

import json
import hashlib
import os
import platform
import re
import subprocess
import sys
import tempfile
import uuid
import urllib.error
from urllib.parse import urlparse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from agent_kits import __version__
from agent_kits.domain.errors import ConflictError, NotFoundError, PolicyError, ValidationError
from agent_kits.domain.manifest import load_kit_manifest
from agent_kits.infrastructure.paths import (
    doctor_report,
    ensure_contained,
    project_state_root,
    user_client_root,
    user_state_root,
)
from agent_kits.infrastructure.repository import (
    discover_repository,
    list_kits,
    list_source_locks,
    load_kit,
    load_repository_profile,
)
from agent_kits.infrastructure.sources import inspect_source, quarantine_source
from agent_kits.infrastructure.state import (
    canonical_json,
    read_json,
    sha256_file,
    state_file,
    write_json_atomic,
)


def _managed_block(block_id: str, payload: str) -> str:
    normalized = payload.rstrip("\n")
    return f"<!-- agent-kits:start {block_id} -->\n{normalized}\n<!-- agent-kits:end {block_id} -->"


def _render_managed_block(existing: str, block_id: str, payload: str) -> str:
    block = _managed_block(block_id, payload)
    start = f"<!-- agent-kits:start {block_id} -->"
    end = f"<!-- agent-kits:end {block_id} -->"
    if start in existing or end in existing:
        if start not in existing or end not in existing or existing.index(start) > existing.index(end):
            raise ValidationError(f"Malformed managed block: {block_id}")
        prefix, remainder = existing.split(start, 1)
        _, suffix = remainder.split(end, 1)
        return prefix + block + suffix
    if existing.strip():
        return existing.rstrip("\n") + "\n\n" + block + "\n"
    return block + "\n"


def _state_root(scope: str, project_root: Path) -> Path:
    return project_state_root(project_root) if scope == "project" else user_state_root()


def _target_root(scope: str, project_root: Path, client: str) -> Path:
    return project_root if scope == "project" else user_client_root(client)


def _json_target(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_target(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_target(item) for item in value]
    return value


def context(repository_arg: str | None, project_arg: str | None) -> tuple[Path, Path]:
    project_root = Path(project_arg).expanduser().resolve() if project_arg else Path.cwd().resolve()
    repository = Path(repository_arg).expanduser().resolve() if repository_arg else discover_repository(project_root)
    return repository, project_root


def run_doctor(repository: Path, project_root: Path) -> dict[str, Any]:
    report = doctor_report()
    return {
        "repository": str(repository),
        "project_root": str(project_root),
        "platform": report.platform,
        "python_version": report.python_version,
        "state_root": report.state_root,
        "clients": report.clients,
    }


def run_catalog_list(repository: Path) -> dict[str, Any]:
    kits = list_kits(repository)
    return {"kits": [{"id": kit.identifier, "version": kit.version, "risk": kit.risk, "description": kit.description, "targets": len(kit.targets)} for kit in kits]}


def run_source_inspect(source: str, max_bytes: int | None = None) -> dict[str, Any]:
    inspection = inspect_source(source, max_bytes or int(os.environ.get("AGENT_KITS_SOURCE_MAX_BYTES", "2097152")))
    return _json_target(inspection.__dict__)


def run_source_import(source: str, source_kind: str, state_root: Path | None = None) -> dict[str, Any]:
    return quarantine_source(source, source_kind, state_root)


def run_update_check(repository: Path, project_root: Path, target: str) -> dict[str, Any]:
    valid_targets = {"cli", "repository", "sources", "environment"}
    requested = valid_targets if target == "all" else {target}
    if not requested.issubset(valid_targets):
        raise ValidationError(f"Unsupported update target: {target}")
    result: dict[str, Any] = {}
    if "cli" in requested:
        result["cli"] = {"version": __version__, "update_mode": "external-package-manager", "actionable": False}
    if "repository" in requested:
        result["repository"] = {"path": str(repository), "update_mode": "reviewed-release", "actionable": False}
    if "sources" in requested:
        result["sources"] = [{"id": lock.identifier, "version": lock.version, "release_status": lock.release_status, "install_policy": lock.install_policy, "actionable": False} for lock in list_source_locks(repository)]
    if "environment" in requested:
        state = project_state_root(project_root)
        result["environment"] = {"state_root": str(state), "receipt_count": len(list((state / "receipts").glob("*.json"))) if state.exists() else 0, "actionable": False}
    return result


def _install_state_path() -> Path:
    """Return the installer metadata path without requiring third-party path libraries."""

    explicit = os.environ.get("KITCLI_INSTALL_STATE")
    if explicit:
        return Path(explicit).expanduser()
    if platform.system().lower() == "windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "kitcli" / "install.json"


def _download_update_asset(url: str, destination: Path, max_bytes: int) -> None:
    if not url.startswith("https://") or urlparse(url).hostname not in {"github.com", "api.github.com", "objects.githubusercontent.com"}:
        raise ValidationError("Update asset URL must use HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "kitcli-updater/1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as stream:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise ValidationError("Update asset exceeds the configured size limit")
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise ValidationError("Update asset exceeds the configured size limit")
                stream.write(chunk)
    except (OSError, ValueError, urllib.error.URLError) as error:
        if isinstance(error, ValidationError):
            raise
        raise ValidationError(f"Unable to download update asset: {error}") from error


def _wheel_version(path: Path) -> str:
    metadata_name = re.compile(r"^[^/]+\.dist-info/METADATA$")
    try:
        with zipfile.ZipFile(path) as archive:
            candidates = [name for name in archive.namelist() if metadata_name.fullmatch(name)]
            if len(candidates) != 1:
                raise ValidationError("Update wheel has an invalid metadata layout")
            for line in archive.read(candidates[0]).decode("utf-8").splitlines():
                if line.lower().startswith("version:"):
                    version = line.split(":", 1)[1].strip()
                    if version:
                        return version
    except (OSError, UnicodeError, zipfile.BadZipFile) as error:
        raise ValidationError(f"Unable to inspect update wheel: {error}") from error
    raise ValidationError("Update wheel does not declare a version")


def _verify_release_checksum(wheel: Path, checksum_file: Path, wheel_name: str) -> str:
    expected: str | None = None
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) >= 2 and Path(fields[-1].lstrip("*?")).name == wheel_name:
            expected = fields[0].lower()
            break
    if not expected or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValidationError(f"Release checksum does not contain {wheel_name}")
    actual = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if actual != expected:
        raise ValidationError("Release wheel SHA-256 verification failed")
    return actual


def run_update_cli(check_only: bool = False, yes: bool = False) -> dict[str, Any]:
    """Update a CLI installed by the official isolated installer.

    Conda, pip, pipx, and uv installs intentionally remain owned by their package
    managers. The installer metadata contains only HTTPS release URLs and a
    fixed Python executable path; no shell command from a remote source is run.
    """

    state_path = _install_state_path()
    if not state_path.is_file():
        raise ValidationError(
            "No kitcli installer metadata found; use the package manager that installed it "
            "(Conda, pipx, or uv), or reinstall with the official installer"
        )
    try:
        metadata = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(f"Invalid kitcli installer metadata: {error}") from error
    if not isinstance(metadata, dict):
        raise ValidationError("Invalid kitcli installer metadata: expected an object")
    if metadata.get("method") != "official-isolated-installer" or metadata.get("package") != "agent-kits":
        raise ValidationError("Unsupported kitcli installer metadata method")
    wheel_url = metadata.get("wheel_url")
    checksum_url = metadata.get("checksum_url")
    python_executable = metadata.get("python")
    if not all(isinstance(value, str) and value.startswith("https://") for value in (wheel_url, checksum_url)):
        raise ValidationError("Installer metadata contains an invalid HTTPS release URL")
    install_root = metadata.get("install_root")
    if not isinstance(python_executable, str) or not isinstance(install_root, str):
        raise ValidationError("Installer metadata is missing its isolated Python root")
    # A POSIX venv commonly stores ``bin/python`` as a symlink to the base
    # interpreter. Validate the recorded path lexically inside the isolated
    # root, while allowing that standard venv link to resolve outside it.
    python_path = Path(python_executable).expanduser()
    root_path = Path(install_root).expanduser()
    python_absolute = Path(os.path.abspath(python_path))
    root_absolute = Path(os.path.abspath(root_path))
    if root_absolute not in python_absolute.parents or not python_path.is_file():
        raise ValidationError("Installer metadata points to a missing Python executable")
    with tempfile.TemporaryDirectory(prefix="kitcli-update-") as temporary:
        directory = Path(temporary)
        wheel = directory / "kitcli-update.whl"
        checksums = directory / "SHA256SUMS"
        _download_update_asset(wheel_url, wheel, 64 * 1024 * 1024)
        _download_update_asset(checksum_url, checksums, 1024 * 1024)
        wheel_name = Path(urlparse(wheel_url).path).name
        if not wheel_name.startswith("agent_kits-") or not wheel_name.endswith("-py3-none-any.whl"):
            raise ValidationError("Update URL does not reference an agent-kits wheel")
        digest = _verify_release_checksum(wheel, checksums, wheel_name)
        version = _wheel_version(wheel)
        current = __version__
        if check_only:
            return {"current_version": current, "available_version": version, "update_available": version != current, "sha256": digest, "mode": "official-isolated-installer"}
        if not yes:
            raise PolicyError("CLI update writes the installed environment; rerun with --yes")
        command = [str(python_path), "-m", "pip", "install", "--upgrade", "--no-deps", str(wheel)]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as error:
            raise ValidationError(f"CLI package update failed: {error}") from error
    return {"current_version": current, "updated_version": version, "sha256": digest, "mode": "official-isolated-installer"}


def run_plan(repository: Path, project_root: Path, kit_id: str, scope: str, clients: list[str] | None, profile_id: str | None) -> dict[str, Any]:
    if scope not in {"project", "user"}:
        raise ValidationError("scope must be project or user")
    selected_kits = [kit_id]
    if profile_id:
        profile = load_repository_profile(repository, profile_id)
        if kit_id not in profile.kits:
            raise ValidationError(f"Kit {kit_id!r} is not selected by profile {profile_id!r}")
        selected_kits = list(profile.kits)
    platform = doctor_report().platform
    requested_clients = set(clients or [])
    targets: list[dict[str, Any]] = []
    for selected in selected_kits:
        kit = load_kit(repository, selected)
        if platform not in kit.platforms:
            raise PolicyError(f"Kit {kit.identifier} does not support platform {platform}")
        for target in kit.targets:
            if requested_clients and target.client not in requested_clients:
                continue
            if scope not in target.scopes:
                continue
            payload_path = kit.root / target.payload
            payload = payload_path.read_text(encoding="utf-8")
            root = _target_root(scope, project_root, target.client)
            target_path = ensure_contained(root / target.path, root)
            before_content = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
            after_content = _render_managed_block(before_content, target.block_id, payload)
            targets.append({
                "client": target.client,
                "scope": scope,
                "root": str(root.resolve()),
                "path": str(target_path),
                "block_id": target.block_id,
                "before_sha256": sha256_file(target_path),
                "after_sha256": __import__("hashlib").sha256(after_content.encode()).hexdigest(),
                "after_content": after_content,
            })
    if not targets:
        raise ValidationError("No compatible targets selected")
    state_root = _state_root(scope, project_root)
    plan_id = uuid.uuid4().hex
    plan = {"schema_version": 1, "plan_id": plan_id, "created_by": "agent-kits", "cli_version": __version__, "repository": str(repository), "project_root": str(project_root), "kit": kit_id, "profile": profile_id, "scope": scope, "targets": targets}
    plan["plan_sha256"] = __import__("hashlib").sha256(canonical_json(plan)).hexdigest()
    write_json_atomic(state_file(state_root, "plans", plan_id), plan)
    return _json_target(plan)


def _load_verified_plan(state_root: Path, plan_id: str) -> dict[str, Any]:
    plan = read_json(state_file(state_root, "plans", plan_id))
    digest = plan.pop("plan_sha256", None)
    if not isinstance(digest, str) or __import__("hashlib").sha256(canonical_json(plan)).hexdigest() != digest:
        raise ValidationError("Plan integrity check failed")
    plan["plan_sha256"] = digest
    return plan


def _load_verified_receipt(state_root: Path, receipt_id: str) -> dict[str, Any]:
    receipt = read_json(state_file(state_root, "receipts", receipt_id))
    digest = receipt.pop("receipt_sha256", None)
    if not isinstance(digest, str) or __import__("hashlib").sha256(canonical_json(receipt)).hexdigest() != digest:
        raise ValidationError("Receipt integrity check failed")
    receipt["receipt_sha256"] = digest
    return receipt


def run_apply(plan_id: str, scope: str, project_root: Path, confirm: bool) -> dict[str, Any]:
    state_root = _state_root(scope, project_root)
    plan = _load_verified_plan(state_root, plan_id)
    if not confirm:
        raise PolicyError("apply requires --yes; inspect the plan before writing")
    receipt_id = uuid.uuid4().hex
    backup_root = state_root / "backups" / receipt_id
    applied: list[dict[str, Any]] = []
    try:
        for index, item in enumerate(plan["targets"]):
            root = Path(item["root"])
            path = ensure_contained(Path(item["path"]), root)
            current_sha = sha256_file(path)
            if current_sha != item["before_sha256"]:
                raise ConflictError(f"Target changed after planning: {path}")
            backup_path = backup_root / f"target-{index}.bak"
            existed = path.exists()
            if existed:
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                backup_path.write_bytes(path.read_bytes())
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{receipt_id}.tmp")
            # Write bytes so the digest and managed content retain LF semantics
            # on Windows instead of inheriting the platform text newline mode.
            temporary.write_bytes(item["after_content"].encode("utf-8"))
            os.replace(temporary, path)
            applied.append({"path": str(path), "root": str(root), "before_sha256": item["before_sha256"], "after_sha256": item["after_sha256"], "backup": str(backup_path) if existed else None, "existed": existed})
    except Exception:
        for item in reversed(applied):
            path = Path(item["path"])
            if item["existed"]:
                path.write_bytes(Path(item["backup"]).read_bytes())
            elif path.exists():
                path.unlink()
        raise
    receipt = {"schema_version": 1, "receipt_id": receipt_id, "plan_id": plan_id, "scope": scope, "targets": applied, "status": "applied"}
    receipt["receipt_sha256"] = __import__("hashlib").sha256(canonical_json(receipt)).hexdigest()
    write_json_atomic(state_file(state_root, "receipts", receipt_id), receipt)
    return receipt


def run_verify(receipt_id: str, scope: str, project_root: Path) -> dict[str, Any]:
    receipt = _load_verified_receipt(_state_root(scope, project_root), receipt_id)
    checks = []
    for item in receipt.get("targets", []):
        current = sha256_file(Path(item["path"]))
        checks.append({"path": item["path"], "expected": item["after_sha256"], "actual": current, "ok": current == item["after_sha256"]})
    receipt["verification"] = checks
    receipt["verified"] = all(item["ok"] for item in checks)
    if not receipt["verified"]:
        raise ConflictError(json.dumps(receipt["verification"], sort_keys=True))
    return receipt


def run_rollback(receipt_id: str, scope: str, project_root: Path, confirm: bool) -> dict[str, Any]:
    if not confirm:
        raise PolicyError("rollback requires --yes")
    state_root = _state_root(scope, project_root)
    receipt = _load_verified_receipt(state_root, receipt_id)
    for item in receipt.get("targets", []):
        path = ensure_contained(Path(item["path"]), Path(item["root"]))
        if sha256_file(path) != item["after_sha256"]:
            raise ConflictError(f"Target changed after apply; refusing rollback: {path}")
    for item in receipt.get("targets", []):
        path = Path(item["path"])
        if item["existed"]:
            path.write_bytes(Path(item["backup"]).read_bytes())
        elif path.exists():
            path.unlink()
    receipt["status"] = "rolled_back"
    write_json_atomic(state_file(state_root, "receipts", receipt_id), receipt)
    return receipt
