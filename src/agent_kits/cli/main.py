"""Stable human and machine-facing command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from agent_kits.application.service import (
    context,
    run_apply,
    run_agents_check,
    run_agents_list,
    run_catalog_list,
    run_component_create,
    run_doctor,
    run_plan,
    run_rollback,
    run_install,
    run_source_import,
    run_source_intake,
    run_source_inspect,
    run_update_check,
    run_update_cli,
    run_verify,
)
from agent_kits.domain.errors import AgentKitsError

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_VALIDATION = 3
EXIT_CONFLICT = 4
EXIT_POLICY = 5
EXIT_INTERNAL = 10


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kitcli", description="Plan and verify cross-platform Agent configuration kits.")
    parser.add_argument("--repository", help="agent-kits repository root")
    parser.add_argument("--project-root", help="project scope root (default: current directory)")
    parser.add_argument("--json", action="store_true", help="emit a stable JSON envelope")
    parser.add_argument("--non-interactive", action="store_true", help="never prompt; write commands still require --yes")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="inspect platform and client paths")
    agents = subparsers.add_parser("agents", help="inspect local Agent and sandbox prerequisites")
    agents_sub = agents.add_subparsers(dest="agents_command", required=True)
    agents_sub.add_parser("list", help="list discovered local Agent executables without using a model")
    agent_check = agents_sub.add_parser("check", help="prove one local Agent can complete a constrained model call")
    agent_check.add_argument("--agent", choices=("auto", "codex", "claude-code"), default="auto")
    catalog = subparsers.add_parser("catalog", help="inspect local catalog")
    catalog.add_subparsers(dest="catalog_command", required=True).add_parser("list", help="list validated kits")

    source = subparsers.add_parser("source", help="inspect or quarantine untrusted sources")
    source_sub = source.add_subparsers(dest="source_command", required=True)
    inspect = source_sub.add_parser("inspect", help="inspect local or HTTPS source")
    _add_source_arguments(inspect)
    inspect.add_argument("--max-bytes", type=int)
    import_parser = source_sub.add_parser("import", help="quarantine source for review")
    _add_source_arguments(import_parser)
    import_parser.add_argument("--as", dest="source_kind", choices=("document", "bundle"), required=True)
    intake = source_sub.add_parser("intake", help="analyze and validate a source with a local Agent")
    _add_source_arguments(intake)
    intake.add_argument("--agent", choices=("auto", "codex", "claude-code"), default="auto")
    intake.add_argument("--scope", choices=("project", "user"), default="user")
    intake.add_argument("--yes", action="store_true", help="approve installation after validation")

    plan = subparsers.add_parser("plan", help="create a reviewable installation plan")
    plan.add_argument("--kit", required=True)
    plan.add_argument("--profile")
    plan.add_argument("--scope", choices=("project", "user"), required=True)
    plan.add_argument("--client", action="append", choices=("codex", "claude-code"))

    apply = subparsers.add_parser("apply", help="apply an approved plan")
    apply.add_argument("--plan", dest="plan_id", required=True)
    apply.add_argument("--scope", choices=("project", "user"), required=True)
    apply.add_argument("--yes", action="store_true")

    verify = subparsers.add_parser("verify", help="verify an installation receipt")
    verify.add_argument("--receipt", dest="receipt_id", required=True)
    verify.add_argument("--scope", choices=("project", "user"), required=True)

    rollback = subparsers.add_parser("rollback", help="restore an installation receipt")
    rollback.add_argument("--receipt", dest="receipt_id", required=True)
    rollback.add_argument("--scope", choices=("project", "user"), required=True)
    rollback.add_argument("--yes", action="store_true")

    install = subparsers.add_parser("install", help="install a sandbox-validated component")
    install.add_argument("component")
    install.add_argument("--scope", choices=("project", "user"), default="user")
    install.add_argument("--yes", action="store_true", help="approve installation")

    component = subparsers.add_parser("component", help="create a local review candidate without global installation")
    component_sub = component.add_subparsers(dest="component_command", required=True)
    create = component_sub.add_parser("create", help="analyze and record a source as a review candidate")
    _add_source_arguments(create)
    create.add_argument("--agent", choices=("auto", "codex", "claude-code"), default="auto")
    create.add_argument("--id", dest="component_id")

    update = subparsers.add_parser("update", help="check or update the CLI installation")
    update.add_argument("--check", action="store_true", help="check the official release without writing")
    update.add_argument("--yes", action="store_true", help="approve replacing the isolated CLI installation")
    update_sub = update.add_subparsers(dest="update_command", required=False)
    check = update_sub.add_parser("check", help="check update targets without writing")
    check.add_argument("--target", choices=("all", "cli", "repository", "sources", "environment"), default="all")
    return parser


def _add_source_arguments(command: argparse.ArgumentParser) -> None:
    """Add explicit source selectors while retaining positional compatibility."""

    command.add_argument("source", nargs="?", help=argparse.SUPPRESS)
    group = command.add_mutually_exclusive_group()
    group.add_argument("-file", "--file", dest="source_file", help="local source file")
    group.add_argument("-url", "--url", dest="source_url", help="HTTPS source URL")


def _source_value(args: argparse.Namespace, parser: argparse.ArgumentParser) -> str:
    selected = [value for value in (args.source, args.source_file, args.source_url) if value]
    if len(selected) != 1:
        parser.error("source requires exactly one positional value, --file, or --url")
    if args.source_file and args.source_url:
        parser.error("--file and --url are mutually exclusive")
    return selected[0]


def _result(command: str, data: Any, as_json: bool) -> None:
    envelope = {"ok": True, "command": command, "data": data}
    if as_json:
        print(json.dumps(envelope, ensure_ascii=False, sort_keys=True))
        return
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                print(f"{key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}")
            else:
                print(f"{key}: {value}")
    else:
        print(data)


def _error_code(error: Exception) -> int:
    name = error.__class__.__name__
    if name == "ConflictError":
        return EXIT_CONFLICT
    if name == "PolicyError":
        return EXIT_POLICY
    if name in {"ValidationError", "NotFoundError"}:
        return EXIT_VALIDATION
    return EXIT_INTERNAL


def _normalize_argv(argv: list[str] | None) -> list[str]:
    """Accept `source -file/-url` as the concise source-intake form."""

    values = list(sys.argv[1:] if argv is None else argv)
    try:
        source_index = values.index("source")
    except ValueError:
        return values
    remainder = values[source_index + 1 :]
    if remainder and remainder[0] in {"inspect", "import", "intake"}:
        return values
    if any(item in {"-file", "--file", "-url", "--url"} for item in remainder):
        values.insert(source_index + 1, "intake")
    return values


def _confirmed(confirm: bool, non_interactive: bool, prompt: str) -> bool:
    if confirm:
        return True
    if non_interactive or not sys.stdin.isatty():
        return False
    return input(prompt).strip().lower() in {"y", "yes"}


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(_normalize_argv(argv))
    except SystemExit as error:
        return int(error.code)
    as_json = bool(args.json)
    command = args.command
    try:
        repository, project_root = context(args.repository, args.project_root)
        if command == "doctor":
            data = run_doctor(repository, project_root)
        elif command == "agents":
            data = run_agents_list() if args.agents_command == "list" else run_agents_check(args.agent)
        elif command == "catalog":
            data = run_catalog_list(repository)
        elif command == "component":
            try:
                source_value = _source_value(args, parser)
            except SystemExit as error:
                return int(error.code)
            data = run_component_create(repository, project_root, source_value, args.agent, args.component_id)
        elif command == "source":
            try:
                source_value = _source_value(args, parser)
            except SystemExit as error:
                return int(error.code)
            if args.source_command == "inspect":
                data = run_source_inspect(source_value, args.max_bytes)
            elif args.source_command == "import":
                data = run_source_import(source_value, args.source_kind)
            else:
                data = run_source_intake(repository, source_value, args.agent, args.scope, project_root)
                if data["installable"]:
                    approved = _confirmed(args.yes, bool(args.non_interactive), "Install validated component to the selected scope? [y/N] ")
                    if approved:
                        data["installation"] = run_install(repository, project_root, data["component_id"], args.scope, True)
                    else:
                        data["installation"] = {
                            "installed": False,
                            "status": "not_installed",
                            "reason": "explicit confirmation is required",
                        }
        elif command == "plan":
            data = run_plan(repository, project_root, args.kit, args.scope, args.client, args.profile)
        elif command == "apply":
            data = run_apply(args.plan_id, args.scope, project_root, args.yes)
        elif command == "verify":
            data = run_verify(args.receipt_id, args.scope, project_root)
        elif command == "rollback":
            data = run_rollback(args.receipt_id, args.scope, project_root, args.yes)
        elif command == "install":
            approved = _confirmed(args.yes, bool(args.non_interactive), "Install component to the selected scope? [y/N] ")
            data = run_install(repository, project_root, args.component, args.scope, approved)
        elif command == "update":
            if args.update_command == "check":
                data = run_update_check(repository, project_root, args.target)
            else:
                if args.non_interactive and not args.yes and not args.check:
                    raise AgentKitsError("Non-interactive CLI update requires --yes or --check")
                data = run_update_cli(check_only=args.check or not args.yes, yes=args.yes)
        else:
            parser.error(f"unsupported command: {command}")
            return EXIT_USAGE
        _result(command, data, as_json)
        return EXIT_OK
    except AgentKitsError as error:
        envelope = {"ok": False, "command": command, "error": {"type": error.__class__.__name__, "message": str(error)}}
        if as_json:
            print(json.dumps(envelope, ensure_ascii=False, sort_keys=True))
        else:
            print(f"kitcli: {error}", file=sys.stderr)
        return _error_code(error)
    except (OSError, ValueError) as error:
        envelope = {"ok": False, "command": command, "error": {"type": error.__class__.__name__, "message": str(error)}}
        if as_json:
            print(json.dumps(envelope, ensure_ascii=False, sort_keys=True))
        else:
            print(f"kitcli: {error}", file=sys.stderr)
        return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
