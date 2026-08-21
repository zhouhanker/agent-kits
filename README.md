# agent-kits

- [中文 README](README.md)
- [English README](README_en.md)

`agent-kits` 是一个可版本化、可审计的 Agent 开发环境配置与分发仓库。用户命令是
`kitcli`；`agent-kits` 保留为兼容命令、发行包名、Python import 名称和 Conda 环境名。

## 安装 kitcli

`kitcli` 默认安装 GitHub 上最新的正式 Release。安装器要求 Python 3.11+，下载 wheel
后会校验 Release 中的 `SHA256SUMS`，并安装到独立的用户目录，不会修改系统 Python。

### macOS / Linux

```bash
curl -fsSL https://github.com/zhouhanker/agent-kits/releases/latest/download/install.sh | sh
```

安装完成后执行：

```bash
kitcli doctor
```

安装器会把入口放在 `~/.local/bin/kitcli`。若当前 shell 找不到命令，请将
`~/.local/bin` 加入 `PATH` 后重新打开终端。

### Windows PowerShell

在 PowerShell 中执行：

```powershell
irm https://github.com/zhouhanker/agent-kits/releases/latest/download/install.ps1 | iex
```

安装器会将 `kitcli` 放到 `%LOCALAPPDATA%\Programs\kitcli` 并加入用户 `PATH`。
请重新打开 PowerShell，再执行：

```powershell
kitcli doctor
```

一键命令适用于信任本项目正式 Release 的场景。需要先审查安装脚本时，下载 Release
中的 `install.sh` 或 `install.ps1`，审查后再执行；不要将外部 Markdown 中的命令直接
作为安装内容执行。

## 快速开始

```bash
kitcli doctor
kitcli catalog list
```

## 使用本机 Agent 验证来源

`kitcli` 的动态安装验证要求本机已安装并登录 Codex CLI 或 Claude Code，并要求 Docker
daemon 正在运行。模型由本机 Agent 自己选择和计费；`kitcli` 不提供模型、不保存 token，
也不会执行来源 Markdown 中的命令。

Claude Code 默认兼容订阅登录；需要显式使用 `ANTHROPIC_API_KEY` 的无用户配置模式时，设置
`AGENT_KITS_CLAUDE_CODE_MODE=api-key`。也可设置为 `subscription` 强制使用订阅登录，或保留
默认 `auto` 自动选择。两种模式均禁用模型工具、MCP 配置和会话持久化。

`kitcli agents check` 若失败会保留 Agent 返回的可操作诊断并脱敏 API-key 形式的内容。
认证、订阅、额度或第三方 Agent 提供方拒绝请求时，必须先修复该 Agent；`kitcli` 不会尝试
修改登录态或替换凭据。

还必须设置一个经过审查、带 SHA-256 digest 的验证镜像。镜像需要提供
`/usr/local/bin/python`，例如由团队发布的 Python 3.11 验证镜像：

```bash
export AGENT_KITS_SANDBOX_IMAGE='registry.example/kitcli-python@sha256:<64-hex-digest>'
```

先检查前置条件：

```bash
kitcli agents list
```

`agents list` 只检查命令是否可在 `PATH` 中找到，不会触发登录或模型调用。需要在导入
来源前确认账户、模型访问和结构化输出真正可用时，再显式执行下列命令；它会消耗当前
Codex 或 Claude Code 账户的一次受限模型调用，但不接收外部来源、不使用 Docker，也不
安装或修改任何客户端配置：

```bash
kitcli agents check --agent codex
kitcli agents check --agent claude-code
```

对本地文档或 HTTPS 链接进行完整 intake。该命令先做静态检查，再用本机 Agent 生成受限
JSON 分类，在无网络、无主目录挂载的 Docker 容器中验证已审核组件；验证成功后才询问是否
安装到所选 scope：

```bash
kitcli source -file ./docs/CODEX_LUNA_WORKER_SETUP.md --agent codex --scope user
kitcli source -url https://example.com/component.md --agent auto --scope user
```

非交互自动化必须显式确认：

```bash
kitcli --non-interactive source -file ./docs/CODEX_LUNA_WORKER_SETUP.md --agent codex --scope user --yes
```

未传 `--yes` 的自动化，以及交互提示中回答 `n`，都会保留验证 receipt 并返回
`not_installed`；不会把“未确认”报告成安装失败，也不会修改全局客户端配置。

