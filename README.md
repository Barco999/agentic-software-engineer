# Agentic Software Engineer + URL Shortener

A FastAPI URL-shortening service and a local Streamlit review dashboard connected to a durable, governed LangGraph software-engineering workflow. The workflow is the primary assessment: it inspects actual source, analyzes requirements, creates a task DAG, proposes changes, pauses for approval, modifies a controlled workspace, executes real Pytest tests, repairs bounded failures, rolls back rejected/failed changes, and produces a final report.

Gemini and OpenAI-compatible providers are configurable. No key is needed for the URL API, unit tests, or explicitly offline demonstrations. Live AI workflows require valid provider credentials. The custom greenfield path can propose new source files, but does not execute AI-generated code.

## Quick start — Windows PowerShell

Run these commands from the repository directory. Python 3.12 is a conservative choice if available; use a compatible installed Python version if not.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=...`, `GEMINI_MODEL=...` and `DEMO_MODE=false` for live Gemini runs. Use a currently accessible model; never commit `.env`. Streamlit must be installed in the environment (`python -m pip install streamlit` if it is not already listed as a dependency).

**Terminal A — start FastAPI (URL shortener):**

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

**Terminal B — start the Streamlit dashboard:**

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard.py
```

Open **http://localhost:8501**. Streamlit provides the **Agentic Engineering Review** page and the **URL Shortener** page (`pages/1_URL_Shortener.py`). On the URL Shortener page, use `http://127.0.0.1:8000` as the FastAPI base URL. The API exposes Swagger at **http://127.0.0.1:8000/docs** and health information at `/health`.

An API key is not required to use the URL shortener. The dashboard is a **trusted local operator interface**, not an authenticated public service. On Windows, invoking `.venv\Scripts\python.exe` directly avoids PowerShell activation-policy issues.

## Reviewer walkthrough

1. In Streamlit, choose **Greenfield**, leave **Offline fixture mode** unchecked, and enter a custom requirement such as: *Build a Task Management REST API with FastAPI, SQLite, CRUD, Pydantic schemas, tests and documentation.*
2. Start the workflow. Inspect `requirements`, `planning`, and `architecture` artifacts at the first approval gate.
3. After architecture approval, inspect `implementation_plan`: look for `generate_files` with actual `{path, content}` entries. Review the proposed code before approving implementation.
4. Inspect the isolated run's changed-file ledger, syntax validation metadata and release checkpoint. **Custom-generated tests are not automatically run**, so a completed run is not a functional correctness guarantee.
5. Open **URL Shortener** in the Streamlit sidebar, create a link, open it to trigger a redirect, and check analytics by short code. This requires the FastAPI server to be running separately.
6. To view unit-test results on your own machine, run `.\.venv\Scripts\python.exe -m pytest -q`. The previously reported 54-pass result was from the earlier baseline; rerun tests for this version.

## Stack and architecture

| Concern | Technology |
| --- | --- |
| API / schemas / database | FastAPI / Pydantic / SQLAlchemy + SQLite |
| Workflow / durable state | LangGraph StateGraph + SqliteSaver |
| Providers | Gemini generateContent / OpenAI-compatible Chat Completions / offline fixtures |
| Validation | Pytest for trusted predefined flows; static Python syntax checks for custom-generated files |
| Audit / locking | Hash-chained SQLite JSON events / cross-process filelock |
| Configuration / lint | python-dotenv + environment variables / Ruff |
| Local UI | Streamlit (`dashboard.py` and `pages/1_URL_Shortener.py`) |

~~~mermaid
flowchart TD
  Client["API client"] --> API["FastAPI"]
  API --> Domain["URL service"]
  Domain --> URLs["SQLite URL data"]
  Operator["Local operator CLI / Streamlit"] --> Graph["LangGraph"]
  Graph --> Provider["Gemini / OpenAI / offline"]
  Graph --> Gates["Approval gates"]
  Gates --> Tools["Validated proposal applier"]
  Tools --> Workspace["Run-specific workspace"]
  Workspace --> Tests["Trusted-flow Pytest / custom-flow syntax check"]
  UI["Streamlit URL page"] --> API
  Graph --> Checkpoints["SQLite checkpoints"]
  Graph --> Audit["Audit and metrics"]
  API --> Audit
~~~

The public API has no workflow-write endpoints. The CLI and local Streamlit reviewer are privileged control interfaces; neither should be exposed to untrusted users.

