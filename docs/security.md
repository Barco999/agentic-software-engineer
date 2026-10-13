# Security, governance and boundaries

## Threat model

Untrusted inputs include URL destinations, requirements, source snippets, model responses and public requests. Sensitive assets include provider keys, private source, local files, execution authority and engineering decisions.

## Enforced boundaries

1. Models only return schema-validated JSON. Supported executable operations are bootstrap_reference, implement_expiration and set_creation_limit.
2. Models never select shell commands, paths, arbitrary Python, destructive actions, migrations or deployments. Unsupported actions are denied, even if a caller tries to approve them.
3. WorkspacePolicy rejects absolute paths, traversal, escaping symlinks, unsupported prefixes and unsupported extensions.
4. Every high-impact implementation/repair/release decision pauses through LangGraph interrupt. Approvals bind revision and artifacts/source hashes.
5. Snapshot rollback restores modified files and removes newly created files. Rejection and exhausted repair budgets are terminal.
6. The single test command uses the active Python interpreter, trusted repository/compiled tests, a filtered environment without API keys, and a timeout. A model cannot substitute a command.
7. Live provider context is bounded/redacted; audit summaries never return raw source/prompt/workspace paths. API keys remain configuration-only SecretStr values.
8. Public endpoints are read-only for workflows. Starting, changing, approving and rejecting require access to the local operator CLI.

## Important limitations

The workspace is a copied directory, not a verified OS/container sandbox. Source/templates are trusted repository assets. This version intentionally refuses arbitrary model-generated executable code; broader autonomous editing requires genuine isolation, least privilege and code review.

Redaction is pattern-based, not a complete DLP system. Review sensitive source before live inference; live CLI use sends approved source context to the configured provider. No provider call occurred during offline verification.

Audit chaining can reveal edits to event history, but a host owner could rewrite the database and hashes. It is not immutable, signed or certified compliance storage. No Schwab-specific compliance certification is claimed.

The public URL service intentionally redirects to user-chosen public destinations. Scheme/credential/private-IP/DNS controls reduce abuse but do not verify page content or fully solve client DNS rebinding. No visitor IP, user-agent or referrer is stored in link analytics. Public analytics and unauthenticated link creation remain explicit prototype trade-offs.

Schema create_all is initialization, not migration management. Any future destructive/migration operation is unsupported until a reviewed migration and approval policy are added. Multi-worker rate limiting, TLS, ownership/auth, retention and production abuse monitoring are out of scope.
