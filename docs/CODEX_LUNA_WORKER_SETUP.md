# Codex 全局 Luna-only 子代理设置指南

本文用于在个人 Codex 环境中创建一个全局 `luna_worker` 自定义子代理，并通过 `PreToolUse` Hook 强制所有子代理调用只能使用：

- `agent_type = "luna_worker"`
- `model = "gpt-5.6-luna"`
- `model_reasoning_effort = "max"`
- `fork_turns = "none"` 或正整数字符串
- 不允许在调用时覆盖模型或推理强度

完成后，主代理仍可使用原来的模型；只有子代理被限制为 Luna。

## 适用范围

本指南适用于支持以下能力的新版 Codex Desktop、Codex CLI 或 IDE 扩展：

- 自定义子代理目录 `~/.codex/agents/`
- `PreToolUse` Hook
- `/hooks` 信任管理
- `gpt-5.6-luna` 和 `max` 推理强度

如果 `/hooks` 不存在，或者客户端不能解析 `model_reasoning_effort = "max"`，当前客户端版本不适用。不要在未验证的旧客户端中宣称 Hook 已生效。

官方资料：

- [Codex Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Codex Hooks](https://learn.chatgpt.com/docs/hooks)
- [Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)

## 约束结构

| 层级 | 作用 | 是否能阻止违规调用 |
|---|---|---:|
| `luna-worker.toml` | 定义 Luna 子代理的模型和工作方式 | 否 |
| `AGENTS.md` | 要求主代理主动选择 `luna_worker` | 否 |
| `PreToolUse` Hook | 检查真实调用参数并拒绝违规调用 | 是 |
| `/hooks` 信任 | 允许非托管 command Hook 真正运行 | 必需 |

不要只设置默认子代理模型。默认值可能被显式 spawn 参数覆盖，不能构成强制约束。

## 一、安装前检查

先确认 Codex 和 Python 环境：

```bash
codex --version
codex features list
command -v python3
python3 -c 'import tomllib; print("tomllib available")'
```

要求：

- Codex 支持 `/hooks`。
- `hooks` 功能处于启用状态。
- Python 支持 `tomllib`，通常需要 Python 3.11 或更高版本。
- 记录 `command -v python3` 输出的绝对路径，后面需要写入 `hooks.json`。

如果用户设置了 `CODEX_HOME`，下文所有 `~/.codex` 都应替换为真实的 `CODEX_HOME`。

## 二、检查现有配置

不要直接覆盖已有文件。先检查：

```bash
test -f ~/.codex/agents/luna-worker.toml \
  && sed -n '1,160p' ~/.codex/agents/luna-worker.toml

test -f ~/.codex/hooks.json \
  && sed -n '1,260p' ~/.codex/hooks.json

test -f ~/.codex/AGENTS.md \
  && sed -n '1,260p' ~/.codex/AGENTS.md
```

处理原则：

- `luna-worker.toml` 已存在时，先核对内容，再决定是否更新。
- `hooks.json` 已存在时，只合并新的 `PreToolUse` matcher group。
- 保留已有的 `SessionStart`、`Stop`、`UserPromptSubmit` 和其他 Hook。
- `AGENTS.md` 已存在时，只增加子代理约束，不覆盖原有规则。
- `config.toml` 中已有 `[features]` 时，在原表内合并，不能重复创建同名 TOML 表。

## 三、创建目录

```bash
mkdir -p ~/.codex/agents
mkdir -p ~/.codex/hooks
```

## 四、创建自定义子代理

创建 `~/.codex/agents/luna-worker.toml`：

```toml
name = "luna_worker"
description = "Fast worker for clear, narrowly scoped, and repeatable tasks."
developer_instructions = """
Handle the assigned task strictly within its stated scope.
Work independently and use appropriate tools when needed.
Verify the result when practical.
Do not make unrelated changes.
Return a concise summary containing the result, relevant file paths, verification performed, and any important caveats.
"""
model = "gpt-5.6-luna"
model_reasoning_effort = "max"
```

说明：

- `name` 是 Codex 识别自定义 Agent 的依据。
- 文件名与 `name` 保持对应，便于维护。
- 模型和推理强度写在自定义 Agent 文件中，避免子代理继承主代理模型。

## 五、在全局 AGENTS.md 添加规则

在 `~/.codex/AGENTS.md` 的合适位置加入：

```markdown
## 子代理约束

- 任务适合分派时，优先使用 `luna_worker` 子代理。
- 所有子代理必须显式使用 `agent_type = "luna_worker"`。
- 禁止使用 `default`、`worker`、`explorer` 或其他自定义子代理。
- 调用 `spawn_agent` 时，`fork_turns` 必须使用 `"none"` 或正整数字符串，禁止使用 `"all"`。
- 禁止为子代理传入 `model`、`reasoning_effort` 或其他模型覆盖参数。
- 子代理模型和推理强度以 `luna-worker.toml` 为准。
- 如果 `luna_worker` 不可用，由主代理自行完成，不得换用其他子代理。
```

`AGENTS.md` 是行为约束，不是强制执行边界。真正的拦截由下一步 Hook 完成。

## 六、创建 PreToolUse 校验脚本

创建 `~/.codex/hooks/enforce_luna_worker.py`：

```python
#!/usr/bin/env python3

import json
import os
import sys
import tomllib
from pathlib import Path


CODEX_HOME = Path(
    os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
).expanduser()

AGENT_CONFIG = CODEX_HOME / "agents" / "luna-worker.toml"

EXPECTED_AGENT = {
    "name": "luna_worker",
    "model": "gpt-5.6-luna",
    "model_reasoning_effort": "max",
}

OVERRIDE_FIELDS = (
    "model",
    "reasoning_effort",
    "model_reasoning_effort",
    "thinking",
)


def deny(reason: str) -> None:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(output, ensure_ascii=False))


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        deny("Blocked subagent spawn: invalid PreToolUse input.")
        return

    if not isinstance(event, dict):
        deny("Blocked subagent spawn: invalid PreToolUse input.")
        return

    if event.get("hook_event_name") != "PreToolUse":
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
    bounded_fork = (
        isinstance(fork_turns, str)
        and 1 <= len(fork_turns) <= 9
        and fork_turns.isascii()
        and fork_turns.isdigit()
        and any(character != "0" for character in fork_turns)
    )

    if fork_turns != "none" and not bounded_fork:
        deny("luna_worker requires fork_turns=none or a positive integer.")
        return

    overridden = [
        field
        for field in OVERRIDE_FIELDS
        if tool_input.get(field) not in (None, "")
    ]

    if overridden:
        deny("luna_worker model and reasoning overrides are not allowed.")
        return

    try:
        with AGENT_CONFIG.open("rb") as config_file:
            agent_config = tomllib.load(config_file)
    except (OSError, tomllib.TOMLDecodeError):
        deny("luna_worker configuration is missing or invalid.")
        return

    if any(
        agent_config.get(key) != value
        for key, value in EXPECTED_AGENT.items()
    ):
        deny(
            "luna_worker configuration does not match "
            "the required Luna profile."
        )
        return


if __name__ == "__main__":
    try:
        main()
    except Exception:
        deny("Blocked subagent spawn: unexpected validation failure.")
```

该脚本采用 fail-closed：配置缺失、TOML 损坏、输入异常或参数不符合要求时，一律拒绝子代理启动。

脚本通过 Python 解释器调用，不要求设置可执行位。

## 七、注册 Hook

编辑 `~/.codex/hooks.json`。

如果没有其他 Hook，可以使用：

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "hooks": [
          {
            "command": "/ABSOLUTE/PATH/TO/python3 /Users/yourname/.codex/hooks/enforce_luna_worker.py",
            "statusMessage": "Enforcing luna_worker subagent",
            "timeout": 5,
            "type": "command"
          }
        ],
        "matcher": "^(Agent|spawn_agent)$"
      }
    ]
  }
}
```

必须替换：

```text
/ABSOLUTE/PATH/TO/python3
/Users/yourname
```

例如：

```json
"command": "/opt/homebrew/bin/python3 /Users/example/.codex/hooks/enforce_luna_worker.py"
```

如果已经存在 `hooks.json`，只把下面这个对象追加到现有 `hooks.PreToolUse` 数组：

```json
{
  "hooks": [
    {
      "command": "/ABSOLUTE/PATH/TO/python3 /Users/yourname/.codex/hooks/enforce_luna_worker.py",
      "statusMessage": "Enforcing luna_worker subagent",
      "timeout": 5,
      "type": "command"
    }
  ],
  "matcher": "^(Agent|spawn_agent)$"
}
```

不要覆盖其他 Hook。Codex 会加载并运行所有匹配的 Hook。

## 八、启用 Hooks

在 `~/.codex/config.toml` 中确认：

```toml
[features]
hooks = true
```

如果已有 `[features]`，只在原表中加入或更新 `hooks = true`。

新版 Codex 默认启用多代理。可以用下面的命令检查当前能力：

```bash
codex features list
```

不要为了强制 Luna 而修改主代理的：

```toml
model = "..."
model_reasoning_effort = "..."
```

主代理模型与子代理模型应保持独立。

## 九、验证配置文件

运行：

```bash
python3 -c '
import ast
import json
import pathlib
import tomllib

