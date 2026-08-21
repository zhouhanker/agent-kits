# Agent Validation And Component Lifecycle

## Status

Proposed V2 architecture. It replaces the V1 assumption that a static
quarantine alone is sufficient for a component to become installable.

## Decision

`agent-kits` is for users who have a supported local coding Agent. A local
Agent is therefore required for semantic source analysis and real-client
acceptance. It is not a trust root, a credential broker, or a substitute for an
operating-system sandbox.

Supported V2 adapters are:

| Adapter | Semantic analysis | Client acceptance | Notes |
| --- | --- | --- | --- |
| Codex CLI | `codex exec` with structured output and a read-only workspace | Codex component validation | Uses the user's Codex authentication and selected model. |
| Claude Code | `claude --print` with no tools and structured output | Claude Code component validation | Uses the user's Claude Code authentication and selected model; API-key mode additionally uses `--bare`. |
| `model-api` | Host-side OpenAI-compatible JSON request from local `env.toml` | No client acceptance; semantic analysis only | API key remains on the host and is never mounted into a sandbox. |

`kitcli` does not configure, provide, select, or pay for a foundation model.
The selected local Agent or model API account remains responsible for its own
login, model, quota, and provider policy.

`kitcli agents list` is deliberately a zero-cost executable discovery command;
it does not prove login or model access. `kitcli agents check --agent <id>` is
an explicit, fixed-content structured model probe. It proves that the selected
local Agent can make a constrained call, can consume its quota, and makes no
installation, source download, or sandbox operation. Source intake independently
proves the same capability with the actual source only after the Docker gate.
An Agent must successfully support the structured-output capability used by the
adapter. A binary that can produce ordinary text but whose provider rejects
structured output is unavailable for dynamic intake; this is reported as an
Agent prerequisite failure, not as a source or sandbox failure.

## Required Lifecycle

```text
source -> static gate -> Agent analysis -> isolated execution -> receipt
       -> explicit user confirmation -> user/project installation -> reuse
```

1. **Static gate**: read only a regular local file or HTTPS source; retain its
   SHA-256; reject oversized files, invalid redirects, traversal, symlinks, and
   unsafe archives.
2. **Agent analysis**: pass the source as untrusted data to a selected local
   Agent. The Agent has no write tools, returns a schema-checked candidate, and
   classifies it as a Codex subagent, hook, MCP server, skill, or unsupported
   material.
3. **Isolated execution**: render the candidate only under a disposable root.
   Dynamic validation uses a sandbox backend with no secrets, a bounded timeout,
   a narrow writable root, and disabled network unless an approved recipe
   explicitly requires a registry. A successful process exit proves only the
   stated test, not general safety.
4. **Receipt**: write source digest, Agent identity/version, candidate digest,
   sandbox backend, commands, exit status, and timestamps to local state.
5. **Confirmation**: never install globally merely because analysis or a test
   passed. Interactive `y/N` is required for a source intake; non-interactive
   installation requires `--yes`. Declining confirmation retains the validation
   receipt and returns `not_installed`; it is not an installation failure.
6. **Reuse**: promote a verified candidate to a reviewed component, then use a
   stable component ID to install it on another device. Promotion is a source
   change and requires normal repository review and release evidence.

## Command Model

The V1 `plan`, `apply`, `verify`, and `rollback` commands remain the only
transaction commands. `apply` is deliberately not repurposed to parse an
arbitrary document.

```text
kitcli agents list
kitcli agents check --agent auto|codex|claude-code
kitcli agents check --agent model-api
kitcli source inspect --file PATH|--url HTTPS_URL
kitcli source import --file PATH|--url HTTPS_URL --as document|bundle
kitcli source intake --file PATH|--url HTTPS_URL [--agent auto|codex|claude-code|model-api]
kitcli source --file PATH|--url HTTPS_URL [--agent auto|codex|claude-code|model-api]
kitcli component create --file PATH|--url HTTPS_URL --id COMPONENT_ID [--agent ...]
kitcli install COMPONENT_ID --scope user|project [--yes]
```

`kitcli source --file` and `kitcli source --url` are the user-facing intake
commands. They perform static inspection, require a selected supported analysis
provider, and create a validation receipt for a known reviewed component before
prompting for installation. They do not execute source Markdown verbatim.
Direct intake returns its evidence but does not persist a candidate file.

