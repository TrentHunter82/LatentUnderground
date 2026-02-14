# Review Task Template

## Pre-flight Checklist
- [ ] Read ALL rule files in `.claude/rules/`
- [ ] Read `tasks/lessons.md` for recent patterns
- [ ] Identify all files changed in this phase: `git diff --name-only HEAD~N`

## Review Process
For each changed file:

### Code Quality
- [ ] Would a staff engineer approve this?
- [ ] No hacky fixes — if found, demand the elegant solution
- [ ] No temporary workarounds left in place
- [ ] Functions have single responsibility
- [ ] Error handling is consistent (HTTPException, not error dicts)

### Security (SECURITY_RULES)
- [ ] No new endpoints bypass auth without justification
- [ ] User-supplied regex has ReDoS protection (#3)
- [ ] Pydantic fields that become subprocess args have bounds (#2)
- [ ] File access goes through allowlist (#7)
- [ ] No secrets in committed files

### Testing
- [ ] Tests actually test the right things (not just coverage theater)
- [ ] All api.js mocks use `createApiMock()` factory
- [ ] No hardcoded version strings or schema versions
- [ ] Module-level state cleaned up between tests

### Consistency
- [ ] Version numbers in sync (frontend, backend, health endpoint)
- [ ] Response model field names match frontend expectations
- [ ] New exports added to both api.js AND createApiMock()

## Post-flight Checklist
- [ ] Run full test suite (backend + frontend): zero regressions
- [ ] Run `npm run validate:mocks`: sync check passes
- [ ] Update CHANGELOG.md with phase features
- [ ] Bump version in package.json and main.py
- [ ] Consolidate and deduplicate lessons in tasks/lessons.md

## Acceptance Criteria
- Full test suite passes
- No security regressions
- CHANGELOG updated
- Version bumped consistently
- Lessons consolidated
