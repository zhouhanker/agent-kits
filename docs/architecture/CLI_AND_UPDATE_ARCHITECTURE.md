# kitcli CLI、来源准入与更新架构

> 状态：Accepted baseline，已进入分阶段实施
>
> 更新日期：2026-08-21
>
> 本文定义管理面、来源准入、安装作用域和更新协议。V1 实施进度见
> `../implementation/CLI_V1_IMPLEMENTATION_PLAN.md`。

## 1. 结论

`kitcli` 应提供一个跨客户端、跨平台的统一 CLI，但 CLI 不应成为
`clients/` 下的新客户端。这里的 `clients` 指 Codex、Claude Code 等被配置的
目标应用；CLI 是操作这些声明和目标应用的管理面。

现有六层内容模型可以保留，不需要推翻：

```text
内容面：catalog + clients + platforms + services + kits + profiles
管理面：CLI -> application use cases -> domain policy -> infrastructure adapters
```

内容面回答“安装什么、适配谁、支持什么平台、如何组合”；管理面回答“从哪里
取得、是否可信、安装到哪里、怎样预览、验证、更新和回滚”。两者是正交关系，
不是七个并列目录层。

## 2. 语言选择

推荐 V1 使用 Python，核心尽量依赖标准库：

| 方案 | 优点 | 主要成本 | 本项目结论 |
| --- | --- | --- | --- |
| Python | 与现有项目、Conda、schema/Markdown/JSON/TOML 处理一致；开发和测试成本最低 | 终端用户需要 Python 或封装后的运行环境 | V1 推荐 |
| Go | 交叉编译和单文件分发简单 | 需要维护第二套语言、包模型和实现 | 仅在未来需要极简 bootstrap 时评估 |
| Rust | 二进制小、类型和内存安全强 | 实现、跨平台打包和团队维护成本最高 | 当前不值得迁移 |
| Shell/PowerShell | 小任务启动快 | 无法形成一致的 macOS/Windows/Linux 行为 | 不作为核心实现 |

开发环境仍使用 Conda `agent-kits`。面向用户的分发按以下优先级设计：

1. 开发者和当前仓库：Conda 环境。
2. 普通用户：`pipx`、`uv tool` 或组织批准的 Python 工具安装方式，使 CLI 与
   业务项目环境隔离。
3. 无 Python 前置条件的设备：在 CLI 稳定后，为正式 Release 构建并签名
   macOS、Windows 和 Linux 独立制品。

当前 Conda 开发环境使用 Python 3.14；CLI 分发元数据已采用
`>=3.11,<3.15`，因为实现只使用 Python 3.11 起提供的标准库能力。3.11、3.12
和 3.13 的兼容性由多 OS CI 矩阵验证，本机会明确记录只验证了 Conda 3.14。

## 3. 管理面模块边界

建议未来 Python 包采用以下内部结构：

```text
src/agent_kits/
|-- cli/                 # 参数、交互、表格/JSON 输出和退出码
|-- application/         # inspect/import/plan/apply/update 等用例编排
|-- domain/              # manifest、lock、plan、receipt、policy 纯模型
`-- infrastructure/
    |-- sources/         # HTTPS、GitHub Release、本地文件和缓存
    |-- clients/         # Codex、Claude Code 等目标适配
    |-- platforms/       # macOS、Windows、Linux 路径/权限/进程适配
    |-- state/           # 锁、安装回执、备份和本地配置
    `-- packages/        # pipx/uv/Conda/独立制品的更新代理
```

仓库根目录的 `clients/`、`platforms/` 是声明和模板；Python 包内的
`infrastructure/clients/`、`infrastructure/platforms/` 是解释这些声明并访问
设备的代码。两者不能各自维护一份组件内容。

核心规划器不得散布 `if macos`、`if windows` 或绝对用户目录。平台适配器负责
路径、权限、原子替换和进程语义；客户端适配器负责配置格式、加载顺序和验收。
Ubuntu 属于 Linux 平台族，可以有发行版 capability，但不应复制一个完整 Ubuntu
实现。

## 4. 用户交互模型

建议命令面保持资源导向，并且所有写操作先产生可保存、可复核的 plan：

```text
kitcli doctor
kitcli catalog list
kitcli source inspect <URL-or-path>
kitcli source import <URL-or-path> --as bundle|document
kitcli plan --kit <id> --scope project|user --client <id>
kitcli apply --plan <plan-id>
kitcli verify [--receipt <id>]
kitcli rollback --receipt <id>
kitcli update check --target cli|repository|sources|environment
kitcli update plan --target <target>
kitcli update apply --plan <plan-id>
```

推荐使用显式来源参数：

```text
kitcli source inspect --file <path>
kitcli source inspect --url <https-url>
kitcli source import --file <path> --as document|bundle
kitcli source import --url <https-url> --as document|bundle
```

