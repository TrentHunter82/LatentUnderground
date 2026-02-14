# Backend Task Template

## Pre-flight Checklist
- [ ] Read `.claude/rules/BACKEND_RULES.md` and `.claude/rules/SECURITY_RULES.md`
- [ ] Read `.claude/rules/WINDOWS_RULES.md` (if touching subprocess/file I/O)
- [ ] Grep for related patterns in existing code: `Grep pattern="<keyword>" path="backend/app/"`
- [ ] Check if task touches Pydantic models — if so, verify dependency order (leaf first)
- [ ] Check if task adds new endpoints — if so, plan response models in responses.py

## Implementation
- [ ] Write the code
- [ ] If adding DB columns: add migration to `_MIGRATIONS`, bump `SCHEMA_VERSION`
- [ ] If adding DB columns: update hardcoded assertions in test_migration.py, test_phase17_features.py, test_graceful_shutdown.py, test_database_indexes.py
- [ ] If adding module-level state: add cleanup to conftest.py teardown
- [ ] If using blocking I/O in async code: wrap in `asyncio.to_thread()`

## Post-flight Checklist
- [ ] Run backend tests: `cd backend && uv run python -m pytest -q`
- [ ] Zero new warnings in test output
- [ ] If new endpoint: test with curl/httpie to verify response shape
- [ ] If new model: run `cd backend && uv run python scripts/export_schemas.py` to update contracts
- [ ] Add lesson to `tasks/lessons.md` if anything unexpected happened

## Acceptance Criteria
- All backend tests pass
- No hardcoded version strings (use `app.version` or constants)
- No blocking I/O in async routes (BACKEND_RULES #8)
- All new Pydantic fields have bounds (SECURITY_RULES #2)
- Bind to 127.0.0.1 only (SECURITY_RULES #1)