`kitcli component create` is the safe replacement for the proposed
`kitcli apply PATH`: it uses an Agent to produce a structured, reviewable
component candidate in project state and does not alter the user's client
configuration. `kitcli install` resolves a reviewed component into the existing
plan/apply/verify transaction model. It accepts only IDs declared in the
source-controlled component registry; ordinary catalog kits must use `plan`
and `apply` directly.

The V1 `source inspect` and `source import` commands remain available for
evidence capture without an Agent or model invocation.

## Sandbox Backends

The execution backend must be selected explicitly by platform capability:

| Backend | Platforms | Intended use |
| --- | --- | --- |
| Docker Engine/Desktop | macOS, Linux, Windows | Preferred portable dynamic verifier; digest-pinned image, no host home, no host credentials, no default network. Windows Desktop normally uses WSL2 for Linux containers. |
| Podman | macOS, Linux, Windows | Compatible fallback; uses a Podman machine/service on macOS and Windows, commonly WSL2-backed on Windows. |
| None | all | Static gate and Agent analysis only. Dynamic validation fails closed. |

`codex sandbox` is an internal executor interface that requires an existing
Codex sandbox state; it is not a standalone general-purpose sandbox backend.
The deprecated macOS `sandbox-exec` utility is not a supported backend because
its policy behavior is not portable or stable enough to prove the required
isolation. `subprocess` with a temporary current directory is not a sandbox.
Claude Code's
tool permissions and Codex read-only mode constrain an Agent, but they do not
isolate an arbitrary installer process. A source requiring commands outside the
available sandbox policy remains `review_required` and cannot offer global
installation.

The model API is intentionally not called from the validation container. Putting
a long-lived API key in a container and enabling egress would make it a
credential-bearing network client, weakening the isolation boundary. V2 calls
the configured model on the host, then validates only reviewed component payload
under no-network Docker/Podman. A future networked recipe needs a separate
egress proxy, short-lived scoped credential, provider allowlist, and explicit
manifest declaration.

## Component Rules

- `catalog/components.toml` is the source-controlled registry of reusable
  component IDs, compatibility aliases, permitted scopes, backing kit IDs, and
  fixed validator identifiers. Adding a component requires a reviewed registry
  entry, manifest, payload, and validator recipe.
- A Markdown document is evidence, not an executable package.
- The Agent output must be JSON validated against a local schema. It may
  describe files, target client, required capabilities, and a finite validation
  recipe, but may not carry credentials or unrestricted shell text.
- Codex subagent components are rendered into a temporary `CODEX_HOME` and
  checked for TOML/JSON/Python syntax plus their documented Hook protocol.
  Real invocation is an explicit acceptance check with the installed Codex CLI.
- MCP components must declare their executable, arguments, package provenance,
  environment-variable names, required network, and a bounded health check.
  They cannot run until a compatible sandbox backend and an approved manifest
  exist.
- Skills and instruction-only components are schema and target-path validated;
  they require real client loading evidence before being marked verified.
- A successful sandbox receipt is scoped to the exact source and candidate
  SHA-256. Changing either invalidates the receipt.

## Luna Guide Application

`docs/CODEX_LUNA_WORKER_SETUP.md` becomes the first Codex subagent component.
Its reusable payload is split into a Luna agent TOML, a fail-closed Hook script,
a Hook registration fragment, and an instruction block. The sandbox verifies
the rendered files and valid/invalid Hook fixtures. Global installation happens
only after the local Codex adapter is detected, the sandbox receipt is current,
and the user answers `y` or supplies `--yes`.

## Security Boundaries

- Prompt injection in a source is expected. Agent prompts must state that source
  content is untrusted data and that it cannot authorize tools, network access,
  installation, or policy changes.
- Model output is advisory until schema validation and sandbox verification
  succeed.
- Agent credentials, client state, Keychain data, Cloudflare credentials, and
  user homes are never mounted into dynamic validation.
- A global installation may change only manifest-declared paths and is always
  reversible through a receipt.
- External integrations such as `multiple-devices-ai-gateway` need only prove
  their declared component installation recipe in the sandbox. They do not need
  to expose unrelated project internals to `agent-kits`.
