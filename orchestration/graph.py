from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agents.roles import AgentSuite, inspect_repository
from agents.testing import run_trusted_pytest
from app.config import Settings
from llm.provider import LLMClient
from orchestration.audit import AgentStore, redact, utc_iso
from orchestration.gates import complete_task, validate_dependencies
from orchestration.policies import PolicyViolation, WorkspacePolicy, content_hash, validate_proposal
from orchestration.rollback import SnapshotManager
from orchestration.state import (
    ArchitectureArtifact,
    ChangeProposal,
    DocumentationArtifact,
    PlanArtifact,
    RequirementsArtifact,
    TestDesignArtifact,
    WorkflowState,
)
from orchestration.tools import apply_proposal


class GraphRuntime:
    """One local orchestration worker. SQLite checkpoints survive process restarts."""

    def __init__(self, settings: Settings, reference: Path, offline: bool, client=None):
        self.settings = settings
        self.reference = reference.resolve()
        self.store = AgentStore(settings.agent_data_dir)
        self.connection = sqlite3.connect(
            settings.agent_data_dir / "checkpoints.db", check_same_thread=False
        )
        self.connection.execute("PRAGMA busy_timeout=15000")
        self.checkpointer = SqliteSaver(self.connection)

        def retry_audit(attempt, code, context):
            self.store.record(
                context["run_id"],
                context["revision"],
                context["role"],
                "provider_retry",
                "retrying",
                retry_count=attempt,
                failure_code=code,
            )

        self.suite = AgentSuite(
            client or LLMClient(settings, offline=offline, on_retry=retry_audit)
        )
        self.graph = self._build()

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _record(self, state, agent, action, status, duration_ms=0, **details):
        return self.store.record(
            state["run_id"],
            state["revision"],
            agent,
            action,
            status,
            duration_ms=duration_ms,
            retry_count=state.get("repair_count", 0),
            **details,
        )

    def _artifact(self, state, role, artifact):
        directory = (
            self.settings.agent_data_dir
            / "runs"
            / state["run_id"]
            / f"r{state['revision']}"
            / "artifacts"
        )
        directory.mkdir(parents=True, exist_ok=True)
        envelope = {
            "mode": state["mode"],
            "revision": state["revision"],
            "agent": role,
            "artifact_sha256": content_hash(artifact),
            "artifact": artifact,
        }
        (directory / f"{role}.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")

    def _error(self, state, role, exc):
        # External error bodies and prompts are intentionally not exposed.
        reason = getattr(exc, "code", None) or type(exc).__name__ + ": " + str(exc)
        reason = redact(reason)
        event = self._record(state, role, "stage_exit", "failed", reason=reason)
        return {"errors": [reason], "trace": [event]}

    def _role(self, state, role, schema, needs):
        started = time.monotonic()
        entered = self._record(
            state, role, "stage_entry", "running", required_artifacts=list(needs)
        )
        try:
            if any(key not in state.get("artifacts", {}) for key in needs):
                raise PolicyViolation("Stage precondition: missing required artifact")
            artifact, usage = self.suite.run(role, schema, state)
            if redact(artifact) != artifact:
                raise PolicyViolation("Output contains a secret or private path")
            if role == "planning":
                validate_dependencies(artifact["tasks"])
                for task in artifact["tasks"]:
                    task["status"] = "completed" if task["id"] == "REQ" else "pending"
            if role == "architecture":
                actual = state["artifacts"]["inspection"]["hashes"]
                if any(
                    actual.get(path) != digest
                    for path, digest in artifact["reviewed_source_hashes"].items()
                ):
                    raise PolicyViolation("Architecture invented a repository finding")
                if (
                    state["scenario"] == "brownfield"
                    and "app/expiration.py" not in artifact["reviewed_source_hashes"]
                ):
                    raise PolicyViolation(
                        "Brownfield impact analysis must inspect app/expiration.py"
                    )
            if role in {"implementation_plan", "repair"}:
                validate_proposal(state["scenario"], artifact, custom_generation=state.get("custom_generation", False))
                if not set(artifact["requirement_ids"]).issubset({t["id"] for t in state["tasks"]}):
                    raise PolicyViolation("Change references an unknown requirement/task")
                if not set(artifact["decision_ids"]).issubset(
                    {d["id"] for d in state["decisions"]}
                ):
                    raise PolicyViolation("Change references an unknown decision")
            self._artifact(state, role, artifact)
            exited = self._record(
                state,
                role,
                "stage_exit",
                "passed",
                (time.monotonic() - started) * 1000,
                artifact_sha256=content_hash(artifact),
                provider=usage["provider"],
            )
            update = {
                "artifacts": {role: artifact},
                "usage": [{"role": role, **usage}],
                "lineage": {
                    role: {
                        "revision": state["revision"],
                        "input_hashes": {
                            key: content_hash(state["artifacts"][key]) for key in needs
                        },
                        "output_hash": content_hash(artifact),
                    }
                },
                "trace": [entered, exited],
            }
            if role not in {"implementation_plan", "test_design"}:
                update["current_stage"] = role
            return update
        except Exception as exc:
            return self._error(state, role, exc)

    def inspect(self, state):
        try:
            artifact = inspect_repository(Path(state["workspace"]))
            self._artifact(state, "inspection", artifact)
            event = self._record(
                state,
                "inspection",
                "repository_inspected",
                "passed",
                files=artifact["files"],
                source_hashes=artifact["hashes"],
            )
            return {
                "artifacts": {"inspection": artifact},
                "trace": [event],
                "current_stage": "inspection",
            }
        except Exception as exc:
            return self._error(state, "inspection", exc)

    def requirements(self, state):
        update = self._role(state, "requirements", RequirementsArtifact, ("inspection",))
        update["reanalysis"] = False
        return update

    def requirements_gate(self, state):
        if state["artifacts"]["requirements"]["needs_clarification"] and not state.get(
            "clarification"
        ):
            request = {
                "gate": "clarification",
                "questions": state["artifacts"]["requirements"]["open_questions"],
                "review_hash": content_hash(state["artifacts"]["requirements"]),
                "revision": state["revision"],
                "instruction": "Clarify scope or reject; no code changes have run",
            }
            response = interrupt(request)
            if not isinstance(response, dict) or response.get("approved") is not True:
                return {"status": "rejected", "errors": ["clarification_rejected"]}
            text = response.get("clarification", "").strip()
            if not text or len(text) > 4000 or redact(text) != text:
                return {"errors": ["invalid_or_sensitive_clarification"]}
            decision = {
                "id": uuid.uuid4().hex,
                "gate": "clarification",
                "approved": True,
                "operator": response["operator"],
                "revision": state["revision"],
                "review_hash": request["review_hash"],
                "reason": response["reason"],
            }
            event = self._record(
                state,
                "requirements_gate",
                "replan",
                "passed",
                source="clarification",
                invalidated=["requirements"],
                preserved=["inspection"],
            )
            return {
                "clarification": text,
                "revision": state["revision"] + 1,
                "reanalysis": True,
                "decisions": [decision],
                "trace": [event],
            }
        return {"current_stage": "requirements_gate"}

    def planning(self, state):
        update = self._role(state, "planning", PlanArtifact, ("requirements",))
        if "artifacts" in update:
            update["tasks"] = update["artifacts"]["planning"]["tasks"]
        return update

    def architecture(self, state):
        update = self._role(
            state, "architecture", ArchitectureArtifact, ("requirements", "planning", "inspection")
        )
        if "artifacts" in update:
            update["tasks"] = complete_task(state["tasks"], "ARCH")
        return update

    def _review_hash(self, state, gate):
        keys = {
            "architecture": ["architecture", "requirements", "planning"],
            "implementation": ["implementation_plan", "test_design"],
            "repair": ["repair", "validation"],
            "release": ["release_readiness", "documentation", "validation"],
        }[gate]
        values = {key: state.get("artifacts", {}).get(key, state.get(key)) for key in keys}
        values["source_hashes"] = inspect_repository(Path(state["workspace"]))["hashes"]
        import hashlib

        policy = WorkspacePolicy(Path(state["workspace"]))
        values["test_hashes"] = {
            path.relative_to(policy.workspace).as_posix(): hashlib.sha256(
                policy.path(path.relative_to(policy.workspace).as_posix()).read_bytes()
            ).hexdigest()
            for path in (policy.workspace / "tests").glob("**/*.py")
        }
        values["revision"] = state["revision"]
        return content_hash(values)

    def _approval(self, state, gate):
        review_hash = self._review_hash(state, gate)
        response = interrupt(
            {
                "gate": gate,
                "review_hash": review_hash,
                "revision": state["revision"],
                "instruction": "Approve or reject the current artifact and workspace hash",
                "summary": f"{gate} checkpoint for {state['scenario']}",
                "artifact_names": sorted(state["artifacts"]),
            }
        )
        approved = (
            isinstance(response, dict)
            and response.get("approved") is True
            and response.get("review_hash") == review_hash
        )
        decision = {
            "id": uuid.uuid4().hex,
            "gate": gate,
            "approved": approved,
            "operator": response.get("operator", "unknown")
            if isinstance(response, dict)
            else "unknown",
            "reason": response.get("reason", "") if isinstance(response, dict) else "",
            "review_hash": review_hash,
            "revision": state["revision"],
        }
        event = self._record(
            state,
            gate,
            "approval_decision",
            "approved" if approved else "rejected",
            operator=decision["operator"],
            reason=decision["reason"],
            review_hash=review_hash,
        )
        update = {"approvals": {gate: decision}, "decisions": [decision], "trace": [event]}
        if not approved:
            update.update({"status": "rejected", "errors": [f"{gate}_approval_rejected_or_stale"]})
        return update

    def architecture_approval(self, state):
        return self._approval(state, "architecture")

    def implementation_plan(self, state):
        return self._role(
            state,
            "implementation_plan",
            ChangeProposal,
            ("requirements", "architecture", "planning"),
        )

    def test_design(self, state):
        return self._role(
            state, "test_design", TestDesignArtifact, ("requirements", "architecture")
        )

    def synchronize(self, state):
        if state.get("errors"):
            return {}
        for name in ("implementation_plan", "test_design"):
            if (
                name not in state["artifacts"]
                or state["lineage"][name]["revision"] != state["revision"]
            ):
                return {"errors": ["synchronization_gate_missing_or_stale_branch"]}
        event = self._record(
            state,
            "synchronization",
            "fan_in",
            "passed",
            branches=["implementation_plan", "test_design"],
            branch_hashes={
                name: content_hash(state["artifacts"][name])
                for name in ("implementation_plan", "test_design")
            },
        )
        return {"trace": [event], "current_stage": "synchronization"}

    def implementation_approval(self, state):
        return self._approval(state, "implementation")

    def _snapshot(self, state):
        return SnapshotManager(
            Path(state["workspace"]),
            self.settings.agent_data_dir
            / "runs"
            / state["run_id"]
            / "snapshots"
            / f"r{state['revision']}",
        )

    def _apply(self, state, repair=False):
        gate, proposal_key = (
            ("repair", "repair") if repair else ("implementation", "implementation_plan")
        )
        try:
            approval = state["approvals"].get(gate)
            if (
                not approval
                or not approval["approved"]
                or approval["review_hash"] != self._review_hash(state, gate)
            ):
                raise PolicyViolation("Implementation approval is missing or stale")
            self._snapshot(state).create()
            ledger = apply_proposal(
                state["scenario"],
                Path(state["workspace"]),
                self.reference,
                state["artifacts"][proposal_key],
                state.get("fault_mode", ""),
                state.get("repair_count", 0),
                custom_generation=state.get("custom_generation", False),
            )
            prior = {entry["path"]: entry for entry in state["artifacts"].get("changes", [])}
            for entry in ledger:
                prior[entry["path"]] = {
                    **entry,
                    "requirement_revision": state["revision"],
                    "approval_id": approval["id"],
                    "requirement_ids": state["artifacts"][proposal_key]["requirement_ids"],
                    "proposal_hash": content_hash(state["artifacts"][proposal_key]),
                }
            changes = list(prior.values())
            event = self._record(
                state,
                "implementation",
                "repair_applied" if repair else "changes_applied",
                "passed",
                files=[entry["path"] for entry in ledger],
                approval_id=approval["id"],
                proposal_sha256=content_hash(state["artifacts"][proposal_key]),
            )
            self._artifact(state, "changes", changes)
            return {
                "artifacts": {"changes": changes},
                "changed_files": sorted(prior),
                "snapshot_ready": True,
                "tasks": complete_task(state["tasks"], "CODE"),
                "trace": [event],
                "current_stage": "implementation",
            }
        except Exception as exc:
            # Snapshot can exist even if a write failed halfway through.
            update = self._error(state, "implementation", exc)
            update["snapshot_ready"] = self._snapshot(state).manifest.exists()
            return update

    def implementation(self, state):
        return self._apply(state)

    def validation(self, state):
        try:
            self._verify_executables(state)
            expected_command = "static_generated" if state.get("custom_generation") else "pytest_workspace"
            if state["artifacts"]["test_design"]["command_key"] != expected_command:
                raise PolicyViolation("Test command is not allowlisted")
            report_dir = (
                self.settings.agent_data_dir
                / "runs"
                / state["run_id"]
                / f"r{state['revision']}"
                / f"validation-{state.get('repair_count', 0)}"
            )
            if state.get("custom_generation"):
                # No sandbox is available: generated Python must NEVER be executed
                # by the trusted regression runner.
                from agents.testing import inspect_generated_sources
                report = inspect_generated_sources(Path(state["workspace"]), report_dir)
            else:
                report = run_trusted_pytest(
                    Path(state["workspace"]), report_dir, self.settings.agent_timeout_seconds
                )
            event = self._record(
                state,
                "testing",
                "pytest",
                "passed" if report["success"] else "failed",
                report["duration_ms"],
                passed=report["passed"],
                failed=report["failed"],
                errors=report["errors"],
                return_code=report["return_code"],
            )
            self._artifact(state, f"validation-{state.get('repair_count', 0)}", report)
            update = {
                "validation": report,
                "artifacts": {"validation": report},
                "trace": [event],
                "current_stage": "validation",
            }
            if report["success"]:
                update["tasks"] = complete_task(state["tasks"], "TEST")
            return update
        except Exception as exc:
            return self._error(state, "testing", exc)

    def _verify_executables(self, state):
        """Execute only unchanged trusted baseline or compiler-hashed source/tests."""
        import hashlib

        snapshot = self._snapshot(state)
        baseline = set(json.loads(snapshot.manifest.read_text(encoding="utf-8")))
        changes = {entry["path"]: entry["sha256"] for entry in state["artifacts"]["changes"]}
        policy = WorkspacePolicy(Path(state["workspace"]))
        required = {path for path in baseline | set(changes) if path.endswith(".py")}
        current = {
            path.relative_to(policy.workspace).as_posix() for path in policy.workspace.rglob("*.py")
        }
        if current - required:
            raise PolicyViolation("Untrusted executable file appeared in the workspace")
        if required - current:
            raise PolicyViolation("Trusted executable file was removed from the workspace")
        for path in policy.workspace.rglob("*.py"):
            relative = path.relative_to(policy.workspace).as_posix()
            actual = hashlib.sha256(policy.path(relative).read_bytes()).hexdigest()
            if relative in changes:
                expected = changes[relative]
            elif relative in baseline:
                expected = hashlib.sha256(
                    (snapshot.root / "files" / relative).read_bytes()
                ).hexdigest()
            else:
                raise PolicyViolation("Untrusted executable file appeared in the workspace")
            if actual != expected:
                raise PolicyViolation(
                    "Trusted executable source changed outside approved operations"
                )

    def repair(self, state):
        update = self._role(
            state, "repair", ChangeProposal, ("requirements", "architecture", "validation")
        )
        update["repair_count"] = state.get("repair_count", 0) + 1
        return update

    def repair_approval(self, state):
        return self._approval(state, "repair")

    def apply_repair(self, state):
        return self._apply(state, repair=True)

    def documentation(self, state):
        update = self._role(
            state,
            "documentation",
            DocumentationArtifact,
            ("requirements", "architecture", "changes", "validation"),
        )
        if "artifacts" in update:
            markdown = update["artifacts"]["documentation"]["markdown"]
            WorkspacePolicy(Path(state["workspace"])).write("docs/generated-summary.md", markdown)
            update["changed_files"] = sorted(
                set(state["changed_files"]) | {"docs/generated-summary.md"}
            )
            update["tasks"] = complete_task(state["tasks"], "DOCS")
        return update

    def release_readiness(self, state):
        try:
            if not state["validation"].get("success") or state.get("errors"):
                raise PolicyViolation("Release exit gate requires successful validation")
            policy = WorkspacePolicy(Path(state["workspace"]))
            for entry in state["artifacts"]["changes"]:
                import hashlib

                if (
                    hashlib.sha256(policy.path(entry["path"]).read_bytes()).hexdigest()
                    != entry["sha256"]
                ):
                    raise PolicyViolation("Validated code changed after testing")
            artifact = {
                "ready": True,
                "validation_hash": content_hash(state["validation"]),
                "changed_files": state["changed_files"],
                "revision": state["revision"],
                "deployment_performed": False,
                "mode": state["mode"],
            }
            self._artifact(state, "release_readiness", artifact)
            event = self._record(
                state,
                "release_readiness",
                "exit_gate",
                "passed",
                validation_hash=artifact["validation_hash"],
            )
            return {"artifacts": {"release_readiness": artifact}, "trace": [event]}
        except Exception as exc:
            return self._error(state, "release_readiness", exc)

    def release_approval(self, state):
        return self._approval(state, "release")

    def finalize(self, state):
        if state["approvals"]["release"]["review_hash"] != self._review_hash(state, "release"):
            return {"errors": ["release_approval_stale"]}
        finished = utc_iso()
        duration = (
            datetime.fromisoformat(finished) - datetime.fromisoformat(state["started_at"])
        ).total_seconds() * 1000
        report = {
            "outcome": "completed",
            "mode": state["mode"],
            "scenario": state["scenario"],
            "revision": state["revision"],
            "repair_attempts": state.get("repair_count", 0),
            "changed_files": state["changed_files"],
            "tests": {
                k: state["validation"][k] for k in ("passed", "failed", "skipped", "return_code")
            },
            "assumptions": state["artifacts"]["requirements"]["assumptions"],
            "risks": state["artifacts"]["architecture"]["risks"],
            "limitations": state["artifacts"]["documentation"]["limitations"],
            "decisions": state["decisions"],
            "deployment_performed": False,
        }
        self._artifact(state, "final_report", report)
        event = self._record(state, "finalize", "workflow_finished", "completed", duration)
        return {
            "status": "completed",
            "finished_at": finished,
            "duration_ms": duration,
            "tasks": complete_task(state["tasks"], "RELEASE"),
            "artifacts": {"final_report": report},
            "trace": [event],
        }

    def rollback(self, state):
        if state.get("snapshot_ready") and not state.get("rollback_done"):
            restored = self._snapshot(state).restore()
            event = self._record(state, "rollback", "rollback", "passed", restored_files=restored)
            return {"rollback_done": True, "trace": [event]}
        return {}

    def safe_stop(self, state):
        finished = utc_iso()
        status = "rejected" if state.get("status") == "rejected" else "safe_stopped"
        reason = "; ".join(state.get("errors", [])) or "validation_retry_limit_exhausted"
        duration = (
            datetime.fromisoformat(finished) - datetime.fromisoformat(state["started_at"])
        ).total_seconds() * 1000
        event = self._record(
            state,
            "safe_stop",
            "workflow_finished",
            status,
            duration,
            reason=reason,
            deployment_performed=False,
        )
        artifact = {
            "outcome": status,
            "reason": reason,
            "rollback_done": state.get("rollback_done", False),
            "mode": state["mode"],
            "validation": state.get("validation", {}),
        }
        self._artifact(state, "final_report", artifact)
        return {
            "status": status,
            "stop_reason": reason,
            "finished_at": finished,
            "duration_ms": duration,
            "artifacts": {"final_report": artifact},
            "trace": [event],
        }

    @staticmethod
    def route(state, destination):
        return (
            "rollback" if state.get("errors") or state.get("status") == "rejected" else destination
        )

    def _build(self):
        graph = StateGraph(WorkflowState)
        nodes = {
            "inspection": self.inspect,
            "requirements": self.requirements,
            "requirements_gate": self.requirements_gate,
            "planning": self.planning,
            "architecture": self.architecture,
            "architecture_approval": self.architecture_approval,
            "implementation_plan": self.implementation_plan,
            "test_design": self.test_design,
            "synchronize": self.synchronize,
            "implementation_approval": self.implementation_approval,
            "implementation": self.implementation,
            "validation": self.validation,
            "repair": self.repair,
            "repair_approval": self.repair_approval,
            "apply_repair": self.apply_repair,
            "documentation": self.documentation,
            "release_readiness": self.release_readiness,
            "release_approval": self.release_approval,
            "finalize": self.finalize,
            "rollback": self.rollback,
            "safe_stop": self.safe_stop,
        }
        for name, function in nodes.items():
            graph.add_node(name, function)
        graph.add_edge(START, "inspection")
        sequential = {
            "inspection": "requirements",
            "requirements": "requirements_gate",
            "planning": "architecture",
            "architecture": "architecture_approval",
            "synchronize": "implementation_approval",
            "implementation_approval": "implementation",
            "implementation": "validation",
            "repair": "repair_approval",
            "repair_approval": "apply_repair",
            "apply_repair": "validation",
            "documentation": "release_readiness",
            "release_readiness": "release_approval",
            "release_approval": "finalize",
        }
        for source, target in sequential.items():
            graph.add_conditional_edges(
                source, lambda state, t=target: self.route(state, t), [target, "rollback"]
            )
        graph.add_conditional_edges(
            "requirements_gate",
            lambda state: self.route(
                state, "requirements" if state.get("reanalysis") else "planning"
            ),
            ["requirements", "planning", "rollback"],
        )
        graph.add_conditional_edges(
            "architecture_approval",
            lambda state: (
                "rollback" if state.get("errors") else ["implementation_plan", "test_design"]
            ),
            ["rollback", "implementation_plan", "test_design"],
        )
        graph.add_edge(["implementation_plan", "test_design"], "synchronize")
        graph.add_conditional_edges(
            "validation",
            lambda state: (
                "rollback"
                if state.get("errors")
                else "documentation"
                if state.get("validation", {}).get("success")
                else "repair"
                if state.get("repair_count", 0) < self.settings.max_agent_retries
                else "rollback"
            ),
            ["documentation", "repair", "rollback"],
        )
        graph.add_conditional_edges(
            "finalize", lambda state: self.route(state, END), [END, "rollback"]
        )
        graph.add_edge("rollback", "safe_stop")
        graph.add_edge("safe_stop", END)
        return graph.compile(checkpointer=self.checkpointer)
