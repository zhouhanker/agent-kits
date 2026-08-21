# 动态 Agent 验证排障与验收

`kitcli` 的动态来源验证由三个独立前置条件组成：可调用的本机 Agent、隔离执行
环境，以及可验证的组件定义。三者必须同时成立；任何一个失败都不能安装到用户或
项目环境。

## 1. 先验证本机能力

```bash
kitcli agents list
kitcli agents check --agent codex
kitcli agents check --agent claude-code
kitcli agents check --agent model-api
```

`list` 不调用模型，仅确认二进制是否在 `PATH`。`check` 会发送固定的、无来源内容的
结构化 JSON probe，因此会使用本机 Agent 的登录态和额度，但不会执行 Docker、下载来源
或写入客户端配置。

通过 `check` 的 Agent 才可用于 `source`。能回答普通文本、但不能遵守
`--output-schema` 或 `--json-schema` 的 Agent 不是可用的动态验证器。
`model-api` 读取本地 `env.toml` 的 OpenAI-compatible 配置并要求返回相同 JSON
结构；它不需要在容器中登录。

| 结果 | 含义 | 处理责任 |
| --- | --- | --- |
| 二进制未发现 | 本机没有受支持 CLI | 安装或配置对应 Agent CLI |
| 401/认证失败 | Agent 登录或 API key 无效 | 在 Agent 自身完成登录或修复凭据 |
| 403/提供方拒绝结构化输出 | 当前提供方或客户端策略不支持该调用 | 升级/配置标准客户端，或联系提供方 |
| 超时/额度失败 | Agent 无响应或不可用 | 检查账户额度、网络和 Agent 服务状态 |
| 成功返回 JSON | Agent 可完成受限分类 | 继续检查 Docker 和 component receipt |

`kitcli` 不读取、替换或修复 Agent 凭据。错误诊断会脱敏 API-key 形式的内容。

## 2. 配置隔离验证环境

```bash
docker info --format '{{.ServerVersion}}'
export AGENT_KITS_SANDBOX_IMAGE='python@sha256:<reviewed-image-digest>'
```

镜像必须是带 `@sha256:` 的不可变引用，并且包含组件验证所需的运行时。验证容器默认
无网络、只读根文件系统、无用户主目录或凭据挂载；只有受审 payload 被渲染到临时
工作目录。Docker 可用并不能证明 Agent 的登录或模型能力。

macOS/Linux 推荐 Docker Engine/Desktop，Docker 不可用时支持 Podman。Windows 推荐
Docker Desktop 的 WSL2 Linux-container backend；Podman Desktop 是可选后备。原生
Windows container 与 Linux runtime 的语义不同，当前不作为跨平台 component 验证器。
无论运行时位于 WSL2 或 Podman machine，`kitcli` 都只依赖容器 CLI 和 daemon，不要求
项目自身在 WSL 发行版中安装。

## 3. 验证而不安装 Luna

先以非交互模式运行，不传 `--yes`：

```bash
kitcli --json --non-interactive source \
  -file ./docs/CODEX_LUNA_WORKER_SETUP.md \
  --agent model-api \
  --scope user
```

成功输出必须同时包含：

- `analysis.kind = "codex_subagent"`；
- `validation.status = "validated"`；
- 与当前指南和 catalog payload 对应的 source/candidate SHA-256；
- `installation.status = "not_installed"`。

此时 receipt 已保存在本地状态目录，但没有修改 `~/.codex/`。检查输出后，在交互
终端重跑同一命令并回答 `y`，或在自动化中显式提供 `--yes`，才会安装。当前 macOS
开发环境已使用 `model-api` 和 Docker 完成这一无安装验收；其 receipt 仅对当时的
指南 SHA-256、catalog payload SHA-256 和 Docker backend 有效。

安装后仍需在真实 Codex 中确认 `/hooks` 显示 Hook 已信任并实际运行一次
`luna_worker`。Docker receipt 证明受控配置和 Hook fixture，不证明 Codex 客户端的
信任状态或模型账户可用。

## 4. 外部 MCP 或 Skill 的准入

`kitcli source -url URL` 可静态读取 HTTPS 来源并由可用 Agent 分类，但不会执行网页
或 Markdown 中的安装命令。未知 MCP/Skill 仅能生成 `review_required` 候选。

将其变为可复用、可安装组件前，维护者必须在 catalog 中补齐：

1. 不可变 Release asset、commit 或内容 SHA-256。
2. 不包含秘密的 component manifest 与 payload。
3. 运行时、可执行文件、参数、环境变量名和目标客户端。
4. 固定且有超时限制的 sandbox health check。
5. 安装目标、字段所有权、备份和 rollback 边界。

完成后，sandbox 只运行 manifest 声明的固定 health check，不会审查无关项目源码。
这适用于内部的 `multiple-devices-ai-gateway`：只需为它准备明确组件的不可变制品和
验证 recipe，而不需要将整个仓库导入或交给 Agent 审查。

## 5. 其他设备复用

只有 source digest、candidate digest 和 sandbox receipt 都与已审 catalog 对应时，才可：

```bash
kitcli install <component-id> --scope user
```

接收设备仍必须满足组件自身的 Agent、Docker、平台和客户端版本条件。`install` 只写
manifest 允许的目标路径，并继续使用 `plan/apply/verify/rollback` 的 receipt 机制。
