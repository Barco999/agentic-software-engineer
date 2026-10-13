# Final engineering summary

## Plan and rationale

Build the reference URL service first, then make the orchestration govern real changes to a copied workspace. Prioritize the assignment's differentiator: explicit dependency gates, parallel synchronization, durable context, approvals, failure repair/rollback and traceability.

FastAPI/Pydantic/SQLAlchemy make application boundaries and validation inspectable. LangGraph handles real conditional scheduling, reducers and interrupt/resume. SQLite keeps local setup reproducible. Model transports are configurable without assuming a free tier or available model ID.

## Delivered artifacts

- Runnable URL API, schema initialization, UTC expiry and aggregate analytics.
- Live Gemini/OpenAI-compatible providers plus honest offline fixtures.
- Typed LangGraph state, canonical task DAG, parallel planning, durable checkpoints.
- Real approval controls, supported source/test operations, revision-scoped snapshots.
- Real Pytest validation, two-repair budget, fallback/safe stop, rollback and selective replan.
- Redacted durable audit records, hashes, reliability metrics, read-only API and local CLI.
- Three executable scenario exports, OpenAPI, tests/lint, architecture/security/decision/coverage docs.
- Docker/Render configuration and GitHub instructions; no external publish/deploy.

## Validation

The actual verification commands and results are in evidence/verification.json, test-results.xml, live-server.json and scenarios/. The suite runs provider mock transports, API/SQLite behavior, unsafe destination checks, collisions/expiration, graph persistence, approvals, genuine parallel overlap, repair routing, retry limits, rollback, lineage, redaction and selective re-planning. A real owned Uvicorn child is verified over TCP.

Tests do not claim to validate live authenticated inference. Add your key/model in .env and run the live CLI to test account/model/schema compatibility. Docker build, Render deployment, Windows execution, load testing and independent penetration testing remain unverified.

## Assumptions, risks and trade-offs

The URL service accepts only public HTTP(S) destinations on standard ports. Analytics are aggregate-only. Public creation/analytics have no ownership/auth model. DNS checks reduce unsafe-target exposure but cannot guarantee content safety or eliminate client-side DNS rebinding.

Offline fixtures are deterministic analysis, not inference. Greenfield materializes prewritten reviewed reference source; models are not falsely credited with authoring it. Supported semantic edits are intentionally bounded. The copied workspace is not an OS sandbox, so arbitrary generated Python or shell is not executed.

SQLite/checkpoints/file locks and local limiting are single-node prototype choices. Audit chains are not signed immutable compliance logs. Schema initialization is not migration management. Broad code generation, remote authenticated operators, genuine sandboxing, retention, shared limiting, high-availability persistence and production monitoring are future work.

Humans own final approval and quality control. Release approval only records readiness and does not deploy.
