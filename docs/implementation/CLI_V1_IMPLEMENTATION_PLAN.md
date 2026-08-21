# kitcli CLI V1 实施计划

> 状态：Locally complete，外部 CI、设备和上游发布门禁待验证
>
> 批准日期：2026-08-21
>
> 本计划执行 `CLI_AND_UPDATE_ARCHITECTURE.md`。每个阶段完成后必须更新本文、
> `llm-repo/fplan.md`、`llm-repo/agent.md` 和必要的风险记录。

## 1. 本轮交付边界

V1 使用 Python 标准库实现，不新增第三方运行依赖，交付以下能力：

- `kitcli doctor`：只读检查平台、Python、仓库、客户端目录和状态目录。
- `kitcli catalog list`：读取并验证 kit manifest。
- `kitcli source inspect`：只读检查本地文件或 HTTPS 来源并计算 SHA-256。
- `kitcli source import`：把 Markdown 或 bundle 放入 quarantine，绝不执行。
- 来源命令支持显式 `--file`/`--url` 选择；旧位置参数仅作兼容。
- `kitcli plan`：为已登记 kit 生成不可变 JSON plan。
- `kitcli apply/verify/rollback`：以原子写、摘要和回执管理事务。
- `kitcli update check`：分别报告 CLI、repository、sources 和 environment，
  不执行 Git、包管理器或设备写入。
- 人类文本输出和 Agent `--json --non-interactive` 输出契约。

V1 提供一个低风险 `base` kit，用隔离测试证明项目/用户作用域、Codex/Claude
目标适配和 Markdown managed block 合并。不会自动修改当前真实全局配置。

## 2. 明确不包含

- 任意 Markdown 代码块或远程脚本执行。
- 跟踪 GitHub 默认分支、隐式 `git pull` 或自动 Git 操作。
- 未经确认的 CLI 自覆盖更新、后台自动 apply 或系统管理员作用域。官方用户目录
  安装器支持显式 `kitcli update --check` 和 `kitcli update --yes`。
- Apple 审批网关自动安装；其上游 Release 契约尚未满足。
- 工作设备 managed policy、Windows Apple 审批桥或未经真机验证的兼容声明。
- 自动把 Luna 长文档转换成可执行 Hook。Luna 拆分在基础事务能力稳定后单独评审。

## 3. 数据契约

V1 使用 TOML 维护人工编辑的 kit/profile/source 声明，使用 JSON 保存机器生成的
plan、receipt、quarantine metadata 和 update report。

每个 kit manifest 至少包含：

- `schema_version`、`id`、`version`、`description`、`risk`。
- payload 的相对路径与 SHA-256。
- 支持的 client、platform、scope。
- 目标位置、写入策略和 managed block ID。

V1 仅实现 `managed_markdown_block` 策略。目标路径必须相对、安全且位于作用域根
目录内；payload 摘要不匹配时拒绝生成 plan。

## 4. 状态和事务

项目作用域本地状态位于 `<project>/.agent-kits/`；用户作用域状态使用平台标准
目录。所有路径都可通过命令参数或 `AGENT_KITS_*` 环境变量覆盖，以支持隔离测试。

```text
plans/<plan-id>.json
receipts/<receipt-id>.json
backups/<receipt-id>/
quarantine/documents/<sha256>/
quarantine/bundles/<sha256>/
```

plan 只记录目标文件写入前/后的摘要和待写入内容，不保存目标文件的完整旧内容，
避免把用户已有私密信息写入 plan。apply 必须确认 plan 未被修改且目标仍处于规划
时状态；verify 比较当前摘要；rollback 只在目标仍等于本事务写入摘要时恢复备份，
避免覆盖后续用户修改。

## 5. 分阶段计划

### Phase 0 - 文档和批准

- [x] CLI、来源准入、作用域和更新架构获得执行授权。
- [x] 定义 V1 范围、非目标、数据契约和验收标准。
- [x] 保留 Git 禁令和外部网关 Release 阻塞项。

### Phase 1 - Schema、Catalog 和 Profile

- [x] 添加 kit/profile/source-lock JSON Schema 文档。
- [x] 添加 `base` kit manifest、payload 和 `team-base` profile。
- [x] 添加外部 Apple 网关的 `source-pinned + manual-only` 锁定声明。
- [x] 验证所有摘要、标识符和相对路径。

### Phase 2 - 只读 CLI

- [x] 添加 console entry point、稳定退出码和 JSON envelope。
- [x] 实现 repository/config/platform/client path discovery。
- [x] 实现 `doctor`、`catalog list` 和 `source inspect`。
- [x] 添加成功、无效 manifest、HTTP policy 和本地来源测试。

### Phase 3 - 安装事务

- [x] 实现 resolver 和 plan 持久化。
- [x] 实现 managed Markdown block 渲染与幂等合并。
- [x] 实现 apply、receipt、verify 和安全 rollback。
- [x] 在临时 project/user home 中验证 Codex 和 Claude Code。

### Phase 4 - 来源准入和更新检查

- [x] 实现 Markdown quarantine import。
- [x] 实现安全 zip bundle 检查和 quarantine import。
- [x] 实现四类 `update check` 只读报告。
- [x] 验证代码块不执行、路径穿越拒绝和大小限制。

### Phase 5 - 分发和跨平台验证

- [x] 更新 README 和命令参考。
- [x] 添加 macOS/Linux 用户目录安装器、Windows PowerShell 安装器和 Release 工作流。
- [x] 添加无秘密、只读默认的 GitHub Actions 多 OS 测试定义。
- [x] 在当前 Conda `agent-kits` 环境完成单元、CLI、安装和包健康检查。
- [x] 记录未能本地证明的 Windows/Linux/macOS 真机边界。

Phase 5 本地部分完成。GitHub Actions 尚未在本次会话实际运行，Windows/Linux
主机和真实 macOS 客户端加载仍是外部验证门禁，不得标记为本机已验证。

## 6. 验收标准

- 所有写操作都有 plan、目标摘要、receipt、verify 和 rollback 证据。
- 重复 apply 幂等；目标在 plan 后变化时拒绝；rollback 不覆盖后续修改。
- URL/Markdown 不能直接触发 apply 或命令执行。
- project 与 user 作用域不越界，路径穿越和 symlink 逃逸被拒绝。
- CLI 默认人类可读，`--json` 输出可稳定解析且错误有非零退出码。
- plan 和 receipt 都有完整性摘要，篡改会在写入/验证前失败。
- 测试不访问真实 `~/.codex`、`~/.claude`，不执行 Git，不需要网络。
- `environment_cross_platform.yml` 与实际依赖保持一致。

## 7. 后续阶段

V1 验收后再拆分 Luna Agent/Hook 规范源，并以真实 Codex 加载验证作为发布门禁。
Apple 网关只有在上游提供不可变 Release、制品摘要和许可证后，才能从手工锁定
进入可安装 integration。

文档输入的导入、提炼、复用和 Luna 拆分流程见
`../guides/DOCUMENT_IMPORT_AND_PROMOTION.md`。V1 `source import` 只完成 quarantine；
从文档生成新的 catalog/kit 仍需人工提炼和审核。
