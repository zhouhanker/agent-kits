# agent-kits

- [English README](README.md)
- [中文 README](README_zh.md)

`agent-kits` 是一个面向 Agent 开发环境的、可版本化且可审计的配置与分发仓库。
它管理 Codex、Claude Code 以及未来客户端所需的 agents、hooks、MCP、skills、
持久化指令、平台适配、kits 和 profiles，同时把外部来源、安装计划和回滚证据分开管理。

当前 V1 使用 Python 标准库实现跨平台 CLI。命令名称是短命令 `kitcli`；已安装的
`agent-kits` 仍作为兼容别名保留。包名、Python import 名称和 Conda 环境名称仍为
`agent-kits`，这三者不随 CLI 命令名改变。

## 状态

V1 已实现并测试以下能力：来源静态检查、Markdown/ZIP quarantine 导入、catalog
查询、安装 `plan/apply/verify/rollback` 事务，以及只读的更新检查。真实用户全局安装、
签名独立制品、Apple 网关自动安装和非 macOS 真机验证仍需满足文档中的发布与验证门禁。

## 环境与安装

项目开发环境使用 Conda `agent-kits`：

```bash
conda env create -f environment_cross_platform.yml
conda activate agent-kits
python -m pip install --no-build-isolation --no-deps -e .
```

可编辑安装会把 `kitcli` 放在当前 Conda 环境的 `bin` 目录中。当前终端如果没有
激活环境，直接在项目目录执行 `kitcli` 会找不到命令；请先激活，或显式使用：

```bash
conda activate agent-kits
kitcli doctor
# 不激活环境时：
conda run -n agent-kits kitcli doctor
```

需要不依赖 Conda、在终端全局调用时，macOS/Linux 可安装官方 Release 的隔离用户版：

```bash
curl -fsSL https://github.com/zhouhanker/agent-kits/releases/latest/download/install.sh -o /tmp/kitcli-install.sh
less /tmp/kitcli-install.sh
sh /tmp/kitcli-install.sh
```

安装器要求 Python 3.11+，把虚拟环境放到 `~/.local/share/kitcli`，并把入口链接到
`~/.local/bin/kitcli`。Windows 请在 PowerShell 中下载并检查 `install.ps1` 后执行，
它会安装到 `%LOCALAPPDATA%\\Programs\\kitcli` 并加入用户 PATH。GitHub Release 必须
同时提供带真实版本的 wheel 和 `SHA256SUMS`，缺少任一项时安装器会失败，不会安装未校验的包。

已有环境可使用：

```bash
conda env update -n agent-kits -f environment_cross_platform.yml
```

## CLI 快速开始

只读检查和列出已审核 kit：

```bash
kitcli doctor
kitcli catalog list
```

检查或隔离本地 Markdown：

```bash
kitcli source inspect --file ./docs/CODEX_LUNA_WORKER_SETUP.md
kitcli source import --file ./docs/CODEX_LUNA_WORKER_SETUP.md --as document
```

检查远程来源时优先使用 HTTPS 的固定 commit Raw URL、GitHub Release asset 或带
manifest 与摘要的正式 bundle：

```bash
kitcli source inspect --url https://example.org/guide.md
kitcli source import --url https://example.org/guide.md --as document
```

来源导入只会写入 quarantine，不会执行 Markdown 代码块、Shell、Python、Hook 或安装命令。
完成审查和人工提炼后，使用已登记的 kit 生成并执行计划：

```bash
kitcli plan --kit base --scope project --client codex
kitcli apply --plan <plan-id> --scope project --yes
kitcli verify --receipt <receipt-id> --scope project
kitcli rollback --receipt <receipt-id> --scope project --yes
```

Agent 自动化应使用稳定 JSON 输出，并保留人工批准边界：

```bash
kitcli --json --non-interactive catalog list
```

## CLI 更新

官方安装器会记录固定的 HTTPS Release 制品地址和校验文件。先检查远程版本而不写入：

```bash
kitcli update --check
```

直接执行 `kitcli update` 也默认只读检查。

确认后更新隔离环境：

```bash
kitcli update --yes
```

通过 Conda、pipx 或 uv 安装的版本仍由对应包管理器负责更新；更新仓库内容和来源锁定
则使用只读的 `kitcli update check`，不会把设备配置、CLI 和外部来源合并成一次无人审查的写操作。

## 来源到可安装 kit

外部链接或文档不是安装授权。推荐链路是：

```text
URL/文件 -> source inspect -> source import/quarantine
        -> 人工提炼与 schema/安全审查
        -> catalog manifest -> kit/profile
        -> plan -> 人工确认 -> apply -> verify/rollback
```

临时原始资料放在 `llm-repo/raw/` 或 CLI quarantine；审核后的说明放在
`docs/guides/` 和 `docs/sources/`；可安装内容放在 `catalog/`，由
`catalog/kits/<id>/manifest.toml` 描述。`llm-repo/` 是 Agent 工作区，不应上传。

## 目录

```text
src/agent_kits/   Python 包和 kitcli 管理面
tests/            自动化测试
catalog/          可审核的 kit、payload 和外部锁
profiles/         非敏感的角色/设备选择
schemas/          版本化声明 schema
docs/             架构、操作和来源文档
llm-repo/         Agent 本地证据与工作日志（不提交）
```

架构、来源提炼、更新和安全边界见：

- [CLI、来源准入与更新架构](docs/architecture/CLI_AND_UPDATE_ARCHITECTURE.md)
- [文档导入、提炼与复用指南](docs/guides/DOCUMENT_IMPORT_AND_PROMOTION.md)
- [CLI V1 实施计划](docs/implementation/CLI_V1_IMPLEMENTATION_PLAN.md)
- [架构评审](docs/architecture/ARCHITECTURE_REVIEW.md)

项目发行包和 Python import 继续使用 `agent-kits`；只有用户交互命令采用更短的
`kitcli`。不执行 Git 操作，不把 GitHub 仓库首页当作可安装 bundle，也不从外部
Markdown 自动执行命令。
