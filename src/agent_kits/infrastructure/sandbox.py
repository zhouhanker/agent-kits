"""Fail-closed execution backends for bounded component validation."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from agent_kits.domain.errors import PolicyError, ValidationError

DEFAULT_SANDBOX_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class SandboxBackend:
    """A host execution backend that can isolate a fixed validation command."""

    identifier: str
    available: bool
    detail: str


@dataclass(frozen=True)
class SandboxResult:
    """Bounded result of a sandboxed validation command."""

    backend: str
    returncode: int
    stdout: str
    stderr: str


def _timeout() -> int:
    raw = os.environ.get("AGENT_KITS_SANDBOX_TIMEOUT_SECONDS", str(DEFAULT_SANDBOX_TIMEOUT_SECONDS))
    try:
        value = int(raw)
    except ValueError as error:
        raise ValidationError("AGENT_KITS_SANDBOX_TIMEOUT_SECONDS must be an integer") from error
    if value < 1 or value > 300:
        raise ValidationError("AGENT_KITS_SANDBOX_TIMEOUT_SECONDS must be between 1 and 300")
    return value


def _container_available(identifier: str) -> bool:
    executable = shutil.which(identifier)
    if executable is None:
        return False
    command = [executable, "info", "--format", "{{.ServerVersion}}"] if identifier == "docker" else [executable, "info", "--format", "{{.Version.Version}}"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def _docker_image() -> str:
    image = os.environ.get("AGENT_KITS_SANDBOX_IMAGE", "")
    if not image or "@sha256:" not in image or any(character.isspace() for character in image):
        raise PolicyError("AGENT_KITS_SANDBOX_IMAGE must be a digest-pinned Docker image")
    return image


def discover_sandboxes() -> list[SandboxBackend]:
    """Report real backend availability without running a candidate command."""

    return [
        SandboxBackend("docker", _container_available("docker"), "Docker Engine or Docker Desktop with no-network container support"),
        SandboxBackend("podman", _container_available("podman"), "Podman machine/service with no-network container support"),
    ]


def sandbox_report() -> list[dict[str, object]]:
    """Return serializable sandbox availability data."""

    return [asdict(backend) for backend in discover_sandboxes()]


def select_sandbox() -> SandboxBackend:
    """Select the preferred executable backend or fail before candidate execution."""

    available = {backend.identifier: backend for backend in discover_sandboxes() if backend.available}
    for identifier in ("docker", "podman"):
        if identifier not in available:
            continue
        _docker_image()
        return available[identifier]
    raise PolicyError("No supported sandbox backend is available; start Docker Desktop, Docker Engine, or Podman before dynamic validation")


def _run_container(backend: SandboxBackend, root: Path, command: list[str], timeout: int) -> SandboxResult:
    executable = shutil.which(backend.identifier)
    if executable is None or not _container_available(backend.identifier):
        raise PolicyError(f"{backend.identifier} sandbox is unavailable")
    image = _docker_image()
    container_command = [
        executable,
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--volume",
        f"{root}:/workspace:rw",
        "--workdir",
        "/workspace",
        image,
        *command,
    ]
    try:
        result = subprocess.run(container_command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PolicyError(f"{backend.identifier} sandbox validation failed: {error}") from error
    return SandboxResult(backend.identifier, result.returncode, result.stdout[-4000:], result.stderr[-4000:])


def run_sandboxed(root: Path, command: list[str], backend: SandboxBackend | None = None) -> SandboxResult:
    """Run only a trusted, fixed verifier under a selected sandbox backend."""

    if not command or not Path(command[0]).is_absolute():
        raise ValidationError("Sandbox verifier must use an absolute executable path")
    if not root.is_dir() or root.is_symlink():
        raise PolicyError("Sandbox root must be a regular directory")
    selected = backend or select_sandbox()
    if not selected.available:
        raise PolicyError(f"Sandbox backend is unavailable: {selected.identifier}")
    timeout = _timeout()
    if selected.identifier in {"docker", "podman"}:
        return _run_container(selected, root, command, timeout)
    raise ValidationError(f"Unsupported sandbox backend: {selected.identifier}")
