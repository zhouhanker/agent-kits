"""CLI use cases. This layer owns policy orchestration, not platform details."""

from __future__ import annotations

import json
import hashlib
import os
import platform
import re
import shlex
import subprocess
import sys
import tempfile
import tomllib
import uuid
import urllib.error
from urllib.parse import urlparse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from agent_kits import __version__
from agent_kits.domain.errors import ConflictError, NotFoundError, PolicyError, ValidationError
from agent_kits.infrastructure.agents import (
    MODEL_API_IDENTIFIER,
    agent_report,
    analyze_model_api,
    analyze_source,
    check_agent_capability,
    check_model_api,
    select_agent,
)
from agent_kits.infrastructure.components import luna_candidate_sha256, luna_source_sha256, source_component, validate_luna_worker
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
    resolve_component,
)
from agent_kits.infrastructure.sandbox import sandbox_report, select_sandbox
from agent_kits.infrastructure.model_provider import model_provider_report
from agent_kits.infrastructure.sources import inspect_source, quarantine_source, read_inspected_source
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


def _render_managed_json_hook(existing: str, block_id: str, payload: str) -> str:
    """Merge one identifiable Hook group without changing other Hook groups."""

    try:
        document = json.loads(existing) if existing.strip() else {}
        group = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValidationError(f"Invalid managed Hook JSON: {error}") from error
    if not isinstance(document, dict) or not isinstance(group, dict):
        raise ValidationError("Managed Hook JSON must contain objects")
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValidationError("hooks.json hooks value must be an object")
    event = group.get("event")
    entries = group.get("entries")
    if event != "PreToolUse" or not isinstance(entries, list) or len(entries) != 1:
        raise ValidationError("Managed Hook payload must declare one PreToolUse group")
    entry = entries[0]
    if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
        raise ValidationError("Managed Hook payload has an invalid group")
    marker = f"agent-kits:{block_id}"
    existing_entries = hooks.get(event, [])
    if not isinstance(existing_entries, list):
        raise ValidationError(f"hooks.json {event} value must be an array")

    def owned(item: object) -> bool:
        return isinstance(item, dict) and any(
            isinstance(hook, dict) and hook.get("statusMessage") == marker
            for hook in item.get("hooks", [])
        )

    hooks[event] = [item for item in existing_entries if not owned(item)] + [entry]
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def _render_payload(payload: str, client_root: Path) -> str:
    """Expand the two path values permitted in source-controlled payloads."""

    values = {
        "{{python}}": shlex.quote(sys.executable),
        "{{client_root}}": shlex.quote(str(client_root)),
    }
    rendered = payload
    for placeholder, value in values.items():
        rendered = rendered.replace(placeholder, value)
    if re.search(r"\{\{[a-z_]+\}\}", rendered):
        raise ValidationError("Payload contains an unsupported template placeholder")
    return rendered


def _render_managed_toml_bool(existing: str, payload: str) -> str:
    """Set one declared top-level TOML boolean while retaining other tables."""

    try:
        declaration = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValidationError(f"Invalid managed TOML declaration: {error}") from error
    if declaration != {"table": "features", "key": "hooks", "value": True}:
        raise ValidationError("Unsupported managed TOML declaration")
    if not existing.strip():
        return "[features]\nhooks = true\n"
    try:
        parsed = tomllib.loads(existing)
    except tomllib.TOMLDecodeError as error:
        raise ValidationError(f"Invalid existing TOML configuration: {error}") from error
    current = parsed.get("features")
    if current is not None and (not isinstance(current, dict) or "hooks" in current and not isinstance(current["hooks"], bool)):
        raise ValidationError("config.toml features.hooks must be a boolean")
    table_match = re.search(r"(?m)^\[features\]\s*$", existing)
    if table_match is None:
        return existing.rstrip("\n") + "\n\n[features]\nhooks = true\n"
    next_table = re.search(r"(?m)^\[[^\]]+\]\s*$", existing[table_match.end():])
    end = table_match.end() + next_table.start() if next_table else len(existing)
    section = existing[table_match.end():end]
    hook_line = re.search(r"(?m)^\s*hooks\s*=\s*(?:true|false)\s*(?:#.*)?$", section)
    if hook_line is None:
        section = "\nhooks = true" + section
    else:
        section = section[:hook_line.start()] + "hooks = true" + section[hook_line.end():]
    return existing[:table_match.end()] + section + existing[end:]


def _render_target(existing: str, strategy: str, block_id: str, payload: str, client_root: Path) -> str:
    rendered_payload = _render_payload(payload, client_root)
    if strategy == "managed_markdown_block":
        return _render_managed_block(existing, block_id, rendered_payload)
    if strategy == "replace_file":
        return rendered_payload.rstrip("\n") + "\n"
    if strategy == "managed_json_hook":
        return _render_managed_json_hook(existing, block_id, rendered_payload)
    if strategy == "managed_toml_bool":
        return _render_managed_toml_bool(existing, rendered_payload)
    raise ValidationError(f"Unsupported target strategy: {strategy}")


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
        "agents": agent_report(),
        "models": [model_provider_report(repository)],
        "sandboxes": sandbox_report(),
    }


def run_agents_list(repository: Path) -> dict[str, Any]:
    """List local Agent and sandbox prerequisites without model invocation."""

    return {"agents": agent_report(), "models": [model_provider_report(repository)], "sandboxes": sandbox_report()}


def run_agents_check(repository: Path, agent_identifier: str) -> dict[str, Any]:
    """Run an explicit, metered local-Agent capability probe."""

    return check_model_api(repository) if agent_identifier == MODEL_API_IDENTIFIER else check_agent_capability(agent_identifier)


