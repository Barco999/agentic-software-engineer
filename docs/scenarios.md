# Executable scenarios and evidence

Run python scripts/run_scenarios.py --offline. The runner executes the real graph and exports artifacts/test logs/trace to evidence/scenarios/<scenario>. Fixture approvals are explicitly attributed to deterministic_demo_fixture, not a claimed human production reviewer.

## Greenfield

The change workspace starts empty. Requirements, task plan, architecture, concurrent implementation/test proposals, approval, source materialization, tests and docs execute. The tool copies reviewed reference source; the report does not pretend the model authored that prewritten implementation.

Evidence: greenfield/evidence.json, r1/artifacts, and r1/validation-0. Source actions have proposal hashes, approval IDs and requirement revision.

## Brownfield expiration

The starter is a copy of real source with app/expiration.py replaced by reproducible unimplemented stubs. Inspection supplies actual bytes/hashes. Approved implementation replaces the module and adds relevant trusted expiration tests.

The demo deliberately applies a trusted expiration-check regression on the first implementation. Real Pytest fails; repair proposes the supported expiration operation, pauses for renewed approval, writes correct code, and retests. There is no simulated test success/failure.

Evidence includes expiration-before.py and expiration-after.py, inspection/architecture/change artifacts, validation-0 failure log, validation-1 recovery log, approval decisions and final summary. The retry-limit/rollback case is separately exercised by test_two_repairs_max_then_rollback_and_safe_stop.

## Ambiguous security/reliability

The graph detects unresolved scope and pauses at clarification before file mutation. The scripted demo supplies measurable scope: keep public-destination protection, limit creation to 20 requests/minute, aggregate counts only, and exclude authentication/password links/deployment. Analysis and planning are regenerated in a new revision; actual app/features.py and a generated reviewed limiter test change.

Evidence: ambiguous/evidence.json, clarity/replan events and r2 artifacts/validation. Product questions are explicit; this is not permission to invent broader requirements.
