@/Users/zhouhan/.codex/RTK.md

# agent-kits project instructions

## Project conventions

- This is a Python project managed by the Conda environment `agent-kits`.
- The distribution name is `agent-kits`; the import package name is `agent_kits`.
- Use the `src/` package layout and standard Python naming conventions: modules,
  functions, methods, and variables use `snake_case`; classes use `PascalCase`;
  constants use `UPPER_SNAKE_CASE`.
- Keep code modular. Runtime values must come from configuration files or
  environment variables; never hard-code credentials, endpoints, or
  environment-specific paths.
- Prefer Conda packages. Use pip only when a package is unavailable from the
  configured Conda channels. Any installed dependency must also be recorded in
  `environment_cross_platform.yml`.

## Agent workspace

- Append each Agent task and its verification result to `llm-repo/agent.md`.
- Track overall progress and the next executable step in `llm-repo/fplan.md`.
- Record unresolved issues, failed nodes, and risks in `llm-repo/warn.md`.
- Follow `llm-repo/schema.md` when creating durable pages under `llm-repo/wiki/`.
- Store source captures under `llm-repo/raw/`, verified durable knowledge under
  `llm-repo/wiki/`, and temporary external deliverables under
  `llm-repo/output/` as HTML and PDF.
- At roughly 60% context usage, checkpoint the active task, operation log,
  current node, errors, unresolved issues, and next plan into the corresponding
  `llm-repo` files, then update the continuation status in this file.

## Git safety

- Do not run Git commands without the user's explicit instruction.
- Before any requested upload, review every Git command and inspect the staged
  file list for secrets and sensitive files.
- Never upload `llm-repo/`; it is excluded by `.gitignore`.
- Never conceal or claim resolution of an unresolved blocker.

## Continuation status

- Current node: architecture baseline approved; schema/catalog, read-only CLI,
  isolated transaction, and quarantine phases are complete. No real global
  configuration has been modified.
- Accepted architecture documents:
  `docs/architecture/ARCHITECTURE_REVIEW.md`,
  `docs/architecture/PROJECT_STRUCTURE_PROPOSAL.md`,
  `docs/architecture/CLI_AND_UPDATE_ARCHITECTURE.md`,
  `docs/architecture/MULTIPLE_DEVICES_AI_GATEWAY_INTEGRATION.md`, and
  `docs/maintenance/UPSTREAM_DOCUMENTATION_UPDATE_STRATEGY.md`.
- Recommended defaults and the seven-requirement traceability audit are in
  `docs/architecture/ARCHITECTURE_REVIEW.md`.
- CLI decision: use Python for V1, expose the short `kitcli` command, and retain
  `agent-kits` as a compatibility alias. Model the CLI as a
  management plane outside the six content layers. GitHub bundles require
  immutable manifests/digests; Markdown imports only create review proposals.
- Update decision: CLI, repository content, external source
  locks, and installed-device state use separate check/plan/apply transactions.
- Document ingestion decision: use `source inspect/import` for quarantine only;
  manually promote reviewed material into `docs/guides`, `docs/sources`,
  `catalog`, kits, and profiles. Never execute Markdown directly. Procedure:
  `docs/guides/DOCUMENT_IMPORT_AND_PROMOTION.md`.
- Gateway decision: keep
  `zhouhanker/multiple-devices-ai-gateway` independent and reference an
  immutable upstream release from `catalog/integrations/external/`; do not
  migrate, vendor, or add it as a Git submodule.
- Remote audit on 2026-08-21 found package version `1.0.0` at commit
  `f5c3b1142ca709d9763bb0d455265ff178c41232`, but no Tag, Release, release
  artifact/checksum, CI workflow, PyPI distribution, declared LICENSE, commit
  signature, or branch protection.
- Detailed implementation plan:
  `docs/implementation/CLI_V1_IMPLEMENTATION_PLAN.md`.
- Next node: evaluate real non-macOS devices, real macOS client loading,
  upstream gateway Release readiness, and branch protection. The supported
  OS/Python CI matrix and official `v0.1.4` installer E2E are complete.
  Repository/source `update check` is read-only; the official isolated
  installer supports explicit `kitcli update --check` / `kitcli update --yes`
  for the CLI only. No device configuration is changed by that operation.
- Current command naming: use `kitcli` in user-facing commands and documentation;
  keep `agent-kits` as the compatibility console alias and package/environment
  identifier. `README.md` is the Chinese default entry point; `README_en.md`
  is the English entry point, while `README_zh.md` remains a Chinese
  compatibility link.
- Global distribution: the official installer scripts are under `scripts/` and
  the tagged Release workflow is `.github/workflows/release.yml`. Release
  `v0.1.4` is the current verified installer reference. Windows remains CI-only
  until a real Windows host is tested.
- Blocking conditions: work-device policy and upstream gateway Release remain
  external gates, but do not block the local V1 CLI foundation.
- Known risks: see `llm-repo/warn.md`.

## Continuation Checkpoint 2026-08-21

- Current node: the local user installation has been replaced by the official
  checksum-verified `v0.1.4` Release installer.
- Verified entry points: `~/.local/bin/kitcli` and the `agent-kits`
  compatibility alias; metadata is in `~/.local/share/kitcli/install.json`.
- Verified operations: catalog JSON, doctor, `update --check`, `update --yes`,
  14 unittest cases, `compileall`, and `pip check`.
- Unresolved: real Windows installation, non-macOS device validation, macOS
  client loading evidence, external gateway Release contract, and branch
  protection. Do not report these as complete.