base = pathlib.Path.home() / ".codex"

agent = tomllib.loads((base / "agents/luna-worker.toml").read_text())
json.loads((base / "hooks.json").read_text())
ast.parse((base / "hooks/enforce_luna_worker.py").read_text())

assert agent["name"] == "luna_worker"
assert agent["model"] == "gpt-5.6-luna"
assert agent["model_reasoning_effort"] == "max"

print("LUNA_CONFIG_VALID")
'
```

如果使用自定义 `CODEX_HOME`，应在验证脚本中替换 `base`。

## 十、验证 Hook 协议

合法调用：

```bash
printf '%s\n' \
'{"hook_event_name":"PreToolUse","tool_name":"spawn_agent","tool_input":{"agent_type":"luna_worker","fork_turns":"4"}}' \
| python3 ~/.codex/hooks/enforce_luna_worker.py
```

预期结果：

- 退出码为 `0`。
- 标准输出为空。

错误代理调用：

```bash
printf '%s\n' \
'{"hook_event_name":"PreToolUse","tool_name":"spawn_agent","tool_input":{"agent_type":"worker","fork_turns":"4"}}' \
| python3 ~/.codex/hooks/enforce_luna_worker.py
```

预期输出包含：

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Only agent_type=luna_worker is allowed."
  }
}
```