## Agent roles

AgentSuite in agents/roles.py implements separate named roles with their own schemas and goals; modules are consolidated deliberately instead of creating empty agent files.

| Role | Concrete output/action |
| --- | --- |
| Requirements | Functional/nonfunctional needs, questions, assumptions, criteria, risk |
| Planning | Validated task dependencies, ownership, inputs, outputs, status, criteria |
| Architecture | Actual-source impact, inspected hashes, decisions, risks, Mermaid |
| Implementation planning | Reviewed operation proposals; custom greenfield can include `generate_files` file contents |
| Test design | Relevant acceptance checks and an allowlisted command key |
| Implementation | Actual approved source/test changes, snapshot, hashes and lineage |
| Testing | Trusted reference workflows run Pytest; custom-generated files receive static parsing only |
| Repair | New proposal; renewed approval; maximum two repairs |
| Documentation/release | Run documentation, risks, readiness, final approval; no deployment |

## Executable workflow

~~~mermaid
flowchart TD
  Inspect["Inspect source"] --> Req["Requirements"]
  Req --> Clear{"Clarity gate"}
  Clear -->|questions| Clarify["Clarification interrupt"]
  Clarify -->|new revision| Req
  Clear -->|clear| Plan["Task DAG"]
  Plan --> Arch["Architecture"]
  Arch --> AApprove["Architecture approval"]
  AApprove --> Impl["Implementation plan"]
  AApprove --> Tests["Test design"]
  Impl --> Sync["Fan-in barrier"]
  Tests --> Sync
  Sync --> IApprove["Implementation approval"]
  IApprove --> Apply["Snapshot and apply"]
  Apply --> Validate["Trusted Pytest or custom syntax validation"]
  Validate -->|pass| Docs["Documentation"]
  Validate -->|fail within budget| Repair["Repair proposal"]
  Repair --> RApprove["Repair approval"]
  RApprove --> Reapply["Apply repair"]
  Reapply --> Validate
  Validate -->|budget exhausted| Rollback["Rollback"]
  Docs --> Ready["Release readiness"]
  Ready --> Release["Release approval"]
  Release --> Done["Final report"]
  Rollback --> Stop["Safe stop"]
~~~

The two planning branches genuinely overlap using LangGraph fan-out, reducers, and a list-based fan-in edge. Required artifacts and task dependencies gate downstream work. Rejection, provider failure, stale approval, or policy failure routes toward rollback/safe stop.

## State, lineage and recovery

WorkflowState tracks run ID/revision, requirements, tasks, decisions, artifacts, hashes, approvals, validation, changes, repair counts, traces, usage and outcome. SQLite checkpoints survive process restart. Decisions link source/proposal hashes and requirement revision to implementation actions. Each run has a workspace, per-revision artifacts/test logs, baseline snapshots, and evidence.json under var/agentic.

One operator action per run is enforced with filelock. This is a local, single-node prototype—not a distributed scheduler. Back up checkpoints, audit and workspace data together. Do not hand-edit checkpoint rows.

## Approvals that control execution

After configuring a provider:

~~~powershell
python -m orchestration.cli start brownfield
python -m orchestration.cli show RUN_ID
python -m orchestration.cli approve RUN_ID --gate architecture --reason "Reviewed impact and design"
python -m orchestration.cli approve RUN_ID --gate implementation --reason "Reviewed proposal and tests"
python -m orchestration.cli approve RUN_ID --gate release --reason "Reviewed passing tests and limitations"
~~~

Replace RUN_ID with the printed ID. Use reject instead of approve to stop. Each action names the currently pending gate and records the operator/reason. Approval is bound to revision, artifacts and actual workspace hashes; stale approvals cannot authorize mutated files.

An ambiguous request pauses before changes:

~~~powershell
python -m orchestration.cli approve RUN_ID --gate clarification --reason "Confirmed scope" --clarification "Limit creation to 20 requests per minute; aggregate clicks only; retain public-destination policy."
~~~

Release approval marks ready for manual release and never deploys.

## Dynamic re-planning

~~~powershell
python -m orchestration.cli revise RUN_ID --stage architecture --value "Retain aggregate-only analytics and manual deployment" --reason "Updated design decision"
~~~

