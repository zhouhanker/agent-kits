# agent-kits

- [English README](README.md)
- [中文 README](README_zh.md)

`agent-kits` is a versioned, auditable configuration and distribution repository
for Agent development environments. Its intended scope
includes Codex, Claude Code, future Agent clients, subagents, hooks, MCP
servers, skills, reusable instructions, platform-specific integrations, and
device profiles.

The repository contains the V1 standard-library CLI, validated manifests,
profiles, source quarantine, isolated plan/apply/verify/rollback transactions,
and architecture documentation. Real user-global installation, GitHub Actions,
and external gateway installation remain gated by the implementation plan.

## Architecture Review

Review these documents before implementation:

- [Architecture review and recommended defaults](docs/architecture/ARCHITECTURE_REVIEW.md)
- [Project structure proposal](docs/architecture/PROJECT_STRUCTURE_PROPOSAL.md)
- [CLI, source admission, and update architecture](docs/architecture/CLI_AND_UPDATE_ARCHITECTURE.md)
- [multiple-devices-ai-gateway integration proposal](docs/architecture/MULTIPLE_DEVICES_AI_GATEWAY_INTEGRATION.md)
- [Upstream documentation and update strategy](docs/maintenance/UPSTREAM_DOCUMENTATION_UPDATE_STRATEGY.md)
- [Existing Codex Luna worker setup guide](docs/CODEX_LUNA_WORKER_SETUP.md)
- [Document import and promotion guide](docs/guides/DOCUMENT_IMPORT_AND_PROMOTION.md)

The architecture baseline is approved for phased implementation. Progress and
acceptance gates are tracked in
[the CLI V1 implementation plan](docs/implementation/CLI_V1_IMPLEMENTATION_PLAN.md).

Planned upstream repository: <https://github.com/zhouhanker/agent-kits.git>.
No Git remote or repository state was changed during the documentation phase.

## Environment

Create or update the Conda environment from the repository root:

```bash
conda env create -f environment_cross_platform.yml
# For an existing environment:
conda env update -n agent-kits -f environment_cross_platform.yml
conda activate agent-kits
```

Install the local package without downloading build dependencies:

```bash
python -m pip install --no-build-isolation --no-deps -e .
```

The editable install creates `kitcli` inside the active Conda environment. From
the repository directory, either activate that environment first or call the
environment explicitly:

```bash
conda activate agent-kits
kitcli doctor
# without activation:
conda run -n agent-kits kitcli doctor
```

For a user-global command on macOS or Linux, install the checksum-verified
wheel into an isolated user directory. The installer uses Python 3.11+ and
does not modify the system Python:

```bash
curl -fsSL https://github.com/zhouhanker/agent-kits/releases/latest/download/install.sh -o /tmp/kitcli-install.sh
less /tmp/kitcli-install.sh
sh /tmp/kitcli-install.sh
```

The installer puts `kitcli` in `~/.local/bin` and tells you if that directory
needs to be added to `PATH`. Windows users should download and inspect
`install.ps1`, then run it from PowerShell; it installs under
`%LOCALAPPDATA%\\Programs\\kitcli` and adds that directory to the user PATH.
The GitHub Release must contain a versioned wheel and `SHA256SUMS`; the
installer fails closed when either is missing.

## CLI

Use `kitcli doctor` and `kitcli catalog list` for read-only discovery. The
installed `agent-kits` command remains available as a compatibility alias.
Inspect or quarantine a GitHub/Markdown source with `kitcli source inspect` or
`kitcli source import`; imported Markdown is never executed. Generate a reviewed
plan with `kitcli plan --kit base --scope project --client codex`, then explicitly
apply it with `kitcli apply --plan <plan-id> --scope project --yes`. Verify and
roll back using the resulting receipt. User scope is available through
`--scope user` and is tested with isolated client roots; no real global
configuration is modified by the test suite.

## CLI updates

An installation made by the official installer records only its fixed HTTPS
Release asset and checksum locations. Run `kitcli update --check` to download
and verify the candidate wheel without writing. Run `kitcli update --yes` to
replace the isolated CLI through its recorded Python environment. Conda, pipx,
and uv installations remain owned by those package managers; use their normal
upgrade command and then run `kitcli update check` for repository/source state.
Plain `kitcli update` is equivalent to the read-only check.

## Layout

```text
src/agent_kits/   Python package
tests/            Automated tests
catalog/          Source-controlled kits and external locks
profiles/         Source-controlled profile selections
schemas/          Versioned declaration schemas
docs/             Project documentation
llm-repo/         Agent-local evidence and work logs (not committed)
```

The V1 standard-library CLI is implemented and tested for source inspection,
quarantine import, catalog discovery, plan/apply/verify/rollback transactions,
and read-only update checks. Real global installation, signed standalone
artifacts, external gateway installation, and non-macOS device verification
remain gated by the documented release and validation requirements.
