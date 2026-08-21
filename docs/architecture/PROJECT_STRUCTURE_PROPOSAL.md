# agent-kits 项目结构提案

> 状态：Accepted baseline，已进入分阶段实施
>
> 更新日期：2026-08-21
>
> 本文只定义目标结构和边界，不代表对应目录或安装能力已经实现。

## 1. 项目定位

`agent-kits` 应定位为可审计的 Agent 开发环境配置仓库，而不是单一 Python
应用。它需要同时解决四类问题：

1. 为 Codex、Claude Code 以及后续客户端分发子代理、Hook、MCP、Skill 和
   持久指令。
2. 在个人电脑、工作电脑和组内成员设备之间复用相同的受控配置。
3. 区分通用能力、客户端差异、操作系统差异和设备私有信息。
4. 对安装、升级、冲突、来源变化和回滚提供可验证记录。

因此，仓库的核心产物应是“声明式组件 + 组合配置档 + 客户端/平台适配”，
Python 包只是未来实现验证器和安装器的一种载体，不应决定仓库的信息架构。

### 仓库身份

- GitHub HTTPS：<https://github.com/zhouhanker/agent-kits.git>
- GitHub SSH：`git@github.com:zhouhanker/agent-kits.git`

这两个地址是未来发布和协作目标。本轮未添加或修改 Git remote，也未执行任何
Git 命令。后续上传仍需逐条审查 Git 命令、暂存文件和敏感信息，并排除
`llm-repo/`。

## 2. 设计原则

### 2.1 仓库是期望状态，不是主目录镜像

不得把 `~/.codex/`、`~/.claude/` 整体复制进仓库。客户端目录包含登录状态、
历史、缓存、信任记录、OAuth 数据和其他设备状态。仓库只保存主动维护的配置
源文件和不含秘密的模板。

### 2.2 内容与安装位置解耦

同一份 Skill 或团队规则可能被多个客户端复用。源内容只维护一份，客户端
适配层负责把它转换或安装到 Codex、Claude Code 所需的位置，避免复制后漂移。

### 2.3 客户端与平台是两个不同维度

`codex`、`claude-code` 是客户端维度；`macos`、`windows`、`linux` 是平台
维度。不能把 macOS 逻辑直接放在 `clients/codex/`，否则未来 Claude Code
复用相同的 Apple 通知能力时会产生重复实现。

### 2.4 配置档只组合能力

个人 Mac、工作 Mac、工作 Windows 等差异应由 profile 选择组件，而不是复制
完整配置树。Profile 只记录启用项和非敏感参数引用。

### 2.5 默认先计划，再修改全局环境

未来安装流程应支持 `doctor -> plan -> apply -> verify -> rollback`。默认输出
变更计划，不直接覆盖全局文件；合并 JSON/TOML 时保留未知字段和其他工具的
配置。

### 2.6 自动发现，人工批准

依赖和官方文档变化可以自动扫描，但 Hook、MCP、Skill、子代理和全局配置不应
在无人审查时自动写入设备。自动化应提交 Issue 或 PR，由维护者确认后发布。

## 3. 目标目录结构

