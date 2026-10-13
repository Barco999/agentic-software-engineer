"""Trusted local CLI; no unauthenticated HTTP workflow mutations exist."""

import argparse
import json

from orchestration.service import WorkflowService
from scenarios import SCENARIOS


def main(argv=None):
    parser = argparse.ArgumentParser(description="Governed agent workflow (local operator only)")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start")
    start.add_argument("scenario", choices=SCENARIOS)
    start.add_argument("--offline", action="store_true")
    start.add_argument("--requirement")
    start.add_argument("--fault-mode", choices=["", "fail_once", "always_fail"], default="")
    for name in ("approve", "reject"):
        command = commands.add_parser(name)
        command.add_argument("run_id")
        command.add_argument("--gate", required=True)
        command.add_argument("--operator", default="local_operator")
        command.add_argument("--reason", required=True)
        command.add_argument("--clarification", default="")
    show = commands.add_parser("show")
    show.add_argument("run_id")
    revise = commands.add_parser("revise")
    revise.add_argument("run_id")
    revise.add_argument("--stage", choices=["requirements", "architecture"], required=True)
    revise.add_argument("--value", required=True)
    revise.add_argument("--reason", required=True)
    revise.add_argument("--operator", default="local_operator")
    commands.add_parser("metrics")
    args = parser.parse_args(argv)
    service = WorkflowService()
    try:
        if args.command == "start":
            result = service.start(args.scenario, args.offline, args.requirement, args.fault_mode)
        elif args.command in {"approve", "reject"}:
            result = service.resume(
                args.run_id,
                args.command == "approve",
                args.operator,
                args.reason,
                args.clarification,
                args.gate,
            )
        elif args.command == "show":
            state, pending = service.state(args.run_id)
            result = {
                "run": service.store.public_run(args.run_id),
                "pending": pending,
                "decisions": state.get("decisions", []),
                "lineage": state.get("lineage", {}),
            }
        elif args.command == "revise":
            result = service.revise(args.run_id, args.stage, args.value, args.operator, args.reason)
        else:
            result = service.store.metrics()
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
