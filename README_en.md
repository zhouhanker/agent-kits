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

The official `v0.1.4` installer and self-update flow are verified on macOS.
The Windows installer has CI coverage but has not yet been verified on a real
Windows device. The external Apple gateway remains manual-only until it has an
immutable Release, artifact digest, license, and CI evidence.