```text
agent-kits/
|-- AGENTS.md
|-- CLAUDE.md                       # 未来：Claude Code 项目级约束
|-- README.md
|-- pyproject.toml
|-- environment_cross_platform.yml
|
|-- catalog/                        # 可安装单元的唯一来源
|   |-- agents/                     # 子代理定义
|   |   |-- codex/
|   |   `-- claude-code/
|   |-- hooks/                      # 生命周期 Hook 定义及其资源
|   |   |-- common/
|   |   |-- codex/
|   |   `-- claude-code/
|   |-- mcp/                        # MCP 服务声明，不保存凭据
|   |   |-- common/
|   |   |-- codex/
|   |   `-- claude-code/
|   |-- skills/                     # 尽量维护客户端中立的 Skill 源
|   |   |-- common/
|   |   |-- codex/
|   |   `-- claude-code/
|   |-- integrations/               # 外部产品的版本化集成声明
|   |   `-- external/
|   |       `-- multiple-devices-ai-gateway/
|   `-- instructions/               # AGENTS.md、CLAUDE.md、rules 等源片段
|       |-- common/
|       |-- codex/
|       `-- claude-code/
|
|-- clients/                        # 客户端格式、目标路径、合并和验证规则
|   |-- codex/
|   |   |-- README.md
|   |   |-- mappings/
|   |   `-- templates/
|   |-- claude-code/
|   |   |-- README.md
|   |   |-- mappings/
|   |   `-- templates/
|   `-- future-client/
|
|-- platforms/                      # 操作系统专属能力
|   |-- common/
|   |-- macos/                       # 平台检测与 agent-kits 自有适配
|   |-- windows/
|   `-- linux/
|
|-- services/                       # agent-kits 自有的远程服务（按需创建）
|
|-- kits/                           # 面向用户的功能组合
|   |-- base/
|   |-- luna-worker/
|   `-- apple-approval-bridge/
|
|-- profiles/                       # 设备或角色组合，不包含秘密
|   |-- team-base/
|   |-- personal-macos/
|   |-- work-macos/
|   `-- work-windows/
|
|-- schemas/                        # Manifest、profile、锁定文件的结构约束
|-- docs/
|   |-- architecture/
|   |-- guides/
|   |   |-- codex/
|   |   |-- claude-code/
|   |   `-- platforms/
|   |-- maintenance/
|   |-- migrations/
|   |-- decisions/                  # ADR：一项决策一个文件
|   `-- sources/                    # 官方资料清单与人工复核记录
|
|-- src/agent_kits/                 # 未来：跨平台管理面
|   |-- cli/                        # 参数、交互、输出和退出码
|   |-- application/                # inspect/plan/apply/update 用例
|   |-- domain/                     # manifest/lock/plan/receipt/policy
|   `-- infrastructure/             # source/client/platform/state adapters
|-- tests/                          # 未来：schema、渲染、幂等和跨平台测试
|-- .github/workflows/              # 未来：校验、链接扫描、上游变化提醒
`-- llm-repo/                       # Agent 本地工作区，永不上传
```

## 4. 各层职责

| 层级 | 保存什么 | 不保存什么 |
| --- | --- | --- |
| `catalog/` | 单个 Agent、Hook、MCP、Skill、规则的规范源，以及外部集成的锁定声明 | 设备选择、真实 token、生成后的全局文件、外部项目源码副本 |
| `clients/` | 客户端目标路径、格式映射、合并与验收规则 | 业务组件内容、操作系统实现 |
| `platforms/` | agent-kits 自有的 macOS、Windows、Linux 检测与平台适配 | 客户端 wire format、外部产品源码、通用远程服务 |
| `services/` | 由 agent-kits 仓库直接拥有和发布的远程服务 | 外部集成所拥有的 Cloudflare 服务、本机平台实现 |
| `kits/` | 可供用户理解和选择的一组相关组件 | 重复的组件源文件、秘密 |
| `profiles/` | 哪台设备或哪类用户启用哪些 kit，以及变量名引用 | 密码、token、绝对用户目录、客户端缓存 |
| `schemas/` | 声明格式、字段约束、兼容版本 | 具体组件内容 |
| `docs/` | 架构、安装指南、来源、决策和迁移文档 | 自动生成的真实凭据或主目录快照 |

## 5. 组件模型

未来每个可安装组件或外部集成应有独立 manifest，至少表达以下信息：

- 稳定 ID、显示名、版本和维护人。
- 组件类型：agent、hook、mcp、skill、instruction 或 external integration。
- 支持的客户端、客户端最低/最高验证版本。
- 支持的平台和平台前置条件。
- 安装目标、合并策略、冲突策略和卸载边界。
- 所需环境变量或秘密的名称与用途，但不包含值。
- 来源 URL、许可证、固定版本或内容摘要。
- 外部集成的不可变提交 SHA、可读版本、制品摘要和上游发布状态。
- 验证命令、人工验收项和回滚方式。
- 成熟度：experimental、verified 或 deprecated。

组件不能通过“复制整个配置文件”取得所有权。它只能声明自己拥有的字段、
Hook group、MCP server ID 或目录，并在卸载时只移除这些内容。

