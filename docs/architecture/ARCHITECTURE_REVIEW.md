# agent-kits 架构评审结论

> 状态：Accepted for phased implementation
>
> 更新日期：2026-08-21
>
> 本文评审现有四份核心设计文档，不实现目录、schema、CLI、安装器或 GitHub
> Actions。

## 1. 评审结论

当前提案适合作为长期目标架构，建议以以下六个责任层为基线：

```text
catalog -> clients -> platforms -> services -> kits -> profiles
```

六层并不是顺序调用链，而是六种所有权：

- `catalog` 保存单个能力的规范源。
- `clients` 负责 Codex、Claude Code 等格式和目标路径。
- `platforms` 负责 macOS、Windows、Linux 本机差异。
- `services` 负责 Cloudflare Relay 等远程运行单元。
- `kits` 把多个能力组合成用户可选择的功能包。
- `profiles` 决定某类用户或设备启用哪些 kit。

这个结构能够同时回答“能力是什么”“给哪个客户端”“在哪个平台运行”“是否有
远程服务”“如何组合”“谁安装”六个问题。它比按客户端复制完整目录更适合持续
扩展，也能正确隔离 Apple 和 Windows 能力。

## 2. 必须保留的三个约束

### 2.1 `catalog` 是唯一内容源

`clients/<client>/templates/` 只能保存客户端格式片段和渲染规则，不能复制完整
Skill、Agent 或 Hook 内容。否则 `catalog` 和 `clients` 会形成双重来源。

### 2.2 Kit 只能引用，不能复制

`kits/apple-approval-bridge` 应引用 `catalog/integrations/external/` 中锁定的
`multiple-devices-ai-gateway`，不能复制其 Codex Hook、macOS 客户端或 Relay
服务。Kit 是组合与兼容性边界，不是源码目录。

### 2.3 Profile 表示一致性，不追求主目录字节一致

“个人电脑和工作电脑配置相同”应解释为：

- 相同的 `team-base` 版本。
- 相同组件在兼容平台上的配置语义一致。
- 平台和组织策略差异被显式声明并可解释。
- 秘密、登录态、信任状态和缓存不参与同步。

这比同步整个 `~/.codex/` 或 `~/.claude/` 更可靠，也避免把个人 Apple 信息带到
工作 Windows 设备。

## 3. 原始需求追踪

| 编号 | 原始要求 | 文档证据 | 评审状态 |
| --- | --- | --- | --- |
| 1 | Codex、Claude Code、未来客户端；组内快速配置 Agent/Hook/MCP/Skill；多设备一致 | `PROJECT_STRUCTURE_PROPOSAL.md` 第 1、3、6、7、8 节 | 已覆盖 |
| 2 | 整合 `multiple-devices-ai-gateway` | `MULTIPLE_DEVICES_AI_GATEWAY_INTEGRATION.md` 第 1、3、4、6、9 节 | 已覆盖，推荐远程版本化引用 |
| 3 | 全局安装且 Apple 与 Windows 分层 | `PROJECT_STRUCTURE_PROPOSAL.md` 第 2.3、3、8、9 节；整合提案第 2、5 节 | 已覆盖 |
| 4 | 持续更新并上传 GitHub | 项目提案“仓库身份”；更新策略第 3、4、5、7 节 | 已覆盖，未执行 Git |
| 5 | Luna 文档安装模式、官方链接扫描、GitHub Actions 和自更新 | 项目提案第 11 节；更新策略第 2 至 8 节 | 已覆盖 |
| 6 | 记录 GitHub HTTPS/SSH 地址 | 项目提案“仓库身份” | 已覆盖 |
| 7 | 先文档设计，不编码，随后评审 | 四份核心设计文档、本文及 README；目标目录均未创建 | 已覆盖，等待确认 |

## 4. 七项决策的推荐默认值

