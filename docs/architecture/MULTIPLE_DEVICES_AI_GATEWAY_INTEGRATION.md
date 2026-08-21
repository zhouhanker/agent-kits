# multiple-devices-ai-gateway 整合提案

> 状态：Accepted boundary，保持独立仓库并固定远程版本
>
> 更新日期：2026-08-21
>
> 本文基于本地目录
> `/Users/zhouhan/dev_env/work_project/py/multiple-devices-ai-gateway` 和公开 GitHub
> 仓库 <https://github.com/zhouhanker/multiple-devices-ai-gateway> 的只读盘点。
> 本轮不移动代码、不安装、不部署，也不执行 Git 操作。

## 1. 已确认现状

旧项目 V1 是已经真机验证的 macOS-only Codex 权限审批桥：

- 使用 Codex `PermissionRequest` Hook。
- 先显示 macOS 本地审批弹窗，15 秒未操作后才进入远程链路。
- 通过 macOS Messages 向 iPhone 发送一次性审批链接。
- Apple Watch 通过系统 Messages 通知镜像获得提醒。
- 使用 macOS Keychain 保存 agent token。
- 使用 Cloudflare Worker 和 Durable Object 保存加密请求与一次性决策状态。
- 当前 Codex backend 已实现；Claude Code 和 Grok Build 只有扩展边界，不能
  宣称支持。
- Windows 客户端只做过研究，没有安装器、消息通道、凭据存储或真机验收。

### 远程仓库状态（2026-08-21）

GitHub API 与远程文件核对结果：

- 仓库公开，默认分支为 `main`。
- `main` 当前指向
  `f5c3b1142ca709d9763bb0d455265ff178c41232`，与本地交接记录一致。
- `pyproject.toml` 声明版本 `1.0.0`、Python 3.10+ 和 macOS classifier。
- README 明确 V1 已定版，仅接受明确安全修复，并明确 Windows 不支持。
- 当前没有 Git Tag、GitHub Release、GitHub Actions workflow 或 PyPI 发布。
- `main` 未启用分支保护；定版提交未签名。
- GitHub commit archive 可下载，但它不是带项目校验和的正式 release asset。

因此，“代码已在 GitHub”证明它适合继续独立维护，但尚不等于已经存在可供
`agent-kits` 安全自动安装的不可变发布通道。

旧项目已经建立了正确的一个边界：Agent 私有 wire format 位于
`backends/<client>/`，共享审批模型和远程流程位于 `approval_bridge/`。但共享
目录内仍包含 Keychain、Messages 和本地弹窗等 macOS 实现。保持独立仓库时，
这些实现不需要物理拆入 `agent-kits`；`agent-kits` 只记录它们的客户端、平台
和服务边界，用于兼容性判断、选择、安装编排和验收。

## 2. 为什么不能整体放入 Apple 层

旧仓库包含三类性质不同的资产：

| 资产 | 架构职责 | 物理源码归属 |
| --- | --- | --- |
| Codex payload、决定格式、Hook 合并 | Codex 客户端能力 | 上游仓库 |
| 本地弹窗、Messages、Keychain、macOS 安装器 | macOS 平台能力 | 上游仓库 |
| 审批模型、AES-GCM、状态机、Relay 客户端 | 上游共享核心 | 上游仓库 |
| Cloudflare Worker / Durable Object | 外部远程服务 | 上游仓库 |
| iPhone / Apple Watch 说明与验收 | Apple 生态交付边界 | 上游仓库；agent-kits 只引用正式文档 |

因此建议保留面向用户的 kit 名称 `apple-approval-bridge`，但它只引用外部
integration，不在 `clients/`、`platforms/` 或 `services/` 中复制上游实现。
Compatibility metadata 仍使用 `macos`，因为当前真正执行的客户端只在 macOS；
iOS/watchOS 没有原生应用代码。

## 3. 目标归位

```text
catalog/
`-- integrations/
    `-- external/
        `-- multiple-devices-ai-gateway/
            |-- manifest             # upstream、版本、平台、客户端和成熟度
            |-- source-lock          # 完整 commit SHA、release asset、摘要
            |-- compatibility        # Codex/macOS/Worker 协议范围
            `-- acceptance           # 上游证据与本机复验要求

kits/
`-- apple-approval-bridge/
    `-- manifest                      # 引用 external integration，不含源码

profiles/
`-- personal-macos/                  # 可选启用该 kit；Windows 不解析安装

docs/
|-- guides/platforms/apple-approval-bridge.md
|-- architecture/approval-bridge.md
`-- integrations/multiple-devices-ai-gateway.md
```

`platforms/macos/` 仍负责 agent-kits 自有的平台检测和路径抽象，但不拥有审批
桥源码；`services/` 只保存 agent-kits 自己发布的远程服务，因此不复制上游
Cloudflare Worker。这样既保留六层架构，又避免造成源码已迁入的错误暗示。

## 4. 推荐整合方式

### 4.1 结论：远程版本化引用，不迁移源码

`multiple-devices-ai-gateway` 已有独立仓库、独立包、完整测试边界、部署协议和
真机验收，应继续拥有自己的发布生命周期。把源码迁入 `agent-kits` 会带来：

- 两个项目的发布和安全修复耦合。
- 已部署 Worker、macOS 客户端和文档的来源变化。
- 定版 V1 的验证证据需要整体重建。
- Apple-only 运行依赖进入通用配置仓库。

