#!/usr/bin/env python3

import json
import os
import sys
import tomllib
from pathlib import Path


CODEX_HOME = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
AGENT_CONFIG = CODEX_HOME / "agents" / "luna-worker.toml"
EXPECTED_AGENT = {
    "name": "luna_worker",
    "model": "gpt-5.6-luna",
    "model_reasoning_effort": "max",
}
OVERRIDE_FIELDS = ("model", "reasoning_effort", "model_reasoning_effort", "thinking")


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}, ensure_ascii=False))


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        deny("Blocked subagent spawn: invalid PreToolUse input.")
        return
    if not isinstance(event, dict) or event.get("hook_event_name") != "PreToolUse":
        deny("Blocked subagent spawn: unexpected hook event.")
        return
    if event.get("tool_name") not in {"Agent", "spawn_agent"}:
        deny("Blocked subagent spawn: unexpected tool name.")
        return
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        deny("Blocked subagent spawn: missing tool input.")
        return
    if tool_input.get("agent_type") != "luna_worker":
        deny("Only agent_type=luna_worker is allowed.")
        return
    fork_turns = tool_input.get("fork_turns")
    bounded_fork = isinstance(fork_turns, str) and fork_turns.isascii() and fork_turns.isdigit() and any(character != "0" for character in fork_turns)
    if fork_turns != "none" and not bounded_fork:
        deny("luna_worker requires fork_turns=none or a positive integer.")
        return
    if [field for field in OVERRIDE_FIELDS if tool_input.get(field) not in (None, "")]:
        deny("luna_worker model and reasoning overrides are not allowed.")
        return
    try:
        with AGENT_CONFIG.open("rb") as config_file:
            agent_config = tomllib.load(config_file)
    except (OSError, tomllib.TOMLDecodeError):
        deny("luna_worker configuration is missing or invalid.")
        return
    if any(agent_config.get(key) != value for key, value in EXPECTED_AGENT.items()):
        deny("luna_worker configuration does not match the required Luna profile.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        deny("Blocked subagent spawn: unexpected validation failure.")
