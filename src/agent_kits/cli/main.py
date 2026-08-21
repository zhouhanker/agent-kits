"""Stable human and machine-facing command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from agent_kits.application.service import (
    context,
    run_apply,
    run_catalog_list,
    run_doctor,
    run_plan,
    run_rollback,
    run_source_import,
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
    group.add_argument("--file", dest="source_file", help="local source file")
    group.add_argument("--url", dest="source_url", help="HTTPS source URL")


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


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    as_json = bool(args.json)
    command = args.command
    try:
        repository, project_root = context(args.repository, args.project_root)
        if command == "doctor":
            data = run_doctor(repository, project_root)
        elif command == "catalog":
            data = run_catalog_list(repository)
        elif command == "source":
            try:
                source_value = _source_value(args, parser)
            except SystemExit as error:
                return int(error.code)
            if args.source_command == "inspect":
                data = run_source_inspect(source_value, args.max_bytes)
            else:
                data = run_source_import(source_value, args.source_kind)
        elif command == "plan":
            data = run_plan(repository, project_root, args.kit, args.scope, args.client, args.profile)
        elif command == "apply":
            data = run_apply(args.plan_id, args.scope, project_root, args.yes)
        elif command == "verify":
            data = run_verify(args.receipt_id, args.scope, project_root)
        elif command == "rollback":
            data = run_rollback(args.receipt_id, args.scope, project_root, args.yes)
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
