"""Cross-platform path discovery with explicit environment overrides."""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from agent_kits.domain.errors import PolicyError


def platform_name() -> str:
    """Map Python platform labels to the manifest platform vocabulary."""

    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    return "linux"


def _configured_path(environment_name: str, default: Path) -> Path:
    value = os.environ.get(environment_name)
    return Path(value).expanduser() if value else default.expanduser()


def user_state_root() -> Path:
    """Return a platform-appropriate, overrideable state root."""

    override = os.environ.get("AGENT_KITS_STATE_ROOT")
    if override:
        return Path(override).expanduser()
    if platform_name() == "windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "agent-kits"
    if platform_name() == "macos":
        return Path.home() / "Library" / "Application Support" / "agent-kits"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "agent-kits"


def user_client_root(client: str) -> Path:
    """Return an overrideable client configuration directory for user scope."""

    defaults = {
        "codex": Path.home() / ".codex",
        "claude-code": Path.home() / ".claude",
    }
    environment_names = {
        "codex": "AGENT_KITS_CODEX_USER_ROOT",
        "claude-code": "AGENT_KITS_CLAUDE_CODE_USER_ROOT",
    }
    return _configured_path(environment_names[client], defaults[client])


def project_state_root(project_root: Path) -> Path:
    """Keep project plans and receipts local but excluded from version control."""

    override = os.environ.get("AGENT_KITS_PROJECT_STATE_ROOT")
    return Path(override).expanduser() if override else project_root / ".agent-kits"


@dataclass(frozen=True)
class DoctorReport:
    """Read-only host facts exposed by the CLI."""

    platform: str
    python_version: str
    state_root: str
    clients: dict[str, dict[str, str | bool]]


def doctor_report() -> DoctorReport:
    """Inspect known configuration roots without creating them."""

    clients = {}
    for client in ("codex", "claude-code"):
        root = user_client_root(client)
        clients[client] = {"root": str(root), "exists": root.exists()}
    return DoctorReport(
        platform=platform_name(),
        python_version=".".join(str(value) for value in sys.version_info[:3]),
        state_root=str(user_state_root()),
        clients=clients,
    )


def ensure_contained(path: Path, root: Path) -> Path:
    """Reject path traversal and symlink escapes before any managed write."""

    root_absolute = Path(os.path.abspath(root))
    root_resolved = root.resolve()
    candidate = Path(os.path.abspath(path))
    try:
        relative = candidate.relative_to(root_absolute)
    except ValueError as error:
        raise PolicyError(f"Target escapes managed root: {path}") from error
    cursor = root_absolute
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise PolicyError(f"Managed path contains a symbolic link: {cursor}")
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(root_resolved)
    except ValueError as error:
        raise PolicyError(f"Target escapes managed root: {path}") from error
    return resolved_candidate
