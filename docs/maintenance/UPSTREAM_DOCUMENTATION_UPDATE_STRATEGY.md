# 上游文档扫描与自更新策略

> 状态：Accepted baseline for phased implementation
>
> 更新日期：2026-08-21
>
> 本文设计未来自动化，不包含 GitHub Actions 实现。

## 1. 目标

Agent 客户端的 Hook、MCP、Skill、子代理和配置格式会更新。仓库需要尽早发现：

- 官方链接失效或重定向。
- 页面内容、配置字段、协议或支持版本发生变化。
- GitHub Release、包依赖或 Action 版本有新版本。
- 本仓库指南中的示例与规范源不一致。

自动化的目标是“发现并提出变更”，不是“未经审查地修改全局 Agent 环境”。

## 2. 来源注册表

建议未来在 `docs/sources/` 维护机器可读来源注册表。每条记录至少包含：

- 稳定来源 ID 和维护人。
- 官方 URL、机器可读 URL 和上游仓库/Release URL。
- 影响的客户端、组件和本仓库文档。
- 检查模式：HTTP、redirect、content digest、release 或 schema probe。
- 最近成功检查时间、最近人工复核时间和复核周期。
- 已知稳定标题/章节或关键字段，不保存整页镜像。
- 当前内容摘要、ETag 或 Last-Modified（上游提供时）。
- 变化风险：low、medium、high。

OpenAI Docs 当前提供 `https://learn.chatgpt.com/llms.txt` 索引，并说明文档页面
可通过追加 `.md` 获取机器可读版本。Anthropic 也提供
`https://code.claude.com/docs/llms.txt` 和对应 `.md` 页面。扫描时应优先使用
这些官方机器可读入口，避免依赖易变化的网页 DOM。

## 3. 三层检查

### 3.1 每次 Pull Request：确定性校验

建议检查：

- Markdown 链接语法和内部锚点。
- 外部链接 HTTP 状态、重定向链和目标域名。
- manifest/profile/schema 格式。
- 文档中声明的文件路径确实存在。
- 组件文档、manifest、兼容矩阵和锁定版本一致。
- 禁止文件与敏感信息模式。
- 生成内容是否与规范源一致。

PR 检查必须可重复、无秘密、无设备副作用，不应访问个人 `~/.codex` 或
`~/.claude`。

### 3.2 定时任务：上游变化探测

建议每周执行，也允许手工 `workflow_dispatch`：

1. 获取官方 `llms.txt`，确认已登记页面仍存在。
2. 获取 `.md` 页面并做规范化摘要，忽略更新时间、导航和非语义噪声。
3. 比较标题、关键配置字段、协议示例和内容摘要。
4. 查询已锁定工具、包、Action 和 GitHub Release 的新版本。
5. 生成变化报告，标明影响的 kit、客户端和指南。

仅 HTTP 200 不能证明内容仍正确；仅比较全文 hash 又会产生大量排版噪声。
因此应同时保留“可达性 + 结构关键点 + 规范化摘要”三类信号。

### 3.3 发布前：真实兼容性复核

涉及 Hook schema、客户端路径、权限、MCP transport、Skill 格式或子代理配置的
变化，需要在受支持平台运行：

- 客户端版本检查。
- 安装 plan 和 dry-run。
- 临时主目录中的安装、重复安装和卸载。
- 与已有用户配置的合并和回滚。
- 客户端实际发现、加载和信任检查。
- 对高风险 kit 的人工设备验收。

只有通过这层检查，兼容矩阵才能从“待验证”更新为“verified”。

## 4. GitHub Actions 工作流建议

未来可设计四个独立工作流：

| 工作流 | 触发 | 产物 | 是否修改仓库 |
| --- | --- | --- | --- |
| `validate` | PR、push | schema、链接、敏感信息、生成一致性报告 | 否 |
| `upstream-watch` | 每周、手工 | 官方文档和 Release 变化报告 | 默认只开 Issue |
| `dependency-update` | Dependabot/Renovate | 包和 Action 的独立 PR | 创建 PR，不自动合并 |
| `compatibility` | 手工、Release 候选 | 多 OS 矩阵与安装器验收 | 否 |

定时任务存在延迟或暂时停用的可能，不能把它当成强实时监控。重要客户端升级
仍应在发布流程中主动检查。

## 5. 变化处理策略

### 5.1 只开 Issue

以下变化默认只创建 Issue：

- Hook 输入/输出结构变化。
- 新权限、信任机制或 managed policy。
- MCP transport 或认证变化。
- Agent/Skill 加载优先级变化。
- 页面内容大幅变化或关键章节消失。

Issue 应包含旧摘要、新摘要、受影响文件、风险级别和人工复核清单。

