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

当前 `v0.1.4` 官方安装器和自更新流程已在 macOS 验证。Windows 安装器有 CI 覆盖，
但尚未在真实 Windows 设备验证；外部 Apple 网关仍需不可变 Release、制品摘要、许可证
和 CI 证据后才能进入无人值守安装。
