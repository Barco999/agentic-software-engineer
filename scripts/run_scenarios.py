"""Run real offline fixture workflows, tests, and source changes; export their evidence."""

import argparse
import json
import shutil
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestration.service import WorkflowService
from scenarios import DEMO_CLARIFICATION, SCENARIOS


def demonstrate(service, scenario):
    result = service.start(
        scenario, offline=True, fault_mode="fail_once" if scenario == "brownfield" else ""
    )
    while result["pending"]:
        result = service.resume(
            result["run"]["run_id"],
            True,
            "deterministic_demo_fixture",
            "Scripted fixture approval for offline demonstration; not a human production approval",
            DEMO_CLARIFICATION,
            expected_gate=result["pending"]["gate"],
        )
    return result


def export(service, result, target):
    run_id = result["run"]["run_id"]
    source = service.settings.agent_data_dir / "runs" / run_id
    if target.exists():
        # Preserve prior generated evidence instead of mixing stale artifacts
        # into a new run or deleting the older trace.
        history = (
            service.settings.agent_data_dir / "export-history" / f"{target.name}-{uuid.uuid4().hex}"
        )
        history.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(history))
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / "evidence.json", target / "evidence.json")
    for revision in sorted(source.glob("r*")):
        if revision.is_dir():
            shutil.copytree(revision, target / revision.name, dirs_exist_ok=True)
    state, _ = service.state(run_id)
    if state["scenario"] == "brownfield":
        before = source / "snapshots" / f"r{state['revision']}" / "files/app/expiration.py"
        shutil.copyfile(before, target / "expiration-before.py")
        shutil.copyfile(
            Path(state["workspace"]) / "app/expiration.py", target / "expiration-after.py"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--offline",
        action="store_true",
        required=True,
        help="Required: demo approvals are fixtures, never automatic live approvals",
    )
    parser.add_argument("--output", default="evidence/scenarios")
    args = parser.parse_args()
    service = WorkflowService()
    summaries = []
    for scenario in SCENARIOS:
        result = demonstrate(service, scenario)
        export(service, result, Path(args.output) / scenario)
        summaries.append(result["run"])
        if result["run"]["status"] != "completed":
            raise SystemExit(json.dumps(result, indent=2))
    report = {
        "mode": "offline-deterministic",
        "runs": summaries,
        "metrics": service.store.metrics(),
    }
    summary_path = Path(args.output).parent / "scenario-summary.json"
    summary_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "runs": [
                    {
                        key: run[key]
                        for key in (
                            "scenario",
                            "run_id",
                            "status",
                            "revision",
                            "repair_count",
                            "validation",
                        )
                    }
                    for run in summaries
                ],
                "summary": str(summary_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