| 决策 | 推荐默认值 | 理由 | 是否必须人工确认 |
| --- | --- | --- | --- |
| 六层结构 | 接受，但 V1 只创建实际使用的子目录 | 长期边界清楚，同时避免空目录噪声 | 是 |
| Claude Code 分发 | V1 由统一安装器直接安装；组件模型稳定后发布私有 Plugin marketplace | 先验证跨客户端规范源，再承担 marketplace 版本和策略复杂度 | 是 |
| 旧网关关系 | 长期保持独立仓库；kit 固定 release + commit + digest，不迁移源码、不用 submodule | 保留独立发布和真机证据，避免 Apple-only 源码污染通用仓库 | 是；上游先补正式 Release |
| 工作设备策略 | 先运行只读 doctor，发现 managed settings、allowlist 和 Hook 限制 | 本地现状不能代表工作设备组织策略 | 必须在工作设备确认 |
| Profile 粒度 | 提交 `team-base`、角色和平台 profile；设备私有覆盖文件本地忽略 | 共享语义一致，避免提交绝对路径和个人信息 | 是 |
| 自动更新 | V1 只开 Issue；成熟后仅对低风险元数据创建待审 PR；永不自动安装 | 可观测、可回滚，不扩大高权限供应链 | 是 |
| CLI 管理面 | Python V1；CLI 独立于六层内容模型；Markdown 只生成待审提案；四类更新分离 | 复用当前项目和 Conda，保持跨客户端/跨平台边界，避免把外部文本当安装器 | 是 |

## 5. 建议的 V1 范围

长期目标树不应一次全部落地。用户确认架构后，V1 建议只覆盖：

1. Python CLI 的命令/JSON 输出契约和管理面模块边界。
2. 一个通用 `team-base` profile。
3. Codex 和 Claude Code 两个客户端适配边界。
4. Luna Agent + 强制 Hook，作为第一个完整 kit。
5. 一个不含秘密的 MCP 示例组件和一个可复用 Skill，用来验证模型是否通用。
6. `doctor`、`source inspect` 与 `plan`，先完成只读发现、来源检查和变更预览。
7. schema、敏感信息扫描、文档链接扫描和隔离主目录测试。
8. 旧审批网关登记为 external integration；上游没有正式 Release 前只允许
   `source-pinned + manual-only`，不搬源码或重新部署。

V1 不应包含：

- 自动写入真实个人或工作设备的高风险配置。
- 自动合并或自动安装上游变化。
- 未经真机验证的 Windows 审批桥。
- Claude Code 或其他客户端尚未实现的审批 backend。
- 把现有用户主目录反向导出成仓库源文件。

## 6. 实施顺序建议

```text
ADR / schema
    -> CLI contract + source admission
    -> catalog + profile resolver
    -> doctor + source inspect + plan
    -> isolated-home render/merge tests
    -> Luna kit apply/verify/rollback
    -> Claude direct install
    -> GitHub validation and upstream watch
    -> external gateway kit registration
    -> upstream release readiness and optional Claude marketplace
```

安装器在能稳定生成并解释 plan 之前，不应获得修改真实全局配置的能力。

## 7. 通过标准

架构评审可在以下事项确认后结束：

- [x] 接受六层责任模型。
- [x] 接受上述七项默认决策，按 V1 风险顺序分阶段实施。
- [x] 确认 Python CLI 管理面、来源准入、安装作用域和四类更新协议。
- [ ] 明确工作设备组织策略的调查责任和时间点。
- [x] 确认旧网关长期独立发布；上游 `v1.0.0` Release 仍是自动安装前置条件。
- [x] 确认 V1 先做只读 `doctor + plan`，再做隔离安装和真实环境 opt-in。
- [x] 确认没有用户授权前不执行 Git、部署和真实全局配置修改。

工作设备组织策略仍需在对应设备调查，不阻塞只读 CLI 和隔离事务实现。当前实施
计划见 `../implementation/CLI_V1_IMPLEMENTATION_PLAN.md`。
