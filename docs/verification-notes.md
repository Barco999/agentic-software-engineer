# Verification notes

An actual default-directory demo uncovered a Pytest import-path issue: because the change workspace lived below the reference repository, Pytest inherited the parent pyproject pythonpath setting and imported reference modules instead of changed modules. The external-temporary-directory workflow tests did not reproduce that placement.

The fix supplies a controlled empty Pytest configuration, an explicit workspace root and conftest boundary, and the workspace PYTHONPATH. A source-origin assertion now checks that app.shortener is imported from the current workspace. A nested-workspace regression test exercises a real failing expiration check and repair under the reference repository.

The corrected full suite and all three demos were rerun. Earlier failed demo exports are archived in local runtime history rather than merged into final evidence. Current evidence/scenarios contains only its corresponding final run. No test success was synthesized.
