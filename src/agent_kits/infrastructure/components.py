"""Known-component validation from immutable catalog payloads."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from agent_kits.domain.errors import PolicyError, ValidationError
from agent_kits.infrastructure.sandbox import SandboxBackend, select_sandbox, run_sandboxed
from agent_kits.infrastructure.state import state_file, write_json_atomic

LUNA_GUIDE_NAME = "CODEX_LUNA_WORKER_SETUP.md"
LUNA_COMPONENT_ID = "luna-worker"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_component(repository: Path, source: str, source_sha256: str, kind: str) -> str | None:
    """Resolve a known catalog component only when source bytes match its guide."""

    if kind != "codex_subagent" or luna_source_sha256(repository) != source_sha256:
        return None
    if Path(source.split("?", 1)[0]).name != LUNA_GUIDE_NAME:
        return None
    return LUNA_COMPONENT_ID


def _luna_backend() -> SandboxBackend:
    return select_sandbox()


def luna_candidate_sha256(repository: Path) -> str:
    """Return the digest that binds a Luna validation receipt to catalog payloads."""

    payload_root = repository / "catalog" / "kits" / LUNA_COMPONENT_ID / "payloads"
    names = ("luna-worker.toml", "enforce-luna-worker.py", "hooks.json", "features.json", "agents.md")
    paths = [payload_root / name for name in names]
    if any(not path.is_file() or path.is_symlink() for path in paths):
        raise ValidationError("Luna component payload is incomplete or unsafe")
    return hashlib.sha256(b"".join(path.read_bytes() for path in paths)).hexdigest()


def luna_source_sha256(repository: Path) -> str:
    """Return the current guide digest that authorizes Luna component validation."""

    guide = repository / "docs" / LUNA_GUIDE_NAME
    if not guide.is_file() or guide.is_symlink():
        raise ValidationError("Luna source guide is missing or unsafe")
    return _sha256(guide)


def _validator_program(codex_home: Path) -> str:
    root = repr(str(codex_home))
    return f"""
import ast
import contextlib
import io
import json
import os
import runpy
import sys
import tomllib
from pathlib import Path

root = Path({root})
with (root / 'agents' / 'luna-worker.toml').open('rb') as stream:
    agent = tomllib.load(stream)
assert agent['name'] == 'luna_worker'
assert agent['model'] == 'gpt-5.6-luna'
assert agent['model_reasoning_effort'] == 'max'
json.loads((root / 'hooks.json').read_text(encoding='utf-8'))
ast.parse((root / 'hooks' / 'enforce-luna-worker.py').read_text(encoding='utf-8'))

def invoke(event):
    original_stdin = sys.stdin
    output = io.StringIO()
    old_home = os.environ.get('CODEX_HOME')
    try:
        os.environ['CODEX_HOME'] = str(root)
        sys.stdin = io.StringIO(json.dumps(event))
        with contextlib.redirect_stdout(output):
            runpy.run_path(str(root / 'hooks' / 'enforce-luna-worker.py'), run_name='__main__')
    finally:
        sys.stdin = original_stdin
        if old_home is None:
            os.environ.pop('CODEX_HOME', None)
        else:
            os.environ['CODEX_HOME'] = old_home
    return output.getvalue()

valid = invoke({{'hook_event_name': 'PreToolUse', 'tool_name': 'spawn_agent', 'tool_input': {{'agent_type': 'luna_worker', 'fork_turns': '4'}}}})
assert valid == ''
invalid = invoke({{'hook_event_name': 'PreToolUse', 'tool_name': 'spawn_agent', 'tool_input': {{'agent_type': 'worker', 'fork_turns': '4'}}}})
assert 'permissionDecision' in invalid and 'deny' in invalid
print('LUNA_SANDBOX_VALID')
"""


def validate_luna_worker(repository: Path, source_sha256: str, agent: str, state_root: Path) -> dict[str, Any]:
    """Validate the catalog Luna component in an isolated temporary CODEX_HOME."""

    component_root = repository / "catalog" / "kits" / LUNA_COMPONENT_ID
    payload_root = component_root / "payloads"
    required = {
        "agent": payload_root / "luna-worker.toml",
        "hook": payload_root / "enforce-luna-worker.py",
        "hooks": payload_root / "hooks.json",
        "features": payload_root / "features.json",
        "instructions": payload_root / "agents.md",
    }
    candidate_sha256 = luna_candidate_sha256(repository)
    with tempfile.TemporaryDirectory(prefix="kitcli-luna-validation-") as directory:
        root = Path(directory)
        codex_home = root / ".codex"
        (codex_home / "agents").mkdir(parents=True)
        (codex_home / "hooks").mkdir(parents=True)
        (codex_home / "agents" / "luna-worker.toml").write_bytes(required["agent"].read_bytes())
        (codex_home / "hooks" / "enforce-luna-worker.py").write_bytes(required["hook"].read_bytes())
        hook_payload = json.loads(required["hooks"].read_text(encoding="utf-8"))
        hooks = {"hooks": {hook_payload["event"]: hook_payload["entries"]}}
        (codex_home / "hooks.json").write_text(json.dumps(hooks, indent=2) + "\n", encoding="utf-8")
        (codex_home / "config.toml").write_text("[features]\nhooks = true\n", encoding="utf-8")
        command = ["/usr/local/bin/python", "-c", _validator_program(Path("/workspace/.codex"))]
        result = run_sandboxed(root, command, _luna_backend())
    if result.returncode != 0 or "LUNA_SANDBOX_VALID" not in result.stdout:
        detail = (result.stderr or result.stdout).strip()[-1000:]
        raise PolicyError(
            f"Luna sandbox validation failed via {result.backend} (exit {result.returncode}): "
            f"{detail or 'validator did not pass'}"
        )
    receipt_seed = f"{source_sha256}:{candidate_sha256}:{agent}:{result.backend}".encode("utf-8")
    receipt_id = hashlib.sha256(receipt_seed).hexdigest()[:32]
    receipt = {
        "schema_version": 1,
        "receipt_id": receipt_id,
        "component_id": LUNA_COMPONENT_ID,
        "source_sha256": source_sha256,
        "candidate_sha256": candidate_sha256,
        "agent": agent,
        "sandbox_backend": result.backend,
        "status": "validated",
    }
    write_json_atomic(state_file(state_root, "validations", receipt_id), receipt)
    return receipt
