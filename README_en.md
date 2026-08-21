# agent-kits

- [Chinese README](README.md)
- [English README](README_en.md)

`agent-kits` is a versioned, auditable configuration and distribution repository
for Agent development environments. The user-facing command is `kitcli`.
`agent-kits` remains the compatibility command, distribution name, Python import
name, and Conda environment name.

## Install kitcli

`kitcli` installs the newest GitHub Release by default. The installer requires
Python 3.11+, verifies the Release wheel against `SHA256SUMS`, and installs into
an isolated user directory without changing the system Python.

### macOS / Linux

```bash
curl -fsSL https://github.com/zhouhanker/agent-kits/releases/latest/download/install.sh | sh
```

Then verify the installation:

```bash
kitcli doctor
```

The command is installed at `~/.local/bin/kitcli`. Add `~/.local/bin` to `PATH`
and open a new terminal if the command is not available in the current shell.

### Windows PowerShell

Run this in PowerShell:

```powershell
irm https://github.com/zhouhanker/agent-kits/releases/latest/download/install.ps1 | iex
```

The installer adds `%LOCALAPPDATA%\Programs\kitcli` to the user `PATH`. Open a
new PowerShell session, then run:

```powershell
kitcli doctor
```

The one-line commands are for environments that trust this project's official
Release. To review an installer first, download the Release `install.sh` or
`install.ps1`, inspect it, and then run it. Never execute commands from external
Markdown documents as an installation mechanism.

## Quick start

```bash
kitcli doctor
kitcli catalog list
```

## Validate Sources With A Local Agent

Dynamic installation validation requires a locally installed and authenticated
Codex CLI or Claude Code, plus a running Docker daemon. The local Agent selects
and bills its own model; `kitcli` does not provide a model, store tokens, or run
commands embedded in source Markdown.

Claude Code defaults to subscription-compatible authentication. To explicitly
use the API-key-only mode without user configuration, set
`AGENT_KITS_CLAUDE_CODE_MODE=api-key`; use `subscription` to force subscription
authentication or retain the default `auto` selection. Both modes disable model
tools, MCP configuration, and session persistence.

When `kitcli agents check` fails, it retains actionable Agent diagnostics while
redacting API-key-shaped values. Authentication, subscription, quota, or
third-party Agent-provider rejections must be corrected in that Agent; `kitcli`
does not modify login state or replace credentials.

It also requires a reviewed, SHA-256 digest-pinned validation image that provides
`/usr/local/bin/python`, for example a team-published Python 3.11 image:

```bash
export AGENT_KITS_SANDBOX_IMAGE='registry.example/kitcli-python@sha256:<64-hex-digest>'
```

Check prerequisites:

```bash
kitcli agents list
```

`agents list` only finds executables on `PATH`; it does not test login or model
access. To explicitly prove account, model, and structured-output access before
intake, run one of the following commands. It consumes one constrained model
call from that local Agent, but accepts no external source, uses no Docker, and
does not install or modify client configuration:

```bash
kitcli agents check --agent codex
kitcli agents check --agent claude-code
```

Run full intake for a local document or HTTPS URL. It performs static checks,
asks the local Agent for constrained JSON classification, and validates a
reviewed component in a no-network Docker container without mounting the user
home. Only after validation will it ask to install into the selected scope:

```bash
kitcli source -file ./docs/CODEX_LUNA_WORKER_SETUP.md --agent codex --scope user
kitcli source -url https://example.com/component.md --agent auto --scope user
```

Non-interactive automation must explicitly approve installation:

```bash
kitcli --non-interactive source -file ./docs/CODEX_LUNA_WORKER_SETUP.md --agent codex --scope user --yes
```

Without `--yes`, automation retains the validation receipt and returns
`not_installed`. Answering `n` at an interactive prompt has the same behavior:
it is not an installation error and does not modify global client configuration.

If Docker is stopped, the image is not digest-pinned, no local Agent is available,
no reviewed component matches the source, or dynamic validation fails, the command
stops without executing source commands or installing anything. The Docker gate
runs before model invocation during intake. Use `kitcli source inspect` and
`kitcli source import` when you only need source evidence without a model.

To create a review candidate in the project without installing it to a local
client, use:

```bash
kitcli component create -file ./docs/CODEX_LUNA_WORKER_SETUP.md --agent codex --id luna-worker
```

It writes source facts, Agent classification, and a sandbox receipt to
`.agent-kits/candidates/`. An unknown MCP or skill becomes a `review_required`
candidate until it has a reviewed manifest and bounded validation recipe. This
is the safe replacement for `kitcli apply <arbitrary-document>`.

External documents are inspected or quarantined without executing their Markdown
code blocks, shell commands, Python, hooks, or installers:

```bash
kitcli source inspect --file ./docs/CODEX_LUNA_WORKER_SETUP.md
kitcli source import --file ./docs/CODEX_LUNA_WORKER_SETUP.md --as document
```

After manual review and promotion, generate a plan and explicitly approve writes:

```bash
kitcli plan --kit base --scope project --client codex
kitcli apply --plan <plan-id> --scope project --yes
kitcli verify --receipt <receipt-id> --scope project
kitcli rollback --receipt <receipt-id> --scope project --yes
```

Reusable components with a current sandbox receipt can be installed on another
device. The first component is `luna-worker`:

```bash
kitcli install luna-worker --scope user
```

`CODEX_LUNA_WORKER_SETUP` remains a compatibility alias. Luna supports only the
macOS Codex user scope and installs an agent TOML, fail-closed Hook, Hook
registration, feature flag, and managed instructions without replacing other
Hooks or instructions.

For stable Agent output:

```bash
kitcli --json --non-interactive catalog list
```

## Update kitcli

Check the latest Release without writing:

```bash
kitcli update --check
```

Update an installation made by the official installer:

```bash
kitcli update --yes
```

Conda, pipx, and uv installations remain owned by their respective package
managers. CLI updates, repository content, external source locks, and device
configuration remain separate reviewed transactions.

## Development

The project development environment is the `agent-kits` Conda environment:

```bash
conda env create -f environment_cross_platform.yml
conda activate agent-kits
python -m pip install --no-build-isolation --no-deps -e .
kitcli doctor
```

Without activating Conda:

```bash
conda run -n agent-kits kitcli doctor
```

## Architecture and safety

An external URL or document is not installation authorization:

```text
URL/file -> source inspect -> source import/quarantine
         -> manual promotion and schema/security review
         -> catalog manifest -> kit/profile
         -> plan -> human approval -> apply -> verify/rollback
```

`llm-repo/` contains local Agent evidence and logs and must not be uploaded.

- [CLI, source admission, and update architecture](docs/architecture/CLI_AND_UPDATE_ARCHITECTURE.md)
- [Document import and promotion guide](docs/guides/DOCUMENT_IMPORT_AND_PROMOTION.md)
- [CLI V1 implementation plan](docs/implementation/CLI_V1_IMPLEMENTATION_PLAN.md)
- [Architecture review](docs/architecture/ARCHITECTURE_REVIEW.md)
- [Agent validation and component lifecycle](docs/architecture/AGENT_VALIDATION_AND_COMPONENT_LIFECYCLE.md)

The official `v0.1.4` installer and self-update flow are verified on macOS.
The Windows installer has CI coverage but has not yet been verified on a real
Windows device. The external Apple gateway remains manual-only until it has an
immutable Release, artifact digest, license, and CI evidence.