Architecture revision preserves requirement/plan history, re-inspects current bytes, invalidates the affected downstream closure, and requires fresh approvals. Requirements revision reruns analysis and its dependents. Earlier artifacts/decisions remain available. Tests verify unaffected requirements are not blindly rerun.

## Three scenarios, no API key

~~~powershell
python scripts/run_scenarios.py --offline
python -m orchestration.cli metrics
~~~

Offline mode uses explicitly scripted fixture approvals, not claimed human production approvals. It performs actual file changes and actual test execution, without inference.

| Scenario | Actual demonstration |
| --- | --- |
| Greenfield | Empty workspace → plan → reviewed reference app/tests materialized → validation |
| Brownfield | Real source with expiration stubs → impact analysis → implemented expiration module/tests → deliberately injected trusted regression → failed tests → repair → passing retest |
| Ambiguous | Questions/assumptions → clarification interrupt → revised plan → real rate-limit code change → tests |

The prebuilt URL-shortener service is reference code, not claimed LLM-generated source. Existing fixture operations apply trusted templates. Separately, **live custom greenfield** requests can generate actual Python, test and documentation file contents through `generate_files`, with human review and syntax-only validation. Arbitrary generated code execution remains unsupported.

For repeated failure, start brownfield with --offline --fault-mode always_fail. After two approved repair attempts, rollback restores the starter.

## API

| Endpoint | Behavior |
| --- | --- |
| POST /api/urls | Create link; optional customCode and expiresAt |
| GET /{short_code} | 307 redirect; atomic aggregate click increment |
| GET /api/urls/{short_code}/analytics | totalClicks, createdAt, lastAccessedAt |
| GET /health | Service/database readiness |
| GET /docs and /openapi.json | Generated Swagger/OpenAPI |
| GET /api/agent/runs | Safe workflow summaries |
| GET /api/agent/runs/{run_id} | Safe status/tasks/test summary |
| GET /api/agent/runs/{run_id}/audit | Redacted hash-chained events |
| GET /api/agent/metrics | Success/retry/rollback/validation/MTTR/latency |

~~~powershell
$body = @{url="https://example.com/article"; expiresAt="2099-01-01T00:00:00Z"} | ConvertTo-Json
$link = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/urls -ContentType "application/json" -Body $body
Invoke-RestMethod -Uri "http://localhost:8000/api/urls/$($link.shortCode)/analytics"
~~~

## Streamlit URL Shortener UI

The second Streamlit page is `pages/1_URL_Shortener.py`. It is an HTTP client of the existing FastAPI API, not a duplicate backend. Start Uvicorn on port 8000 and Streamlit on port 8501 (two terminals). The UI supports creation with an optional custom alias and expiration timestamp, link opening, and lookup of aggregate click analytics. A URL API connection is local by default. The URL shortener does not require a Gemini key.

## Credentials — add them only to your local .env

~~~dotenv
LLM_PROVIDER=gemini
GEMINI_API_KEY=<your key>
GEMINI_MODEL=<current model ID available to your account>
DEMO_MODE=false
~~~

Alternative:

~~~dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=<your key>
OPENAI_MODEL=<available model ID>
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_JSON_MODE=true
DEMO_MODE=false
~~~

No model/free-tier availability is assumed. Gemini uses current generateContent responseFormat schema configuration. The compatible provider uses Chat Completions JSON mode and local Pydantic validation; OPENAI_JSON_MODE=false supports endpoints lacking that option while retaining local validation.

Missing credentials/model safely stop live execution, never masquerading as offline inference. Transient transport errors have two retries and a timeout. Provider request construction, schema handling and retries are mock-transport tested. Live Gemini generation was exercised locally during development, including a custom Task Management API proposal. Model availability and API credentials vary by evaluator; a successful API call does not establish generated application correctness.

## Verification

~~~powershell
python scripts/verify_project.py
~~~

This reproduces the complete local verification and refreshes evidence/verification.json. Individual checks:

~~~powershell
python -m pytest -q
ruff check .
ruff format --check .
python scripts/verify_server.py
~~~

The server verifier starts an owned Uvicorn child, performs real TCP requests, and shuts it down. For an already-running service use python scripts/smoke.py. Test evidence is under evidence/test-results.xml, evidence/live-server.json and evidence/scenarios.

## Security and reliability