### 5.2 可自动创建 PR

低风险变化可以自动创建 PR：

- URL 永久重定向且官方域名和页面语义不变。
- 文档登记的 `last_checked` 和内容摘要更新。
- 锁定依赖或 Action 的补丁版本更新，并且测试通过。
- 由规范源确定性生成的文档片段更新。

自动 PR 必须把来源 diff 和验证结果写入正文，且不得包含秘密。

### 5.3 不自动合并

不建议对以下内容启用自动合并：

- Hook、MCP、Agent、Skill 或 Plugin 的行为变更。
- 全局配置目标路径和合并策略。
- 权限、命令、网络目标或供应链来源变化。
- Apple 审批桥或远程服务协议变化。

这些文件能够执行命令、访问外部系统或改变 Agent 决策边界，必须人工审查。

## 6. Luna 文档的更新方式

现有 `docs/CODEX_LUNA_WORKER_SETUP.md` 中三个 OpenAI 官方链接于 2026-08-21
检查均返回 HTTP 200：

- `agent-configuration/subagents`
- `hooks`
- `agent-configuration/agents-md`

但链接可达不代表配置仍兼容。Luna kit 应另外跟踪：

- 自定义 Agent 文件字段及默认继承规则。
- 可用模型和 `model_reasoning_effort` 值。
- Hook event、matcher、输入/输出和信任机制。
- `spawn_agent` 的参数约束。
- Codex CLI/App/IDE 的最低验证版本。

当上游变化时，自动化先标记该 kit 为 `review_required`，运行隔离验证并创建
报告。人工确认后再更新文档、组件版本和兼容矩阵，不能只替换链接。

## 7. 设备端自更新

“自更新”至少拆成四个独立目标：

1. **CLI 更新**：Conda、pipx 和 uv 继续由各自包管理器替换；官方用户目录安装器
   支持 `kitcli update --check` / `kitcli update --yes`，仅更新其隔离虚拟环境。
2. **仓库更新**：用户主动获取并校验已审查的 tag/release。
3. **外部来源更新**：逐项审查 integration 的 release、commit 和 digest 后更新
   source lock。
4. **环境同步**：运行 `plan` 查看本机与已选仓库版本的差异，明确批准后执行
   `apply`，最后 `verify`。

不建议让后台任务从默认分支直接拉取最新内容并修改全局目录。推荐使用固定
release/tag、校验摘要和变更说明；工作设备还应遵守组织允许的来源与版本范围。

未来可以提供只读通知：检测到新 release 后提醒用户，但不自动运行 Hook 或
安装第三方 MCP。失败时保留原版本和备份，支持显式 rollback。

Markdown 和 GitHub 链接的来源准入、CLI 命令面、安装作用域及更新事务详见
`../architecture/CLI_AND_UPDATE_ARCHITECTURE.md`。普通 Markdown 只能进入隔离
检查并生成待审提案，不能被当作脚本直接执行。

## 8. Action 安全要求

- 工作流 `permissions` 默认只读，只有创建 Issue/PR 的 job 获得最小写权限。
- 第三方 Action 固定到完整 commit SHA，并由更新机器人提出升级 PR。
- 不在来自 fork 的不受信代码上暴露仓库 secret。
- 抓取上游文档的 job 不加载个人 MCP、Hook 或 Agent 配置。
- 不执行从上游页面提取出的命令；上游内容仅作为不可信数据解析。
- 生成的 Issue/PR 正文进行长度限制和转义，避免日志或模板注入。
- 自动化不得读取或上传 `llm-repo/`。

## 9. 建议采用的工具类别

实施时可评估：

- 链接检查器：支持重定向、重试、缓存和忽略规则。
- Dependabot 或 Renovate：维护 Python、npm 和 GitHub Action 版本。
- 自有小型检查器：解析官方 `llms.txt`、Markdown 标题和关键配置字段。
- GitHub Issue/PR：承载变更报告和人工审批，不直接写设备。

工具选择应在实现阶段通过 ADR 确认，本轮不引入依赖。

## 10. 官方参考

以下页面已于 2026-08-21 实际访问：

- [OpenAI Docs 索引](https://learn.chatgpt.com/llms.txt)
- [OpenAI Docs：Hooks](https://learn.chatgpt.com/docs/hooks)
- [OpenAI Docs：Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Anthropic 文档索引](https://code.claude.com/docs/llms.txt)
- [Anthropic：Extend Claude Code](https://code.claude.com/docs/en/features-overview)
- [GitHub Actions：Scheduled events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GitHub Actions：Secure use](https://docs.github.com/en/actions/reference/security/secure-use)
- [GitHub Dependabot version updates](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/configure-version-updates)
