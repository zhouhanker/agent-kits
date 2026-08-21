# 文档导入、提炼与复用指南

> 状态：V1 static procedure plus V2 Agent-driven validation
>
> 更新日期：2026-08-21
>
> 本指南说明如何把 GitHub 链接或 Markdown 指南导入 `agent-kits`，再提炼为
> 可审核、可复用、可安装的 kit。导入文档永远不会直接执行其中的命令。

V2 动态验证需要本机 Codex CLI 或 Claude Code，以及运行中的 Docker daemon。本机
Agent 只负责语义分类和客户端验收；Docker 才负责受限执行。没有可用 sandbox 时，
动态 intake 必须失败，不得降级为“已经验证”。具体边界见
[`AGENT_VALIDATION_AND_COMPONENT_LIFECYCLE.md`](../architecture/AGENT_VALIDATION_AND_COMPONENT_LIFECYCLE.md)。

## 1. 先区分四种东西

| 内容 | 推荐位置 | 是否提交 | 是否可直接安装 |
| --- | --- | ---: | ---: |
| 原始 URL、临时下载和 Agent 操作记录 | `llm-repo/raw/` 或 CLI quarantine | 否 | 否 |
| 已审核的说明文档和来源记录 | `docs/guides/`、`docs/sources/` | 是 | 否 |
| 可安装规范源和 payload | `catalog/` | 是 | 仅通过 manifest/plan |
| V1 kit manifest 和设备选择 | `catalog/kits/`、`profiles/` | 是 | 由 CLI plan/apply |
| 后续用户组合层 | `kits/` | 是 | 由 CLI plan/apply |

当前仓库中的 `docs/CODEX_LUNA_WORKER_SETUP.md` 仍是完整指南。它可以作为提炼
输入和人工参考，但不能被 CLI 当作脚本、Hook 或完整配置文件直接执行。

## 2. 推荐操作流程

### 2.1 导入不可信来源

在 `agent-kits` 仓库根目录执行：

```bash
conda activate agent-kits

kitcli source inspect --file ./docs/CODEX_LUNA_WORKER_SETUP.md
kitcli source inspect --url https://example.org/guide.md
kitcli source import --file ./docs/CODEX_LUNA_WORKER_SETUP.md --as document
kitcli source import --url https://example.org/guide.md --as document
```

`inspect` 只读取大小、类型和 SHA-256。`import` 把内容写入用户状态目录的
quarantine，并生成 `metadata.json`；它不会写 `catalog/`、`docs/`、Codex 或
Claude 配置，也不会执行 Markdown 代码块。

`--file` 和 `--url` 必须二选一。旧的单个位置参数仍兼容，但新文档应使用显式
参数，以便 Agent、日志和审计清楚记录来源类型。GitHub HTML 页面不应作为稳定
来源；优先使用固定 commit 的 Raw URL、Release asset 或正式 bundle URL。

如果原始材料只存在于本地，并且需要 Agent 复盘，可以额外复制到
`llm-repo/raw/incoming/<date>/`。`llm-repo/` 永远不进入 GitHub Release。

### 2.1.1 使用本机 Agent 的动态 intake

当用户希望验证“这个来源是否可以安装并正常工作”时，使用简写 intake 命令：

```bash
kitcli agents list
kitcli agents check --agent codex
kitcli source -file ./docs/CODEX_LUNA_WORKER_SETUP.md --agent codex --scope user
kitcli source -url https://example.org/component.md --agent auto --scope user
```

`agents list` 仅发现可执行文件，绝不调用模型。`agents check` 使用固定的、非安装测试
材料确认一次真实的结构化模型调用，因此可能消耗本机 Agent 的额度；它不下载来源、不会
进入 Docker，也不会写入客户端配置。完整 intake 仍会在 Docker 前置检查成功后才把真实
来源交给本机 Agent。

若 Agent 可执行普通文本调用、但其认证或提供方拒绝结构化 JSON 调用，仍视为动态 intake
不可用。此时先修复对应 Codex/Claude Code 的登录、订阅、额度、版本或提供方策略；不能将
问题误判为来源、MCP、Skill 或 Docker sandbox 失败。

该命令顺序固定为：静态 gate -> Docker sandbox 前置检查 -> 本机 Agent 受限 JSON
分析 -> 已审核组件的无网络 sandbox 验证 -> 本地 receipt -> `y/N` 安装确认。
`--non-interactive` 时，只有显式 `--yes` 才会安装。Agent 输出、Markdown 内容和
沙箱成功退出都不能单独授权全局写入。未确认时 receipt 会保留，命令返回
`not_installed`，不会把正常拒绝视为安装失败。

当前已实现的动态组件是 `luna-worker`，其来源必须精确匹配
`docs/CODEX_LUNA_WORKER_SETUP.md` 的 SHA-256。MCP、Skill 和未知链接可以做静态
记录，但在拥有受审 manifest、有限验证配方和 Docker receipt 前不能安装。

需要把来源整理为项目内候选而不安装时，使用：

```bash
kitcli component create -file ./docs/CODEX_LUNA_WORKER_SETUP.md --agent codex --id luna-worker
```

候选写入 `.agent-kits/candidates/`，不会修改 Codex 或 Claude 配置。它是
`kitcli apply <任意文档>` 的安全替代：现有 `apply` 只接受不可变 plan ID，不能也不应
执行文档中的命令。

### 2.2 人工提炼事实