还应验证以下情况全部返回 `deny`：

- `agent_type = "default"`
- `agent_type = "worker"`
- `agent_type = "explorer"`
- 缺少 `agent_type`
- 缺少 `fork_turns`
- `fork_turns = "all"`
- `fork_turns = "0"`
- 显式传入 `model`
- 显式传入 `reasoning_effort`
- `luna-worker.toml` 缺失或模型配置不匹配
- 输入不是有效 JSON

## 十一、审核并信任 Hook

非托管 command Hook 创建或变化后，Codex 会先跳过它，直到用户审核并信任当前定义。

启动新的 Codex 会话，输入：

```text
/hooks
```

逐项检查：

- Event：`PreToolUse`
- Matcher：`^(Agent|spawn_agent)$`
- Source：`~/.codex/hooks.json`
- Command：Python 和脚本绝对路径正确
- Timeout：`5`
- 没有陌生命令、管道或额外参数

确认后信任该 Hook。

验收状态应为：

```text
PreToolUse    Installed 1    Active 1
```

退出并重新启动 Codex，再执行一次 `/hooks`，确认仍然是 `Installed 1 / Active 1`。

不要在常规使用中通过以下参数绕过信任：

```text
--dangerously-bypass-hook-trust
```

如果修改了 Hook 定义或命令，Codex 会根据新的 hash 要求重新审核。