外部 integration 只保存来源契约和锁定信息，不复制外部仓库源码。实际解析必须
使用完整 commit SHA 或经过校验的 release asset，禁止使用可漂移的默认分支、
裸 tag、Git submodule 当前指针或 `curl | sh`。Tag 用于人类识别，commit SHA
和制品摘要用于机器校验。

## 6. Kit 与 Profile

### 6.1 Kit

Kit 是功能组合，不是第三份实现。例如：

- `base`：团队通用指令、基础 Skill、通用安全 Hook。
- `luna-worker`：Codex `luna_worker` 子代理、对应强制 Hook、操作说明和验收。
- `apple-approval-bridge`：引用外部 `multiple-devices-ai-gateway` 的锁定版本，
  声明 macOS/Codex 兼容条件、所需秘密、安装审批和完整安全验收；不复制其
  Hook、macOS 客户端或 Cloudflare Relay 源码。

### 6.2 Profile

建议至少有以下 profile：

| Profile | 目标 | 典型选择 |
| --- | --- | --- |
| `team-base` | 所有组员和平台 | 通用说明、审查 Skill、低风险 MCP |
| `personal-macos` | 个人 Apple 设备 | `team-base` + Luna + Apple 审批桥 |
| `work-macos` | 工作 Mac | `team-base` + 组织允许的客户端组件 |
| `work-windows` | 工作 Windows | `team-base` + Windows 专属组件，不启用 Apple 审批桥 |

个人电脑与工作电脑“不必完全相同”，而应共享同一基础层，并明确记录受平台、
组织政策或凭据边界影响的差异。强行追求字节级一致会把个人 token、Apple
能力或工作设备策略错误地传播到另一台设备。

## 7. 配置状态分层

建议明确区分四类状态：

1. **仓库源状态**：可提交的组件、模板、profile 和锁定信息。
2. **解析状态**：根据客户端、平台和 profile 生成的安装计划，可审查但不含
   秘密。
3. **设备私有状态**：本地 profile 选择、目标路径覆盖、环境变量和秘密引用，
   默认忽略。
4. **客户端运行状态**：登录、OAuth、信任 hash、缓存、历史、数据库和会话，
   永不由仓库同步。

设备切换时只同步第一类，通过安装器重新生成第二类；第三类由密码管理器、
系统 Keychain/Credential Manager 或组织秘密系统提供；第四类由客户端自己维护。

## 8. 客户端适配策略

### 8.1 Codex

Codex 适配层需要处理：

- `AGENTS.md` 的全局和项目级分层。
- `~/.codex/agents/` 自定义子代理。
- Hook 文件的按组合并、信任和重启验收。
- `config.toml`、MCP、Skill、Plugin 和 rules 的结构化合并。
- 未知字段保留、备份、安装后实际加载检查。

OpenAI 官方文档说明 Codex 会按全局到项目目录链加载 `AGENTS.md`，并对更接近
当前目录的规则赋予更高优先级。因此仓库级指令应保持简洁，特定 kit 的规则应
放在其目标范围内，而不是不断扩大全局文件。

### 8.2 Claude Code

Claude Code 适配层需要处理：

- `CLAUDE.md` 与 `.claude/rules/`。
- 用户级和项目级 agents、skills、hooks、MCP 与 settings。
- Plugin 和 marketplace 作为团队分发层。
- settings 优先级、managed settings 及组织限制。

Anthropic 官方文档将 Plugin 定义为可打包 Skills、Agents、Hooks 和 MCP 的
分发层。对 Claude Code，团队能力成熟后优先发布为私有 marketplace 中的
Plugin；仓库仍保留规范源和生成规则，避免把 `~/.claude/` 当作同步目录。

### 8.3 新客户端

新增客户端时只应增加 `clients/<client-id>/` 适配和必要的专属 catalog 内容，
不得修改通用 Skill 或平台模块来塞入客户端私有格式。

## 9. 安装生命周期

未来命令行能力建议遵循以下流程：

```text
doctor -> resolve -> plan -> approve -> backup -> apply -> verify
                                             `-> rollback on failure