从 quarantine 内容提炼时，逐项记录：

- 文档的来源 URL、提交/版本、抓取日期和摘要。
- 适用客户端：Codex、Claude Code 或其他客户端。
- 适用平台：macOS、Windows、Linux/Ubuntu。
- 输入文件、输出文件、字段所有权和合并策略。
- 命令、权限、网络、秘密名称和信任要求；不记录秘密值。
- 安装前检查、验证、回滚和不支持的情况。
- 哪些结论只是文档描述，哪些已经有真实客户端证据。

代码块只能作为待审参考。需要执行的命令必须由维护者重新表达为明确的、可审查
的 manifest 行为，不能从 Markdown 中复制后自动运行。

### 2.3 生成可复用规范源

将稳定内容拆分到唯一来源：

```text
catalog/agents/<client>/<id>/       # Agent 定义
catalog/hooks/<client>/<id>/        # Hook 定义和资源
catalog/skills/<client-or-common>/<id>/
catalog/instructions/<client-or-common>/<id>/
catalog/mcp/<client-or-common>/<id>/
```

每个可安装目录应有不含秘密的 payload 和 manifest。manifest 必须声明 schema
版本、稳定 ID、版本、平台/客户端、目标路径、字段所有权、冲突策略、摘要、验证
和回滚边界。规范源不能把整份 `~/.codex/`、`~/.claude/` 或用户主目录快照提交
进去。

### 2.4 创建 kit 和 profile

kit 只组合规范源，不复制 payload：

```text
catalog/kits/luna-worker/manifest.toml  # V1 当前实际扫描位置
profiles/team-base/profile.toml
profiles/personal-macos/profile.toml
```

Profile 只选择 kit 和非敏感变量引用。设备差异、环境变量值、Keychain/Credential
Manager 内容和登录态留在设备私有状态。

### 2.5 审核后安装

```bash
kitcli catalog list
kitcli plan --kit luna-worker --scope project --client codex
kitcli apply --plan <plan-id> --scope project --yes
kitcli verify --receipt <receipt-id> --scope project
```

当前 `luna-worker` 已登记为 macOS/Codex 用户组件。先对与当前指南摘要匹配的来源完成
动态 intake，再执行：

```bash
kitcli install luna-worker --scope user
```

V1 的 `user` 是当前用户配置目录，不是系统管理员安装。高风险 Hook、MCP、外部命令和
真实全局文件应先在隔离目录验证，再由用户明确批准。

## 3. Luna 文档如何提炼

对 `docs/CODEX_LUNA_WORKER_SETUP.md`，不要把整篇文档变成一个大 payload。当前拆成：

```text
catalog/kits/luna-worker/payloads/          # Agent、Hook、Hook JSON、features 和指令
catalog/kits/luna-worker/manifest.toml      # 五个目标路径、摘要和合并策略
```

提炼后的 kit 需要分别声明：Codex 最低版本、`luna_worker` 参数约束、Hook matcher
和输入输出、信任步骤、备份/合并规则、失败时的 deny 或 rollback 行为。Docker receipt
证明渲染后的配置与 Hook 输入输出；真实 Codex `/hooks` 信任和子代理加载验收仍必须由
用户在安装后完成。

## 4. 给其他人复用

别人不应复制一份私有主目录或直接运行你的 Markdown。可复用交付物应是：

1. 已审核的 `catalog` payload 和 manifest。
2. 一个引用这些规范源的 kit。
3. 一个不含秘密的 profile 示例。
4. 安装、验证、回滚和兼容矩阵文档。
5. `agent-kits` 正式 Release 中的版本和摘要。

使用者先获取已审查的仓库 Release，再执行 `agents list`、`doctor`、`catalog list` 和
动态 source intake。只有当前来源与组件摘要、sandbox receipt、目标作用域和风险都确认后，
才执行 `kitcli install <component>` 或通过 source intake 回答 `y`。不同平台只使用
兼容的 target；不兼容项必须在 plan 中明确显示，不能静默跳过。

## 5. 文档更新与自更新

文档更新分为三个阶段：

```text
上游 URL/Release
    -> inspect/import/quarantine
    -> 人工提炼 + schema/安全/隔离验证
    -> catalog/kit/docs PR 或 Release
    -> 使用者 update check + plan + apply
```

V1 的 `update check` 仍只读；官方隔离安装器另外提供默认只读的 `kitcli update`、
显式的 `kitcli update --check`
和 `kitcli update --yes`，仅替换安装器元数据指向的 CLI 虚拟环境。它不会自动替换
仓库文件、source lock 或设备配置。低风险的来源摘要/链接变化可以由 CI 生成待审
PR；Hook、MCP、Agent、权限、命令、目标路径和外部服务变化必须人工审核。

## 6. 验收清单

- [ ] 原始来源已保存 URL、版本/提交、抓取日期和 SHA-256。
- [ ] Markdown 代码块没有被自动执行。
- [ ] 稳定内容已经从指南中提炼成 catalog 唯一来源。
- [ ] manifest 声明平台、客户端、目标路径、摘要、风险和回滚。
- [ ] kit 只引用规范源，profile 不包含秘密。
- [ ] 隔离 project/user 目录完成 plan、apply、verify、rollback。
- [ ] 真实客户端加载证据与版本归属已记录。
- [ ] Release、文档和锁定摘要相互一致。

未通过任一项时，材料停留在 quarantine 或 `review_required`，不能进入自动安装
路径。
