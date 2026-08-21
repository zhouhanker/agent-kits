## Subagent Constraints

- Prefer `luna_worker` for suitable delegated tasks.
- Every subagent invocation must explicitly set `agent_type = "luna_worker"`.
- Do not use `default`, `worker`, `explorer`, or another custom agent type.
- Use `fork_turns = "none"` or a positive integer string; do not use `"all"`.
- Do not override the Luna worker model or reasoning effort at invocation time.
- If `luna_worker` is unavailable, complete the task with the primary Agent.
