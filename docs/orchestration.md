# Orchestration and gates

GraphRuntime constructs a real StateGraph with a SQLite checkpointer. No hardcoded success trace is returned by a demo. Offline fixtures replace only model inference; graph execution, interrupts, source changes, test subprocesses, rollback and reports remain real.

## Stage entry and exit conditions

| Stage | Entry condition | Exit condition |
| --- | --- | --- |
| Inspection | Allowlisted workspace exists | Actual source hashes/snippets captured |
| Requirements | Inspection artifact exists | RequirementsArtifact validates |
| Clarity gate | Validated requirements | Clarification supplied or explicitly not required |
| Planning | Clear requirement | Acyclic canonical task DAG and mandatory safety dependencies |
| Architecture | Requirement, plan, inspection | Valid schema; no invented inspected hashes; ARCH dependencies complete |
| Architecture approval | Current design and source fingerprint | Durable approval with matching hash/revision |
| Parallel planning / test design | Approved architecture | Both schema-valid artifacts from current revision |
| Fan-in | Both branches complete | Synchronization verifies both current-revision outputs |
| Implementation approval | Proposal and test design | Matching operator decision before filesystem mutation |
| Apply | Scenario-allowed operations and current approval | Baseline snapshot, actual source writes and change ledger |
| Validation | CODE task complete; allowlisted command | Actual nonempty Pytest report, pass or failure routing |
| Repair | Failed validation; repair count below two | Valid revised proposal and renewed approval |
| Documentation | Passing validation | Report written and DOCS task complete |
| Release readiness | Tests pass, no errors, source hashes unchanged | Exit report ready; no deployment |
| Release approval | Current readiness/validation/code fingerprint | Durable approve or reject |
| Finalize | Matching release approval | Final report and RELEASE task completed |
| Rollback / safe stop | Failure/rejection/limit | Restore snapshot, preserve evidence, terminal safe status |

## Recovery flow

~~~mermaid
flowchart TD
  Test["Real Pytest"] --> Outcome{"Pass?"}
  Outcome -->|yes| Ready["Documentation and readiness"]
  Outcome -->|no| Budget{"Repair budget?"}
  Budget -->|remaining| Proposal["Repair proposal"]
  Proposal --> Approval["Human approval"]
  Approval -->|approved| Apply["Apply supported repair"]
  Apply --> Test
  Budget -->|exhausted| Restore["Restore baseline"]
  Approval -->|rejected| Restore
  Restore --> Stop["Safe stop"]
~~~

Transport retries are separate from repair retries. Only transient HTTP/timeouts are retried; invalid schema/auth/model errors safely stop. No provider failure is reclassified as inferred offline success.

## Durable approval sequence

~~~mermaid
sequenceDiagram
  participant O as Operator
  participant G as LangGraph
  participant P as Provider
  participant T as Trusted tools
  participant S as State stores
  O->>G: Start requirement
  G->>P: Schema-bound analysis
  P-->>G: Validated plan/design
  G->>S: Checkpoint interrupt
  G-->>O: Approval request and hash
  O->>G: Approve current gate
  G->>S: Record decision lineage
  G->>T: Snapshot and supported edits
  T-->>G: Changed file hashes
  G->>T: Run trusted Pytest
  T-->>G: Actual pass/failure report
  alt Failed with budget
    G->>P: Propose repair
    G-->>O: Renewed approval
  else Passed
    G->>S: Readiness evidence
    G-->>O: Release approval request
  end
~~~

Interrupt nodes may replay when resumed. They make no filesystem or audit-decision side effect before interrupt returns. Source tools are idempotent; snapshots are persistent and revision-scoped.

## Re-planning

Requirements change invalidates its dependency closure; architecture change preserves requirements/planning and resets ARCH/CODE/TEST/DOCS/RELEASE. Current source is re-inspected. Reducer fields are explicitly overwritten when dropping stale artifacts/errors/approvals; prior decision history remains append-only. Revised code receives new approval and a new rollback baseline.

## Metrics definitions

Success rate uses terminal outcomes, excluding waiting runs. Repair/provider retries are distinct. Validation pass rate uses real Pytest reports. MTTR is populated only when a failed validation later recovers; null means no recovery samples. End-to-end latency includes time waiting for approval. Stage duration records agent/tool execution. These are demo metrics, not production SLOs.