`source` 本身不执行动作；`inspect` 是静态检查，`import` 是 quarantine。不要设计
`source -file <path>` 这种省略阶段的命令，也不要让来源参数隐式触发安装。CLI
的用户入口固定为短命令 `kitcli`；发行包和 Python import 仍保持 `agent-kits`。

`update check` 永远只读。`update all` 即使未来提供，也只能汇总可用更新，不能把
CLI、仓库、外部来源和设备配置串成一次无人审查的写操作。

V1 对 CLI 自身提供官方隔离安装器的 `update`（默认只读）、`update --check` /
`update --yes`，只更新已写入
安装元数据的用户目录虚拟环境，并在下载后校验 Release `SHA256SUMS`。Conda、pipx
和 uv 安装仍由原包管理器更新；仓库和 external lock 的替换继续委托给各自的
Release 流程，设备变更使用单独的 `plan/apply/verify/rollback`。

### 安装作用域

- `project`：只修改当前项目内由 manifest 声明且由 kit 拥有的文件或字段。
- `user`：安装到当前用户的 Codex、Claude Code 等配置目录，也就是通常所说的
  “全局安装”，但不取得系统管理员权限。
- `managed/system`：未来只有存在明确组织适配器和管理员策略时才开放；不得把它
  作为通用 `--global` 的隐式含义。

CLI 自动检测平台，但目标客户端和 profile 必须可解释。任何兼容性降级、跳过项
或组织策略冲突都必须出现在 plan 中。

### 人与 Agent 的交互

- 人直接使用交互式 CLI，查看表格化 plan 并确认高风险步骤。
- Codex、Claude Code 或其他 Agent 使用稳定的 `--json --non-interactive` 输出、
  明确退出码和 plan 文件；Agent 可以解释 plan，但不能替用户批准写操作。
- 未来如提供 MCP server 或客户端 Plugin，只作为同一 application 层的薄入口，
  不复制 resolver、policy、transaction 或 platform adapter。
- 高风险 apply 需要独立的 plan ID/摘要确认，不能把“给出 URL”解释为批准安装。

项目交互状态建议分为：

```text
agent-kits.toml          # 可提交：项目选择的 profile、kit、client 和非敏感变量引用
agent-kits.lock          # 可提交：解析后的版本、来源、完整摘要和 schema 版本
.agent-kits/             # 本地忽略：plan、receipt、backup、cache 和设备探测结果
```

用户作用域的选择、回执、缓存和备份放入平台标准配置/状态目录，不写入仓库，也不
与 Codex/Claude 的登录态混合。

## 5. GitHub 和 Markdown 来源准入

给 CLI 一个 GitHub 链接或 Markdown 文档不等于授权执行其中的命令。来源先进入
隔离检查，再分为两类。

`source import` 的目标是生成当前 `agent-kits` 仓库可审查的 catalog/guide
候选；`plan/apply --scope project|user` 的目标是把已经准入并锁定的 kit 安装到
项目或用户环境。这两个动作不能合并成“下载后立即执行”。

完整操作规程见 `../guides/DOCUMENT_IMPORT_AND_PROMOTION.md`。临时原始材料进入
`llm-repo/raw/` 或 CLI quarantine；稳定说明进入 `docs/guides/`/`docs/sources/`；
可安装内容必须先提炼为 `catalog/` manifest，再由 kit/profile 组合。

### 5.1 可安装 bundle

可安装来源必须包含版本化 manifest，例如 `agent-kit.toml`，至少声明：

- 稳定 ID、版本、维护者和许可证。
- 支持的客户端、平台、CLI/schema 版本范围。
- 所有 payload 文件及 SHA-256。
- 安装目标、字段所有权、冲突和卸载规则。
- 所需命令、网络、权限和秘密名称，但不包含秘密值。
- 验证、回滚和人工验收要求。
- 来源 Release、完整 commit SHA、制品摘要和可选签名/provenance。

仓库 URL 默认解析到正式 GitHub Release；不能静默跟踪默认分支。完整 commit SHA
可以用于 `source-pinned + manual-only`，但不能冒充正式自动更新通道。

下载过程需要限制重定向、协议、域名、大小和文件类型，并检查 archive 路径穿越、
绝对路径、符号链接和摘要。检查失败的内容留在本地 quarantine，不进入 catalog，
也不能被 apply。

### 5.3 沙箱分级

应提供沙箱，但“沙箱”要分级定义：

1. **V1 静态沙箱**：当前 `inspect`、`import`、ZIP 检查、Markdown 解析、摘要、
   manifest 校验和隔离目录渲染；不启动 shell，不导入外部 Python，不运行 Hook。
2. **提炼沙箱**：未来在临时文件系统中生成 manifest 草案和 plan，限制网络、文件
   大小、路径和输出类型；只产生待审材料，不修改 catalog 或设备。
3. **执行沙箱**：只有明确的、版本化的 manifest 行为才可考虑执行。必须使用平台
   原生隔离/容器/低权限账户、无默认秘密、最小网络和超时；不能用 Python
   `subprocess` 加一层目录就宣称安全。跨 macOS、Windows、Linux 的一致执行沙箱
   不是 V1 能诚实保证的能力。

