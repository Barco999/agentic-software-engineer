from __future__ import annotations

import json
import re
import uuid
from functools import wraps
from pathlib import Path

from filelock import FileLock, Timeout
from langgraph.types import Command, Overwrite

from agents.roles import inspect_repository
from app.config import PROJECT_ROOT, Settings, load_settings
from orchestration.audit import AgentStore, redact, utc_iso
from orchestration.gates import descendants
from orchestration.graph import GraphRuntime
from orchestration.tools import prepare_workspace
from scenarios import SCENARIOS


def config(run_id):
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise ValueError("Invalid workflow ID")
    return {"configurable": {"thread_id": run_id}, "recursion_limit": 100}


def pending_interrupt(snapshot):
    for task in snapshot.tasks:
        for item in task.interrupts:
            return item.value
    return None


def exclusive_run(method):
    @wraps(method)
    def wrapped(self, run_id, *args, **kwargs):
        config(run_id)
        try:
            with self.run_lock(run_id):
                return method(self, run_id, *args, **kwargs)
        except Timeout as exc:
            raise ValueError(
                "Workflow is already executing; retry after the current operator action"
            ) from exc

    return wrapped


class WorkflowService:
    def __init__(
        self, settings: Settings | None = None, reference: Path = PROJECT_ROOT, client=None
    ):
        self.settings = settings or load_settings()
        self.reference = reference.resolve()
        self.store = AgentStore(self.settings.agent_data_dir)
        self.client = client

    def runtime(self, offline):
        return GraphRuntime(self.settings, self.reference, offline, client=self.client)

    def run_lock(self, run_id):
        root = self.settings.agent_data_dir / "locks"
        root.mkdir(parents=True, exist_ok=True)
        return FileLock(root / f"{run_id}.lock", timeout=0)

    def _drive(self, runtime, run_id, value):
        cfg = config(run_id)
        try:
            runtime.graph.invoke(value, cfg)
        except Exception as exc:
            # Unexpected tool/infrastructure failures also fail closed and restore snapshots.
            snapshot = runtime.graph.get_state(cfg)
            runtime.graph.update_state(
                cfg,
                {"errors": [type(exc).__name__ + ": controlled tool failure"]},
                as_node="validation",
            )
            runtime.graph.invoke(None, cfg)
        snapshot = runtime.graph.get_state(cfg)
        state = dict(snapshot.values)
        pending = pending_interrupt(snapshot)
        status = "awaiting_approval" if pending else state.get("status", "running")
        self.store.save_run(state, status, pending["gate"] if pending else None)
        if pending:
            self.store.record(
                run_id,
                state["revision"],
                pending["gate"],
                "approval_requested",
                "paused",
                review_hash=pending["review_hash"],
            )
        self._export(state, pending)
        return {"run": self.store.public_run(run_id), "pending": pending}

    def _export(self, state, pending):
        root = self.settings.agent_data_dir / "runs" / state["run_id"]
        root.mkdir(parents=True, exist_ok=True)
        summary = {
            "run": self.store.public_run(state["run_id"]),
            "pending": pending,
            "decisions": state.get("decisions", []),
            "lineage": state.get("lineage", {}),
            "trace": self.store.audit_events(state["run_id"]),
            "final_report": state.get("artifacts", {}).get("final_report"),
        }
        (root / "evidence.json").write_text(json.dumps(redact(summary), indent=2), encoding="utf-8")

    def start(
        self,
        scenario: str,
        offline: bool = False,
        requirement: str | None = None,
        fault_mode: str = "",
    ):
        if scenario not in SCENARIOS:
            raise ValueError("Unknown scenario")
        custom_generation = bool(requirement and requirement.strip() != SCENARIOS[scenario]) and scenario == "greenfield" and not offline
        requirement = requirement or SCENARIOS[scenario]
        if not requirement.strip() or len(requirement) > 8000 or redact(requirement) != requirement:
            raise ValueError(
                "Requirement is empty, oversized, or appears to contain sensitive data"
            )
        actual_offline = (
            offline or self.settings.demo_mode or self.settings.llm_provider == "offline"
        )
        if fault_mode and (not actual_offline or scenario != "brownfield"):
            raise ValueError(
                "Trusted fault injection is allowed only for offline brownfield demonstrations"
            )
        run_id = uuid.uuid4().hex
        workspace = self.settings.agent_data_dir / "runs" / run_id / "workspace"
        prepare_workspace(scenario, workspace, self.reference)
        state = {
            "run_id": run_id,
            "scenario": scenario,
            "mode": "offline-deterministic"
            if actual_offline
            else "live-" + self.settings.llm_provider,
            "requirement": requirement,
            "custom_generation": custom_generation and not actual_offline,
            "clarification": "",
            "architecture_hint": "",
            "revision": 1,
            "started_at": utc_iso(),
            "status": "running",
            "workspace": str(workspace),
            "artifacts": {},
            "lineage": {},
            "tasks": [],
            "decisions": [],
            "trace": [],
            "errors": [],
            "usage": [],
            "approvals": {},
            "validation": {},
            "changed_files": [],
            "repair_count": 0,
            "rollback_done": False,
            "snapshot_ready": False,
            "fault_mode": fault_mode,
        }
        self.store.save_run(state)
        self.store.record(
            run_id,
            1,
            "control_plane",
            "workflow_started",
            "running",
            mode=state["mode"],
            scenario=scenario,
        )
        with self.run_lock(run_id), self.runtime(actual_offline) as runtime:
            return self._drive(runtime, run_id, state)

    def _existing(self, run_id):
        config(run_id)
        run = self.store.public_run(run_id)
        if run is None:
            raise ValueError("Workflow run does not exist")
        return run

    @exclusive_run
    def resume(
        self,
        run_id: str,
        approved: bool,
        operator: str,
        reason: str,
        clarification: str = "",
        expected_gate: str | None = None,
    ):
        run = self._existing(run_id)
        if (
            not operator.strip()
            or not reason.strip()
            or redact(operator) != operator
            or redact(reason) != reason
        ):
            raise ValueError("Approval requires a nonsensitive operator and reason")
        with self.runtime(run["mode"] == "offline-deterministic") as runtime:
            snapshot = runtime.graph.get_state(config(run_id))
            pending = pending_interrupt(snapshot)
            if pending is None:
                raise ValueError("Workflow is not paused at an approval gate")
            if expected_gate and expected_gate != pending["gate"]:
                raise ValueError("Approval gate changed; inspect the current request")
            response = {
                "approved": approved,
                "operator": operator,
                "reason": reason,
                "review_hash": pending["review_hash"],
                "clarification": clarification,
            }
            return self._drive(runtime, run_id, Command(resume=response))

    def state(self, run_id):
        run = self._existing(run_id)
        with self.runtime(run["mode"] == "offline-deterministic") as runtime:
            snapshot = runtime.graph.get_state(config(run_id))
            return dict(snapshot.values), pending_interrupt(snapshot)

    @exclusive_run
    def revise(self, run_id: str, stage: str, new_value: str, operator: str, reason: str):
        run = self._existing(run_id)
        if (
            stage not in {"requirements", "architecture"}
            or not new_value.strip()
            or redact(new_value) != new_value
        ):
            raise ValueError(
                "Revision must name requirements/architecture and supply nonsensitive new input"
            )
        with self.runtime(run["mode"] == "offline-deterministic") as runtime:
            cfg = config(run_id)
            state = dict(runtime.graph.get_state(cfg).values)
            sources = {"REQ"} if stage == "requirements" else {"ARCH"}
            affected = descendants(state["tasks"], sources)
            keep = {"inspection"} | (
                {"requirements", "planning"} if stage == "architecture" else set()
            )
            preserved = {key: value for key, value in state["artifacts"].items() if key in keep}
            # Existing source may have changed since the initial run; re-inspect
            # current bytes while preserving unaffected requirement/plan artifacts.
            preserved["inspection"] = inspect_repository(Path(state["workspace"]))
            tasks = [
                {**task, "status": "pending" if task["id"] in affected else task["status"]}
                for task in state["tasks"]
            ]
            revision = state["revision"] + 1
            decision = {
                "id": uuid.uuid4().hex,
                "gate": "revision",
                "operator": operator,
                "reason": reason,
                "revision": revision,
                "affected_tasks": sorted(affected),
            }
            self.store.record(
                run_id,
                revision,
                "control_plane",
                "replan",
                "passed",
                affected_tasks=sorted(affected),
                preserved_artifacts=sorted(preserved),
            )
            updates = {
                "revision": revision,
                "status": "running",
                "errors": Overwrite([]),
                "artifacts": Overwrite(preserved),
                "lineage": Overwrite(
                    {key: value for key, value in state.get("lineage", {}).items() if key in keep}
                ),
                "approvals": Overwrite({}),
                "tasks": tasks,
                "decisions": [decision],
                "validation": {},
                "snapshot_ready": False,
                "rollback_done": False,
                "repair_count": 0,
                "changed_files": [],
                "finished_at": "",
                "stop_reason": "",
            }
            if stage == "requirements":
                updates.update({"requirement": new_value, "clarification": ""})
                resume_after = "inspection"
            else:
                updates["architecture_hint"] = new_value
                resume_after = "planning"
            runtime.graph.update_state(cfg, updates, as_node=resume_after)
            return self._drive(runtime, run_id, None)