Docker 未启动、镜像未固定 digest、没有本机 Agent、来源没有可识别的受审组件，或动态验证
失败时，命令会停止，不会调用模型执行来源命令，也不会安装任何内容。Docker 前置检查
发生在 intake 的模型调用之前；只想记录来源而不调用模型时，继续使用 `kitcli source
inspect` 与 `kitcli source import`。

需要把来源提炼成项目内可审核候选、但不安装到本机客户端时，使用：

```bash
kitcli component create -file ./docs/CODEX_LUNA_WORKER_SETUP.md --agent codex --id luna-worker
```

它在 `.agent-kits/candidates/` 写入来源摘要、Agent 分类和 sandbox receipt。未知 MCP
或 Skill 只会生成 `review_required` 候选，必须补齐受审 manifest 与有限验证配方后才能
进入 `kitcli install`；这就是安全替代“`kitcli apply <任意文档>`”的原因。

检查或隔离外部文档时，`kitcli` 只做静态检查和 quarantine 导入，不执行 Markdown
代码块、Shell、Python、Hook 或安装命令：

```bash
kitcli source inspect --file ./docs/CODEX_LUNA_WORKER_SETUP.md
kitcli source import --file ./docs/CODEX_LUNA_WORKER_SETUP.md --as document
```

经过人工审查和提炼后，使用已登记的 kit 生成计划；写入操作必须显式确认：

```bash
kitcli plan --kit base --scope project --client codex
kitcli apply --plan <plan-id> --scope project --yes
kitcli verify --receipt <receipt-id> --scope project
kitcli rollback --receipt <receipt-id> --scope project --yes
```

已通过当前 sandbox receipt 的可复用组件可以在其他设备安装。当前第一个组件是
`luna-worker`：

```bash
kitcli install luna-worker --scope user
```

`CODEX_LUNA_WORKER_SETUP` 也可作为兼容别名。Luna 仅支持 macOS 的 Codex 用户 scope，
安装内容包括 agent TOML、fail-closed Hook、Hook 注册、features 开关和受管理指令区块；
不会覆盖其他 Hook 或既有指令。

Agent 自动化可使用稳定 JSON 输出：

```bash
kitcli --json --non-interactive catalog list
```

## 更新 kitcli

先检查最新 Release，不写入本地环境：

```bash
kitcli update --check
```

确认后更新通过官方安装器创建的隔离环境：

```bash
kitcli update --yes
```

通过 Conda、pipx 或 uv 安装的版本仍由对应包管理器更新。CLI、仓库内容、外部来源锁和
设备配置使用独立的检查与变更事务，不会合并成一次无人审查的写入操作。

## 开发环境

项目开发使用 Conda 环境 `agent-kits`：

```bash
conda env create -f environment_cross_platform.yml
conda activate agent-kits
python -m pip install --no-build-isolation --no-deps -e .
kitcli doctor
```

未激活 Conda 时可以使用：

```bash
conda run -n agent-kits kitcli doctor
```

## 架构与安全边界

外部链接或文档不是安装授权。推荐链路如下：

```text
URL/文件 -> source inspect -> source import/quarantine
        -> 人工提炼与 schema/安全审查
        -> catalog manifest -> kit/profile
        -> plan -> 人工确认 -> apply -> verify/rollback
```

`llm-repo/` 是 Agent 本地证据与工作日志，不应上传。完整架构与操作说明：

- [CLI、来源准入与更新架构](docs/architecture/CLI_AND_UPDATE_ARCHITECTURE.md)
- [文档导入、提炼与复用指南](docs/guides/DOCUMENT_IMPORT_AND_PROMOTION.md)
- [CLI V1 实施计划](docs/implementation/CLI_V1_IMPLEMENTATION_PLAN.md)
- [架构评审](docs/architecture/ARCHITECTURE_REVIEW.md)
- [Agent 验证与组件生命周期](docs/architecture/AGENT_VALIDATION_AND_COMPONENT_LIFECYCLE.md)

当前 `v0.1.4` 官方安装器和自更新流程已在 macOS 验证。Windows 安装器有 CI 覆盖，
但尚未在真实 Windows 设备验证；外部 Apple 网关仍需不可变 Release、制品摘要、许可证
和 CI 证据后才能进入无人值守安装。