因此，外部 Markdown 验证成功后也不能直接“执行并提炼”。正确顺序仍是静态/提炼
沙箱 -> 人工审核 -> catalog/kit Release -> plan/apply。高风险执行要另立安全评审。

### 5.2 普通 Markdown 文档

类似 `docs/CODEX_LUNA_WORKER_SETUP.md` 的 Markdown 首先是“不可信说明文档”，
不是安装包：

1. 保存来源 URL、抓取时间和内容摘要。
2. 解析标题、链接和代码块，但绝不执行代码块。
3. 生成待审的 guide/source 记录，或生成 bundle manifest 草案。
4. 人工把可安装内容拆为 catalog 规范源、客户端映射、kit 和验收规则。
5. 通过 schema、敏感信息、隔离主目录和真实客户端验证后，随新的仓库 Release
   发布。

因此 CLI 可以“导入文档并生成安装提案”，但不应提供“直接执行任意 Markdown”
能力。Luna 文档在当前项目中的正确迁移也是先拆分规范源与指南，而不是让 CLI
逐行执行文档。

## 6. 四类更新必须分离

| 更新目标 | 来源 | 写入对象 | 推荐执行者 |
| --- | --- | --- | --- |
| CLI 自身 | `agent-kits` 正式 Release/包索引 | CLI 安装环境 | pipx/uv/Conda/平台安装器 |
| 仓库内容 | 已审查的 `agent-kits` Release | catalog、schema、docs 快照 | CLI 下载并验证，或开发者明确操作 Git |
| 外部来源 | 各 integration 的锁定 Release | source lock 和本地缓存 | CLI 仅在审核后更新锁 |
| 设备环境 | 已解析的仓库版本和 profile | 项目/用户客户端配置 | CLI plan/apply/verify/rollback |

另有“上游文档探测”，它只产生 Issue、报告或待审 PR，不直接更新以上四类对象。

CLI 不应覆盖正在运行的自身可执行文件，尤其不能假设 Windows 允许这样做。CLI
只检查并生成更新计划，实际替换委托给安装它的 package manager 或独立 launcher。
开发仓库也不得把 `git pull` 隐藏在普通更新命令后；Git 模式必须显式选择，并
遵守本项目逐条审查 Git 命令和敏感文件的规则。

## 7. 更新事务和本地状态

每次 apply 至少需要生成不可变回执，记录：

- CLI、仓库、schema、kit 和 source lock 版本。
- 平台、客户端、profile 和安装作用域。
- 获得所有权的文件/字段及写入前摘要。
- 备份位置、验证结果、时间和 plan ID。

写入应使用进程锁、临时文件、原子替换和结构化合并。失败时只回滚当前事务拥有
的变更，不覆盖其他工具或用户随后做出的修改。缓存、回执、备份和本地策略由
平台适配器解析到 XDG/macOS/Windows 合适目录，不能写死用户路径。

## 8. 版本和兼容契约

至少独立版本化以下对象：

- CLI 版本。
- repository/catalog release 版本。
- manifest/schema 版本。
- kit 版本。
- 外部 integration lock 版本。
- client/platform compatibility 证据版本。

CLI 必须拒绝自己不理解的更高 schema major 版本。更新顺序是先证明新 CLI 能读取
新旧 schema，再更新仓库内容，最后对设备生成 plan。降级和 rollback 也必须遵守
schema 可读范围，不能只替换文件版本号。

V1 建议只提供 `stable` channel；未来的 `preview` channel 必须显式加入，且不能
把预览组件自动传播到用户作用域。

## 9. 推荐的 V1 范围

1. Python CLI 骨架和稳定退出码/JSON 输出契约。
2. `doctor`、`source inspect`、schema validation 和只读 catalog 查询。
3. `plan` 及安装回执模型，在隔离主目录中验证。
4. `apply/verify/rollback` 先支持一个低风险 kit，再支持 Luna。
5. `source import --as document` 只生成隔离的待审材料。
6. `update check` 分别检查 CLI、仓库、外部来源和设备漂移。
7. GitHub Actions 负责验证和变化提醒，不负责设备端写入。

V1 不包含任意 Markdown 命令执行、默认分支自动安装、后台无人值守 apply、系统级
安装、自动 Git 操作或自动合并高风险组件。

## 10. 需要确认的决策

1. 接受 CLI 是独立管理面，而不是第七个内容层或 `clients/cli`。
2. 接受 Python V1，并在实现前评估 Python 3.11+ 的兼容范围。
3. 接受 `project`、`user` 和未来 `managed/system` 的作用域语义。
4. 接受 Markdown 只能生成待审提案，不能直接成为可执行安装器。
5. 接受 CLI、仓库、外部来源和设备环境四类更新相互独立。
6. 接受正式 Release + digest 为默认分发渠道，不跟踪默认分支。
