# Architecture

## Two connected systems

The reference FastAPI app provides real creation, redirect, expiration and aggregate analytics behavior. The LangGraph platform operates against a copied run-specific workspace of that application, changes real supported source files, tests them, and returns reviewable engineering evidence.

The service separates routes, Pydantic schemas, domain logic, SQLAlchemy models/sessions and security policy. Schema initialization uses Base.metadata.create_all at startup. It is not a general migration system; a future schema change must use a reviewed migration before production.

The control plane separates provider transport, schema-bound agent roles, graph state/gates, trusted operations, snapshot rollback, audit/metrics and local CLI. A model cannot access a filesystem or subprocess directly.

## State and stores

| Store | Purpose | Durability boundary |
| --- | --- | --- |
| URL SQLite database | Links, expiration, aggregate counters | Configured DATABASE_URL |
| LangGraph checkpoints.db | Typed state and pending interrupts | AGENT_DATA_DIR |
| audit.db | Safe run summaries and hash-chained events | AGENT_DATA_DIR |
| runs/<id>/workspace | Actual source/test changes | Same runtime storage |
| runs/<id>/snapshots/rN | Per-revision original files | Same runtime storage |
| runs/<id>/rN | Artifacts, test logs, JUnit evidence | Same runtime storage |

All runtime stores must be backed up together. A checkpoint without its workspace/snapshot is not sufficient for recovery. The local file lock prevents two operator commands from executing the same run concurrently; SQLite is still not a distributed work queue.

## Source reasoning and change lineage

Inspection reads actual allowlisted Python bytes, producing relative paths, hashes and bounded/redacted snippets. Architecture output cannot introduce false inspected hashes. Brownfield analysis must inspect app/expiration.py. Every source change records requirement revision, proposal hash and approval decision ID. Release readiness rehashes changed code after validation and refuses drift.

## Scaling and consistency

SQLite uniqueness is authoritative; random-code collisions retry at most five times. Click increments use an atomic SQL update, not read-modify-write. Database sessions are request-scoped. Timestamp round-trips normalize SQLite's naive datetime representation to UTC.

The process-local creation limiter is intentionally simple. A multi-replica system needs a shared limiter and transactional production database. Workflow data needs a production checkpointer/event store, authenticated operator service, isolated execution workers, and durable artifacts before distributed operation.
