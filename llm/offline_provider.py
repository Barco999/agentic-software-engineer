"""Honest fixture provider: no inference, no invented test or source-generation claims."""

import re
import time


class OfflineProvider:
    name = "offline-deterministic"

    def generate(self, role: str, schema: dict, context: dict):
        scenario = context["scenario"]
        artifacts = context.get("artifacts", {})
        requirements = context.get("requirement", "")
        clarification = context.get("clarification", "")
        # A short observable interval helps tests establish genuine fan-out overlap.
        if role in {"implementation_plan", "test_design"}:
            time.sleep(0.03)
        if role == "requirements":
            ambiguous = scenario == "ambiguous" and not clarification
            result = {
                "functional": [requirements] + ([clarification] if clarification else []),
                "nonfunctional": [
                    "No private redirect targets",
                    "Bound collisions and retries",
                    "Persist UTC analytics",
                ],
                "assumptions": [
                    "Aggregate click counts only; no visitor identifiers",
                    "No automatic deployment",
                ],
                "open_questions": [
                    "What measurable security controls are in scope?",
                    "What request rate and expiry policy should apply?",
                ]
                if ambiguous
                else [],
                "acceptance_criteria": [
                    "Valid destinations create unique links",
                    "Redirects record one click",
                    "Expired links return 410",
                    "Unsafe targets are rejected",
                ],
                "risk_level": "high" if scenario == "ambiguous" else "medium",
                "needs_clarification": ambiguous,
            }
        elif role == "planning":
            dependencies = {
                "REQ": [],
                "ARCH": ["REQ"],
                "CODE": ["ARCH"],
                "TEST": ["CODE"],
                "DOCS": ["TEST"],
                "RELEASE": ["DOCS"],
            }
            descriptions = {
                "REQ": "Normalize measurable requirements",
                "ARCH": "Inspect impact and select design",
                "CODE": "Apply approved, supported source changes",
                "TEST": "Execute trusted regression tests",
                "DOCS": "Write reviewed run documentation",
                "RELEASE": "Collect human release decision",
            }
            result = {
                "tasks": [
                    {
                        "id": item,
                        "description": description,
                        "dependencies": dependencies[item],
                        "status": "completed" if item == "REQ" else "pending",
                        "owner": item.lower() + "_agent",
                        "required_inputs": dependencies[item],
                        "expected_outputs": [item.lower() + "_artifact"],
                        "acceptance_criteria": [description + " passes its exit gate"],
                        "risk_level": "high" if item == "CODE" else "medium",
                    }
                    for item, description in descriptions.items()
                ],
                "rationale": "Task dependencies are explicit; implementation/test design can fan out after architecture approval.",
            }
        elif role == "architecture":
            inspection = artifacts.get("inspection", {})
            changed = {
                "greenfield": ["app/shortener.py", "app/routes/urls.py"],
                "brownfield": ["app/expiration.py", "tests/test_generated_expiration.py"],
                "ambiguous": ["app/features.py", "tests/test_generated_policy.py"],
            }[scenario]
            result = {
                "components": [
                    "FastAPI routes",
                    "SQLAlchemy domain service",
                    "SQLite storage",
                    "LangGraph control plane",
                ],
                "affected_files": changed,
                "decisions": [
                    "Use a supported operation compiler, not arbitrary generated code",
                    "Require content-hash-bound implementation approval",
                    context.get("architecture_hint") or "Keep deployment manual",
                ],
                "risks": [
                    "SQLite is single-node",
                    "The copied test workspace is not a security sandbox",
                ],
                "mermaid": 'flowchart TD\n API["FastAPI"] --> Domain["URL service"]\n Domain --> DB["SQLite"]\n Graph["LangGraph"] --> Review["Approval gates"]\n Review --> Workspace["Change workspace"]',
                "reviewed_source_hashes": inspection.get("hashes", {}),
            }
        elif role in {"implementation_plan", "repair"}:
            op = {
                "greenfield": "bootstrap_reference",
                "brownfield": "implement_expiration",
                "ambiguous": "set_creation_limit",
            }[scenario]
            rate = re.search(r"(\d+)\s+(?:requests|creations)", clarification)
            result = {
                "operations": [
                    {
                        "kind": op,
                        "value": int(rate.group(1))
                        if rate
                        else 20
                        if op == "set_creation_limit"
                        else None,
                        "rationale": "Implement the scoped requirement using the reviewed tool vocabulary",
                    }
                ],
                "requirement_ids": ["REQ"],
                "decision_ids": [d["id"] for d in context.get("decisions", [])][-3:],
                "summary": "Materialize reviewed reference code"
                if scenario == "greenfield"
                else "Apply a genuine supported source change",
            }
        elif role == "test_design":
            result = {
                "cases": [
                    "create, collision, redirect, analytics",
                    "expiration UTC contract",
                    "unsafe-target policy",
                ],
                "acceptance_checks": artifacts["requirements"]["acceptance_criteria"],
                "command_key": "pytest_workspace",
            }
        elif role == "documentation":
            report = context.get("validation", {})
            result = {
                "summary": f"{scenario} reviewed workflow; revision {context['revision']}",
                "rationale": "DAG gates and trusted tools preserve bounded autonomy",
                "assumptions": artifacts["requirements"]["assumptions"],
                "risks": artifacts["architecture"]["risks"],
                "limitations": [
                    "Offline fixture planning, not live inference",
                    "Supported semantic edits only; no arbitrary source or shell generation",
                    "Copied workspace is not an OS sandbox",
                ],
                "markdown": f"# Engineering run\n\nMode: offline-deterministic (no LLM inference).\n\nScenario: {scenario}.\n\nActual Pytest report: {report}.\n\nChanges: {context.get('changed_files', [])}.\n",
            }
        else:
            raise ValueError(f"Unknown offline role {role}")
        return result, {"inference_performed": False, "fixture_role": role}
