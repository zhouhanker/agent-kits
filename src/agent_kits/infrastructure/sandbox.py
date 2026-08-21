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


def _docker_available() -> bool:
    executable = shutil.which("docker")
    if executable is None:
        return False
    try:
        result = subprocess.run([executable, "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True, timeout=5, check=False)
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

    return [SandboxBackend("docker", _docker_available(), "Docker daemon with no-network container support")]


def sandbox_report() -> list[dict[str, object]]:
    """Return serializable sandbox availability data."""

    return [asdict(backend) for backend in discover_sandboxes()]


def select_sandbox() -> SandboxBackend:
    """Select the preferred executable backend or fail before candidate execution."""

    available = {backend.identifier: backend for backend in discover_sandboxes() if backend.available}
    if "docker" in available:
        _docker_image()
        return available["docker"]
    raise PolicyError("No supported sandbox backend is available; start Docker before dynamic validation")


def _run_docker(root: Path, command: list[str], timeout: int) -> SandboxResult:
    executable = shutil.which("docker")
    if executable is None or not _docker_available():
        raise PolicyError("Docker sandbox is unavailable")
    image = _docker_image()
    docker_command = [
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
        result = subprocess.run(docker_command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PolicyError(f"Docker sandbox validation failed: {error}") from error
    return SandboxResult("docker", result.returncode, result.stdout[-4000:], result.stderr[-4000:])


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
    if selected.identifier == "docker":
        return _run_docker(root, command, timeout)
    raise ValidationError(f"Unsupported sandbox backend: {selected.identifier}")