```

- `doctor`：检查客户端版本、平台、依赖、目标目录权限和组织策略。
- `resolve`：合并 team profile、device profile、client 和 platform overlay。
- `plan`：展示将新增、修改、保留和冲突的字段/文件。
- `approve`：交互确认高风险 Hook、MCP、权限和外部命令。
- `backup`：保存受影响文件的可恢复副本，不备份登录态和秘密。
- `apply`：原子写入或结构化合并，保证重复执行幂等。
- `verify`：检查文件格式及客户端实际加载状态。
- `rollback`：仅恢复本次拥有的变更和备份。

CLI 是上述生命周期的统一管理面，不属于 `clients/`。Codex、Claude Code 是目标
客户端；macOS、Windows 和 Linux 是运行平台，Ubuntu 是 Linux 发行版能力。CLI
的模块边界、来源准入、安装作用域和分层更新协议见
`CLI_AND_UPDATE_ARCHITECTURE.md`。

## 10. 安全边界

仓库中禁止出现：

- Codex、Claude、GitHub、Cloudflare 或 MCP 的 token。
- `~/.codex/auth.json`、`~/.claude.json`、OAuth 缓存或客户端数据库。
- 真实手机号、Apple ID、工作邮箱、内网地址或设备绝对路径。
- macOS Keychain、Windows Credential Manager 或系统证书的导出内容。
- Hook 信任 hash、会话历史、聊天记录和运行日志。

仓库只保存 `${ENV_NAME}`、Keychain item 名称、Credential Manager target 名称
等引用。安装时缺少秘密应明确失败或降级，不能用默认秘密继续运行。

## 11. 当前文档和 Luna 的归位建议

现有 `docs/CODEX_LUNA_WORKER_SETUP.md` 在评审阶段保留原位。实施阶段建议拆为：

- `catalog/agents/codex/luna-worker/`：Agent 规范源。
- `catalog/hooks/codex/enforce-luna-worker/`：强制 Hook 及所有权声明。
- `kits/luna-worker/`：组合 manifest 和验收要求。
- `docs/guides/codex/luna-worker.md`：用户安装、信任、验证和故障排查。
- `docs/sources/`：OpenAI 官方链接、最近检查日期和内容摘要。

指南不应继续承担唯一配置源的职责，否则文档示例与真实安装文件会逐渐不一致。

## 12. 评审决策点

开始实现前需要明确以下事项：

1. 是否接受 `catalog + clients + platforms + services + kits + profiles`
   六层结构。
2. Claude Code 是否优先走私有 Plugin marketplace，还是先做直接文件安装。
3. 是否确认 `multiple-devices-ai-gateway` 长期保持独立仓库，由 kit 使用
   `v1.0.0 + 完整 commit SHA + 制品摘要` 固定引用；在上游正式创建 release
   前只登记为 `source-pinned`，不提供无人值守安装。
4. 工作设备是否存在 managed settings、MCP allowlist 或禁止个人 Hook 的组织
   策略。
5. Profile 采用“按角色共享”还是“每台设备一个可提交 profile”；建议前者，
   设备私有差异放本地忽略文件。
6. 自动更新采用只开 Issue，还是在低风险文档变化时自动创建 PR；不建议自动
   合并。
7. 是否接受 Python CLI 管理面、`project/user` 作用域、Markdown 仅生成待审
   提案，以及 CLI/仓库/外部来源/设备环境四类更新相互独立。

## 13. 官方参考

以下链接已于 2026-08-21 实际访问：

- [OpenAI Docs：AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [OpenAI Docs：Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [OpenAI Docs：Hooks](https://learn.chatgpt.com/docs/hooks)
- [OpenAI Docs：MCP](https://learn.chatgpt.com/docs/extend/mcp)
- [OpenAI Docs：Build Skills](https://learn.chatgpt.com/docs/build-skills)
- [Anthropic：Extend Claude Code](https://code.claude.com/docs/en/features-overview)
- [Anthropic：Claude directory](https://code.claude.com/docs/en/claude-directory)
- [Anthropic：Plugins](https://code.claude.com/docs/en/plugins)
- [Anthropic：Settings](https://code.claude.com/docs/en/settings)