- Only absolute HTTP(S) destinations; reject embedded credentials, controls, local/private/reserved addresses, ambiguous numeric IPs and nonstandard ports.
- DNS checking is on by default, rejects any nonpublic resolution, and runs again before redirect. Tests inject a resolver; server smoke disables DNS only for reproducibility.
- This is intentionally a redirect service. Controls reduce abuse but do not guarantee destination content safety or eliminate client-side DNS rebinding.
- Random codes plus a primary key ensure uniqueness; collisions have five bounded attempts. Click updates are atomic and timestamps normalize to UTC.
- Creation requests have a process-local per-client limit. Production needs a shared gateway limiter.
- The trusted fixture operations use predefined templates. In custom greenfield mode, the model **can propose file paths and contents**, constrained by schema, path, extension and size policies, followed by operator approval. It cannot authorize shell commands or deployment.
- Workspace traversal/symlinks are blocked. Snapshot rollback restores modifications and removes created files.
- Copied workspace + trusted tools + filtered child environment + timeout is NOT an OS security sandbox. Arbitrary model code execution is unsupported.
- .env, databases and original attachments are excluded from Git/Docker/workspace copies; audit excludes raw prompts and redacts credential/private-path patterns.

## Deployment — optional and manual

~~~powershell
docker build -t agentic-shortener .
docker run --rm -p 8000:8000 --env-file .env -v agentic-data:/data -e DATABASE_URL=sqlite:////data/links.db -e AGENT_DATA_DIR=/data/agentic agentic-shortener
~~~

Render Docker instructions and a non-provisioned blueprint are included. Configure credentials as runtime secrets, never build arguments. The image honors PORT. Render's default filesystem is ephemeral; persistent disks require paid services. Free services can sleep. No disk, account, deployment or paid infrastructure was provisioned. Docker execution and Render deployment remain unverified; see docs/deployment.md.

## GitHub submission

Create an empty repository from your own account, then:

~~~powershell
git init -b main
git add .
git status --short
git commit -m "Build governed LangGraph URL shortener assessment"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
~~~

Choose visibility and give evaluator access if private. Review status and never add .env, var/, local databases, or the original assessment/email. No GitHub push was performed.

## Limitations and next steps

The governed six-stage pipeline supports an optional custom file-generation preview, but is not a fully autonomous, production-grade software engineer. Generated code is not functionally verified by the custom-flow validator. Live-provider quality/account access needs your key. The application has no link ownership/auth system; aggregate analytics are public. Audit hashes are tamper-evident convention, not signed immutable compliance storage. SQLite, single-node locking, DNS checks and local rate limiting are prototype choices. Future work: authenticated control/analytics, distributed durable orchestration, genuine code sandboxing before broader edits, signed audit storage, retention, shared limiting, load tests and monitoring.

See docs/coverage-matrix.md and docs/engineering-summary.md for assignment mapping, rationale, evidence and limitations.

To regenerate a clean submission archive: python scripts/package_project.py. It excludes credentials, databases, runtime workspaces, caches and the virtual environment.

## Custom AI-generated project preview (local operator)

The new optional **custom greenfield** flow uses a custom `--requirement` to ask
Gemini for real `app/`, `tests/` and `docs/` file contents instead of choosing a
fixed URL-shortener template. The six-stage governance, audit trail, revision,
approval hashes and snapshot/rollback remain in place. The implementation artifact
contains complete proposed file contents and must be reviewed **before** the
implementation approval. Maximum 12 files, 30 KB per file. Python must parse.

```powershell
python -m orchestration.cli start greenfield --requirement "Build a Task Management API with FastAPI and SQLite, CRUD endpoints and pytest tests"
python -m orchestration.cli show RUN_ID
python -m streamlit run dashboard.py
```

Install dependencies with `python -m pip install -r requirements.txt`. Set a
valid Gemini model and API key in your local `.env` (never commit it).
The dashboard is for a **trusted local operator only**, not public hosting.
It shows agent progress, full proposed file text, approvals, revisions, and
validation metadata. CLI remains supported. If the provider fails, it fails closed.

**Security / evaluation limitation:** AI-generated source is never executed by
this application's test runner. The custom path performs syntax-only validation,
records `runtime_tests_executed: false` and
`requires_manual_sandbox_test: true`, and awaits release approval. This is **not**
proof of a working generated application; manually run it only inside a separately
hardened, network-restricted environment with no private credentials. Trusted
predefined scenario regression tests continue to execute normally. The custom
mode is an assessment prototype, not a production code-execution sandbox.