## 十二、真实子代理验收

在全新任务中输入：

```text
请使用 luna_worker 子代理完成以下任务：读取当前目录并列出一级文件。
等待子代理完成后，检查并汇总它的结果。
```

检查：

- 子代理类型是 `luna_worker`。
- 子代理模型是 `gpt-5.6-luna`。
- 推理强度是 `max`。
- 主代理模型没有被改成 Luna。
- `/hooks` 仍显示 `PreToolUse Active 1`。

## 十三、日常调用模板

```text
请使用 luna_worker 子代理完成以下任务：[填写任务]。
子代理必须严格遵守任务范围，不做无关修改。
等待子代理完成后，检查并汇总结果、相关文件路径、验证情况和注意事项。
```

并行任务：

```text
请把以下相互独立的任务分别交给多个 luna_worker 子代理并行完成。
每次调用必须显式使用 agent_type=luna_worker，并将 fork_turns 设置为正整数字符串。
等待所有子代理完成后，交叉检查并统一汇总。
```

## 十四、为什么不用 SubagentStart

`SubagentStart` 发生时，子代理已经开始启动。该 Hook 适合：

- 给子代理增加上下文
- 发出警告
- 记录审计信息

它不适合阻止子代理启动。`continue: false` 在 `SubagentStart` 中不会停止子代理。

必须使用 `PreToolUse`，并返回：

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Reason"
  }
}
```

## 十五、局限和安全边界

这套方案是可靠的客户端 guardrail，但不是不可绕过的系统安全边界：

- 不运行 Codex Hooks 的其他客户端不受保护。
- 某些专用工具路径可能不经过默认 Hook 链路。
- 能修改 Agent TOML、Hook 脚本或 `hooks.json` 的本地用户也能改变规则。
- 旧版 CLI 可能不支持自定义 Agent、`max` 或 `/hooks`。
- Hook 输出可能进入日志或模型上下文，不能输出 token、密码或配置全文。

个人环境通常使用 `~/.codex/hooks.json` 即可。

企业级强制应把 Hook 放入管理员托管的 `requirements.toml`，并通过 MDM 或其他设备管理方式分发脚本。只有当 Luna Hook 已经迁移到 managed configuration 后，才可以启用：

```toml
allow_managed_hooks_only = true
```

该设置会跳过用户、项目、会话和插件 Hook。如果在仍使用用户级 Luna Hook 时开启，会连同 Luna Hook 一起禁用。

## 完成检查表

- [ ] `~/.codex/agents/luna-worker.toml` 存在且 TOML 有效
- [ ] `name = "luna_worker"`
- [ ] `model = "gpt-5.6-luna"`
- [ ] `model_reasoning_effort = "max"`
- [ ] `~/.codex/AGENTS.md` 包含 Luna-only 子代理规则
- [ ] `~/.codex/hooks/enforce_luna_worker.py` 语法有效
- [ ] `~/.codex/hooks.json` 保留了原有 Hook
- [ ] `PreToolUse` matcher 覆盖 `Agent` 和 `spawn_agent`
- [ ] `hooks = true`
- [ ] 合法 Luna 调用无输出并继续
- [ ] 错误代理、错误 fork 和模型覆盖全部返回 `deny`
- [ ] `/hooks` 显示 `PreToolUse Installed 1 / Active 1`
- [ ] 重启后 Hook 仍为 Active
- [ ] 真实子代理显示 `gpt-5.6-luna / max`
- [ ] 主代理模型保持不变
