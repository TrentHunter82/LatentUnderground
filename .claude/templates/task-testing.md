# Testing Task Template

## Pre-flight Checklist
- [ ] Read `.claude/rules/TESTING_RULES.md`
- [ ] Read `.claude/rules/BACKEND_RULES.md` and `.claude/rules/FRONTEND_RULES.md` (for domain context)
- [ ] Check existing test patterns: `Grep pattern="describe(" path="backend/tests/"` or `frontend/src/test/`
- [ ] Verify mock targets match actual exports: check named vs default exports (TESTING_RULES #6)

## Implementation
- [ ] Write tests
- [ ] Use `createApiMock()` for all api.js mocks (TESTING_RULES #2)
- [ ] Use `createProjectQueryMock()` / `createSwarmQueryMock()` for hook mocks
- [ ] Use `tmp_path` for file paths, never hardcoded paths (TESTING_RULES #11)
- [ ] Use `database.SCHEMA_VERSION` not hardcoded integers (TESTING_RULES #21)
- [ ] Match component prop interfaces exactly (TESTING_RULES #14)
- [ ] For destructive action buttons: check for ConfirmDialog (TESTING_RULES #15)

## Post-flight Checklist
- [ ] Run full backend tests: `cd backend && uv run python -m pytest -q`
- [ ] Run full frontend tests: `cd frontend && npx vitest run src/test/`
- [ ] Verify tests pass in full suite, not just individually (TESTING_RULES #12)
- [ ] If test uses vi.useFakeTimers: use advanceTimersByTimeAsync, not waitFor (TESTING_RULES #17)
- [ ] If test modifies mock implementations: restore in finally block (TESTING_RULES #5)

## Acceptance Criteria
- All tests pass in full suite
- No test pollution (tests don't affect each other)
- Module-level state cleaned up in teardown (TESTING_RULES #10)
- Mock validation passes for frontend tests
- Explicit timeouts on slow tests (TESTING_RULES #20)
