from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequirementsArtifact(Artifact):
    functional: list[str] = Field(min_length=1)
    nonfunctional: list[str] = Field(min_length=1)
    assumptions: list[str]
    open_questions: list[str]
    acceptance_criteria: list[str] = Field(min_length=1)
    risk_level: Literal["low", "medium", "high"]
    needs_clarification: bool


class Task(Artifact):
    id: str
    description: str
    dependencies: list[str]
    status: Literal["pending", "completed"] = "pending"
    owner: str
    required_inputs: list[str]
    expected_outputs: list[str]
    acceptance_criteria: list[str]
    risk_level: Literal["low", "medium", "high"]


class PlanArtifact(Artifact):
    tasks: list[Task] = Field(min_length=1)
    rationale: str


class ArchitectureArtifact(Artifact):
    components: list[str]
    affected_files: list[str]
    decisions: list[str]
    risks: list[str]
    mermaid: str
    reviewed_source_hashes: dict[str, str]


class GeneratedFile(Artifact):
    path: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=30000)


class Operation(Artifact):
    kind: Literal["bootstrap_reference", "implement_expiration", "set_creation_limit", "generate_files"]
    value: int | None = Field(default=None, ge=1, le=1000)
    rationale: str
    files: list[GeneratedFile] = Field(default_factory=list, max_length=12)


class ChangeProposal(Artifact):
    operations: list[Operation] = Field(min_length=1, max_length=3)
    requirement_ids: list[str] = Field(min_length=1)
    decision_ids: list[str]
    summary: str


class TestDesignArtifact(Artifact):
    cases: list[str] = Field(min_length=1)
    acceptance_checks: list[str] = Field(min_length=1)
    command_key: Literal["pytest_workspace", "static_generated"]


class DocumentationArtifact(Artifact):
    summary: str
    rationale: str
    assumptions: list[str]
    risks: list[str]
    limitations: list[str]
    markdown: str


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    return {**(left or {}), **(right or {})}


class WorkflowState(TypedDict, total=False):
    run_id: str
    scenario: str
    mode: str
    requirement: str
    custom_generation: bool
    clarification: str
    architecture_hint: str
    revision: int
    started_at: str
    finished_at: str
    duration_ms: float
    status: str
    workspace: str
    current_stage: str
    artifacts: Annotated[dict[str, Any], merge_dicts]
    lineage: Annotated[dict[str, Any], merge_dicts]
    tasks: list[dict]
    decisions: Annotated[list[dict], operator.add]
    trace: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]
    usage: Annotated[list[dict], operator.add]
    approvals: Annotated[dict[str, dict], merge_dicts]
    validation: dict
    changed_files: list[str]
    repair_count: int
    rollback_done: bool
    snapshot_ready: bool
    stop_reason: str
    fault_mode: str
    branch_nonce: str
    reanalysis: bool
