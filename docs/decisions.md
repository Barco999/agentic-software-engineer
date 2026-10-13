# Architecture decision record

| Decision | Rationale | Trade-off |
| --- | --- | --- |
| FastAPI/Pydantic/SQLAlchemy | Clear API/domain/schema/persistence boundaries and real OpenAPI | Framework dependencies must be pinned |
| LangGraph + SqliteSaver | Genuine conditional flow, fan-in and durable interrupt/resume | Local SQLite concurrency, not distributed execution |
| Canonical six-task DAG | Task dependencies cannot skip safety-critical phases | Smaller vocabulary than arbitrary task engines |
| Live provider abstraction plus offline fixtures | User can supply credentials later; deterministic demos remain honest | Live quality/account availability requires separate validation |
| Reviewed operation compiler | Real file modification without model-selected executable code or shell | Only three supported semantic edits |
| Per-revision snapshots | Restore failed changes and preserve an accepted earlier revision | Snapshot storage grows; retention needs product decisions |
| Hash-bound approvals | Approval cannot silently authorize a changed proposal/workspace | Reviewers must inspect artifacts before approving |
| Trusted subprocess tests | Actual pass/failure/repair evidence without arbitrary code execution | Copied workspace is not a general sandbox |
| CLI-only mutation | No publicly exposed agent write capability | Remote operators need a future authenticated control service |
| Aggregate analytics | Useful counts while avoiding visitor identifiers | No user-level attribution/cohort analysis |
| Single-node rate limiting and SQLite | Reproducible compact assessment | Shared limiter/database needed for scale |

Alternative general code-writing tools and automated deployment were excluded because they would materially expand execution authority. Provider model IDs stay configurable; no specific model/free-tier claim is baked into the project.
