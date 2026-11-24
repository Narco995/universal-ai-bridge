from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import BridgeService, BridgeError
from .http_api import serve


def _print(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uab", description="Universal AI Bridge — minimal collaboration workflow v0")
    parser.add_argument("--db", default="bridge.sqlite3", help="SQLite database path (default: ./bridge.sqlite3)")
    commands = parser.add_subparsers(dest="command", required=True)

    task = commands.add_parser("task", help="create or inspect a task")
    task_commands = task.add_subparsers(dest="task_command", required=True)
    create = task_commands.add_parser("create")
    create.add_argument("--objective", required=True)
    create.add_argument("--criteria", action="append", required=True, help="repeat for each acceptance criterion")
    create.add_argument("--mode", choices=["independent", "open"], default="independent")
    create.add_argument("--required-author", action="append", default=[])
    show = task_commands.add_parser("show")
    show.add_argument("task_id")
    close = task_commands.add_parser("close")
    close.add_argument("task_id")
    close.add_argument("--note", default="manual close")
    reveal = task_commands.add_parser("reveal")
    reveal.add_argument("task_id")

    position = commands.add_parser("position", help="submit a manually relayed position")
    position_commands = position.add_subparsers(dest="position_command", required=True)
    submit = position_commands.add_parser("submit")
    submit.add_argument("task_id")
    submit.add_argument("--author", required=True, help="attribution label; not provider authentication")
    submit.add_argument("--content", required=True)
    listing = position_commands.add_parser("list")
    listing.add_argument("task_id")
    listing.add_argument("--viewer", default="human")

    decision = commands.add_parser("decision", help="record a decision after reveal")
    decision_commands = decision.add_subparsers(dest="decision_command", required=True)
    record = decision_commands.add_parser("record")
    record.add_argument("task_id")
    record.add_argument("--choice", required=True)
    record.add_argument("--rationale", required=True)
    record.add_argument("--supporting", action="append", default=[])
    record.add_argument("--considered-not-chosen", action="append", default=[])
    record.add_argument("--requires-approval", action="store_true")

    approval = commands.add_parser("approval", help="record a human approval decision")
    approval.add_argument("task_id")
    approval.add_argument("--action", choices=["approve", "reject", "request_changes"], required=True)
    approval.add_argument("--note", required=True)

    action = commands.add_parser("action", help="check whether an action is authorized")
    action.add_argument("task_id")
    action.add_argument("--name", required=True)

    artifact = commands.add_parser("artifact", help="attach an implementation artifact pointer")
    artifact.add_argument("task_id")
    artifact.add_argument("--kind", required=True, help="e.g. commit, pull_request, test_run, file")
    artifact.add_argument("--uri", required=True)
    artifact.add_argument("--sha256")

    export = commands.add_parser("export", help="export the complete task record")
    export.add_argument("task_id")
    export.add_argument("--format", choices=["json", "markdown"], default="json")
    export.add_argument("--output", help="write to a file instead of stdout")
    export.add_argument("--viewer", default="human")

    verify = commands.add_parser("verify", help="verify the append-only event hash chain")
    verify.add_argument("subcommand", nargs="?", choices=["events"], default="events")

    server = commands.add_parser("serve", help="start the loopback-only HTTP API")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    service = BridgeService(args.db)
    try:
        if args.command == "task":
            if args.task_command == "create":
                _print(service.create_task(args.objective, args.criteria, args.mode, args.required_author))
            elif args.task_command == "show":
                _print(service.get_task(args.task_id))
            elif args.task_command == "close":
                _print(service.close_collection(args.task_id, note=args.note))
            elif args.task_command == "reveal":
                _print(service.reveal(args.task_id))
        elif args.command == "position":
            if args.position_command == "submit":
                _print(service.submit_position(args.task_id, args.author, args.content))
            else:
                _print({"positions": service.list_positions(args.task_id, args.viewer)})
        elif args.command == "decision":
            _print(service.record_decision(args.task_id, args.choice, args.rationale, args.supporting, args.considered_not_chosen, args.requires_approval))
        elif args.command == "approval":
            _print(service.record_approval(args.task_id, args.action, args.note))
        elif args.command == "action":
            _print(service.authorize_action(args.task_id, args.name))
        elif args.command == "artifact":
            _print(service.attach_artifact(args.task_id, args.kind, args.uri, args.sha256))
        elif args.command == "export":
            if args.format == "markdown":
                output = service.markdown_export(args.task_id, args.viewer)
            else:
                output = json.dumps(service.export_timeline(args.task_id, args.viewer), ensure_ascii=False, indent=2, sort_keys=True)
            if args.output:
                Path(args.output).write_text(output + ("\n" if not output.endswith("\n") else ""), encoding="utf-8")
                print(f"Export written to {args.output}")
            else:
                print(output)
        elif args.command == "verify":
            result = service.verify_event_chain()
            _print(result)
            return 0 if result["valid"] else 2
        elif args.command == "serve":
            serve(service, args.host, args.port)
        return 0
    except (BridgeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
