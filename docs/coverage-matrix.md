# Assignment coverage matrix

The PDF asks for a working prototype with production-oriented judgment, not a claim of production readiness. The implementation below is executable within its documented bounded scope.

| Requirement | Implementation | Automated verification | Demonstration evidence / status |
| --- | --- | --- | --- |
| Requirement understanding, ambiguities, normalization | agents/roles.py, llm providers, RequirementsArtifact, requirements_gate | test_ambiguous_clarification_replans_before_implementation | Ambiguous clarity interrupt and r2 requirements; implemented |
| Decomposition, dependency sequencing | PlanArtifact, orchestration/gates.py | cycle/missing dependency checks; task completion assertions | Every scenario planning artifact; implemented |
| Brownfield codebase reasoning | inspect_repository, architecture role/hash verification | Brownfield workflows operate on actual starter module | Inspection hashes, before/after expiration source; implemented |
| Full lifecycle orchestration | orchestration/graph.py StateGraph | End-to-end durable workflow test | Plans, changes, tests, docs, readiness, final report; implemented |
| Explicit graph, entry/exit gates | Task DAG plus graph preconditions/readiness | dependency and workflow tests | Graph docs and exported artifacts; implemented |
| Sequential and parallel synchronization | Fan-out + reducers + list-based fan-in | test_true_parallel_fanout_and_synchronization | Overlapping entry/exit timestamps followed by fan_in; implemented |
| Stateful execution/context preservation | WorkflowState + SqliteSaver | new service/runtime reloads pending checkpoint | Resume CLI/state and durable artifacts; implemented |
| Decision lineage | proposal requirement IDs, decision IDs, revision/hash ledger | change entries contain approval IDs | changes artifacts and approval events; implemented |
| Human high-impact approval | LangGraph interrupt + Command resume, hash binding | pause, reject, stale approval and concurrency tests | Actual pending gates; scripted demos honestly identified |
| Bounded retry, fallback, rollback, safe stop | two repairs, transport retries, snapshots, terminal path | fail_once, always_fail, release rejection, missing key | Brownfield failure/recovery logs; implemented |
| Guardrails / security / change control | WorkspacePolicy, operation allowlist, no shell/model code, redaction | traversal/symlink/unsafe operation/redaction tests | Enforced bounded rules; not compliance certification |
| Audit traceability and metrics | AgentStore, hash chain, read-only endpoints | audit-chain verification, recovery sample assertion | Exported traces/metrics; tamper-evident prototype only |
| Dynamic re-plan after upstream change | WorkflowService.revise + affected closure/Overwrite | architecture replan preserves requirements/history | Ambiguous clarification replan and revision test; implemented |
| Engineering outputs: code/API/schema/tests/docs | app/, operation compiler, Pydantic/OpenAPI, tests, docs | API and trusted workspace tests | Real source changes, OpenAPI, generated reviewed tests |
| Risks/trade-offs/validation | docs/security.md, decisions.md, engineering-summary.md | failure paths exercised | Documented; load/security penetration tests not performed |
| Controlled autonomy | local CLI gates, scoped supported operations | rejects stop execution; no HTTP write API | Implemented within narrow operation vocabulary |
| Final engineering summary | finalize artifacts and docs/engineering-summary.md | final task/outcome assertions | Every completed scenario final_report.json |
| Runnable end-to-end prototype | API plus graph/provider/CLI | Pytest and real Uvicorn TCP smoke | Verified offline; live inference pending user's key |
| Architecture overview | README, docs/architecture.md and orchestration.md | Imports/runtime graph verified | Components, control flow, Mermaid, rationale supplied |
| Three scenarios | scripts/run_scenarios.py + fixtures | scenario-specific workflow tests | evidence/scenarios actual execution |
| Setup/testing/limitations | README and docs | pinned dependencies installed; lint and tests | Windows commands supplied; Windows runtime not tested |

## Additional prompt requirements

| Requested capability | Status |
| --- | --- |
| FastAPI, SQLAlchemy, Pytest/TestClient, LangGraph, dotenv, Ruff | Implemented and executed |
| Gemini/OpenAI-compatible structured providers | Implemented and mock-transport tested; authenticated live inference unverified |
| URL validation/private-DNS/collisions/307/410/analytics/persistence | Implemented and tested |
| API read-only run/audit/metrics; privileged local CLI | Implemented and tested |
| Actual file changes with snapshots | Implemented through supported reviewed operations; arbitrary general coding unsupported |
| Test generation | Relevant reviewed template tests are materialized; arbitrary model-generated executable tests unsupported |
| Secure sandbox | NOT implemented or claimed; only trusted operation/template execution |
| Dockerfile and Render configuration | Supplied; build/hosting unverified; no deployment |
| GitHub-ready source and precise push commands | Supplied; no remote push or evaluator message sent |
| Downloadable ZIP and actual evidence | Included in handoff |