也不建议使用 Git submodule：它会增加克隆、更新、Windows 使用和组员 onboarding
成本，却不能替代 release、摘要和安装契约。

### 4.2 正式引用契约

推荐上游先把当前提交发布为真正的 `v1.0.0`：

1. Tag 指向 `f5c3b1142ca709d9763bb0d455265ff178c41232`。
2. 创建 GitHub Release，附上版本说明、支持矩阵和升级顺序。
3. 附加 wheel、sdist 或明确的源码制品及 `SHA256SUMS`。
4. 最好启用 CI，并对 tag/制品增加签名或 provenance。
5. 补充明确 LICENSE，便于团队安装、再分发和审计。

`agent-kits` 的 source lock 同时保存可读版本、完整 commit SHA、制品 URL 和
SHA-256。安装器先验证平台与摘要，再展示 plan；不能从 `main` 直接安装，也不
执行 `curl | sh`。

### 4.3 当前过渡状态

在上游还没有 Tag/Release 时，可以登记：

- upstream URL。
- 完整 commit SHA。
- `version = 1.0.0`。
- `release_status = source-pinned`。
- `install_policy = manual-only`。

这允许架构和兼容性文档引用该项目，但不应把它描述成可自动更新的正式 release。
Tag/Release 完成后再切换为 `release-pinned`。

只有上游项目被明确废弃、两边需要共享内部代码且独立包边界无法维持时，才重新
评估源码迁移。当前没有这些条件。

## 5. Windows 边界

Windows 不应出现一个空的“Apple 等价实现”并被标为支持。建议建立
`platforms/windows/README.md`，明确列出待决策接口：

- 本地审批 UI。
- 凭据存储：Windows Credential Manager 或组织秘密系统。
- 远程通知通道。
- Codex/Claude Code Hook 的 Windows 安装与进程生命周期。
- PowerShell、路径和文件权限语义。
- 真实 Windows 设备的 allow、deny、timeout、offline 和 rollback 验收。

Windows 可以复用 Relay、加密、状态机和客户端协议适配，但必须在上述平台端口
实现并通过真机验收后，才能在兼容矩阵中标为 verified。

## 6. 安全和迁移不变量

远程引用和安装编排不得破坏上游已经形成的安全属性：

- token 只存在于 Cloudflare Secret 和系统凭据存储，不进入仓库、普通配置、
  日志、URL 查询参数或 Agent 工作区。
- Hook 合并保留无关 group，替换前创建备份。
- 本地或远程失败时安全回退或拒绝，绝不静默允许。
- action token 单次、随机、有时效；Worker 不保存明文命令详情。
- 客户端与 Worker 协议有明确升级顺序和兼容窗口。
- 安装、升级和卸载只修改本 kit 拥有的文件或字段。
- 单元测试不能替代 Mac、iPhone、Apple Watch 和未来 Windows 的真机验收。

## 7. 需要保留的证据

整合时至少应保留并重建下列证据链：

- `README.md` 中的支持矩阵和真实设备范围。
- `docs/approval-bridge.md` 的协议、安全模型、升级和故障排查。
- `docs/backend-architecture.md` 的 backend contract 和 fail-closed 路由。
- Codex Hook 示例、安装器合并/卸载测试和备份规则。
- Python、Cloudflare Worker 与真机验收记录。
- 版本 `1.0.0` 以及旧安装入口的兼容策略。
- 远程仓库、完整 commit SHA、正式 release asset 和摘要之间的对应关系。
- 上游测试结果与 Mac/iPhone/Apple Watch 真机验收的版本归属。

`llm-repo/` 仍然不能迁入可上传内容。可以把其中已经验证、确实需要长期维护的
结论重新整理成正式 `docs/`，但不能原样复制 Agent 本地记录。

## 8. 迁移前评审问题

1. 是否确认旧项目长期保持独立 GitHub 仓库，`agent-kits` 不迁入或复制源码？
2. 是否授权后续在上游单独创建 `v1.0.0` Tag/Release、制品和摘要？本轮没有
   Git 或发布授权。
3. Cloudflare Worker 是否由个人账号部署，还是未来转到团队账号和环境？
4. Apple 审批桥是否仅属于个人 profile，还是允许组员自行选择安装？
5. 组内安全策略是否允许远程审批 Hook，是否需要额外审计或组织批准？
6. Windows 的目标是复用同一远程审批产品，还是优先采用 Codex Remote 等官方
   能力？该决策必须先在真实 Windows 主机验证后再做。

## 9. 远程证据

以下地址于 2026-08-21 只读访问：

- [GitHub 仓库](https://github.com/zhouhanker/multiple-devices-ai-gateway)
- [定版提交](https://github.com/zhouhanker/multiple-devices-ai-gateway/commit/f5c3b1142ca709d9763bb0d455265ff178c41232)
- [README](https://github.com/zhouhanker/multiple-devices-ai-gateway/blob/f5c3b1142ca709d9763bb0d455265ff178c41232/README.md)
- [pyproject.toml](https://github.com/zhouhanker/multiple-devices-ai-gateway/blob/f5c3b1142ca709d9763bb0d455265ff178c41232/pyproject.toml)

GitHub API 在该日期返回：零 Tag、零 Release、零 Actions workflow，默认分支
`main` 未保护，定版提交为 unsigned。PyPI 对该分发名返回 404。