def run_catalog_list(repository: Path) -> dict[str, Any]:
    kits = list_kits(repository)
    return {"kits": [{"id": kit.identifier, "version": kit.version, "risk": kit.risk, "description": kit.description, "targets": len(kit.targets)} for kit in kits]}


def run_source_inspect(source: str, max_bytes: int | None = None) -> dict[str, Any]:
    inspection = inspect_source(source, max_bytes or int(os.environ.get("AGENT_KITS_SOURCE_MAX_BYTES", "2097152")))
    return _json_target(inspection.__dict__)


def run_source_import(source: str, source_kind: str, state_root: Path | None = None) -> dict[str, Any]:
    return quarantine_source(source, source_kind, state_root)


def run_source_intake(
    repository: Path,
    source: str,
    agent_identifier: str,
    scope: str,
    project_root: Path,
) -> dict[str, Any]:
    """Classify and dynamically validate a source without globally installing it."""

    if scope not in {"project", "user"}:
        raise ValidationError("source intake scope must be project or user")
    content, inspection = read_inspected_source(source)
    # Dynamic validation is mandatory for Agent-driven intake. Check before
    # invoking a metered local Agent so unavailable isolation has no model cost.
    select_sandbox()
    if agent_identifier == MODEL_API_IDENTIFIER:
        analysis = analyze_model_api(repository, source, content)
    else:
        agent = select_agent(agent_identifier)
        analysis = analyze_source(agent, source, content)
    component_id = source_component(repository, source, inspection.sha256, analysis.kind)
    result: dict[str, Any] = {
        "inspection": _json_target(inspection.__dict__),
        "analysis": _json_target(analysis.__dict__),
        "component_id": component_id,
        "installable": False,
    }
    if component_id == "luna-worker":
        if scope != "user":
            raise PolicyError("The Luna worker component supports user scope only")
        receipt = validate_luna_worker(repository, inspection.sha256, analysis.agent, _state_root(scope, project_root))
        result["validation"] = receipt
        result["installable"] = True
    return result


def run_component_create(
    repository: Path,
    project_root: Path,
    source: str,
    agent_identifier: str,
    identifier: str | None,
) -> dict[str, Any]:
    """Create a local review candidate without changing a client configuration."""

    # Luna is a user-scope component. This validates and records evidence only;
    # it does not call apply or alter the client configuration.
    intake = run_source_intake(repository, source, agent_identifier, "user", project_root)
    requested_id = identifier or intake.get("component_id")
    if requested_id is not None and (not isinstance(requested_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", requested_id)):
        raise ValidationError("Component ID must use lowercase letters, digits, and hyphens")
    status = "verified_candidate" if intake.get("installable") else "review_required"
    candidate_id = requested_id or f"source-{intake['inspection']['sha256'][:12]}"
    candidate = {
        "schema_version": 1,
        "candidate_id": candidate_id,
        "status": status,
        "source": intake["inspection"],
        "analysis": intake["analysis"],
        "component_id": intake.get("component_id"),
        "validation": intake.get("validation"),
    }
    candidate_path = project_state_root(project_root) / "candidates" / f"{candidate_id}.json"
    write_json_atomic(candidate_path, candidate)
    return {"candidate": candidate, "path": str(candidate_path), "installable": bool(intake.get("installable"))}


def _validated_component(repository: Path, component_id: str, validator: str, state_root: Path) -> bool:
    if validator != "luna-worker":
        raise ValidationError(f"Unsupported component validator: {validator}")
    candidate_sha256 = luna_candidate_sha256(repository)
    source_sha256 = luna_source_sha256(repository)
    validation_root = state_root / "validations"
    for path in validation_root.glob("*.json") if validation_root.is_dir() else []:
        try:
            receipt = read_json(path)
        except ValidationError:
            continue
        if receipt.get("status") == "validated" and receipt.get("component_id") == component_id and receipt.get("candidate_sha256") == candidate_sha256 and receipt.get("source_sha256") == source_sha256:
            return True
    return False


def run_install(
    repository: Path,
    project_root: Path,
    component_id: str,
    scope: str,
    confirm: bool,
) -> dict[str, Any]:
    """Install a reviewed component through the existing plan/apply transaction."""

    component = resolve_component(repository, component_id)
    if scope not in component.scopes:
        raise PolicyError(f"Component {component.identifier} does not support {scope} scope")
    state_root = _state_root(scope, project_root)
    if not _validated_component(repository, component.identifier, component.validator, state_root):
        raise PolicyError(f"Component {component.identifier} needs a current sandbox validation receipt before installation")
    plan = run_plan(repository, project_root, component.kit_id, scope, None, None)
    if not confirm:
        return {"component_id": component.identifier, "plan": plan, "installed": False}
    receipt = run_apply(plan["plan_id"], scope, project_root, True)
    return {"component_id": component.identifier, "plan": plan, "receipt": receipt, "installed": True}


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
        wheel_name = Path(urlparse(wheel_url).path).name
        if not wheel_name.startswith("agent_kits-") or not wheel_name.endswith("-py3-none-any.whl"):
            raise ValidationError("Update URL does not reference an agent-kits wheel")
        wheel = directory / wheel_name
        checksums = directory / "SHA256SUMS"
        _download_update_asset(wheel_url, wheel, 64 * 1024 * 1024)
        _download_update_asset(checksum_url, checksums, 1024 * 1024)
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
            after_content = _render_target(before_content, target.strategy, target.block_id, payload, root)
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
