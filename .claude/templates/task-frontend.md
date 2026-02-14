# Frontend Task Template

## Pre-flight Checklist
- [ ] Read `.claude/rules/FRONTEND_RULES.md` and `.claude/rules/SECURITY_RULES.md`
- [ ] Verify the actual API response shape before coding (FRONTEND_RULES #1)
- [ ] Check if component uses browser APIs not in jsdom (ResizeObserver, IntersectionObserver)
- [ ] Check existing component prop interfaces: `Grep pattern="export default function" path="frontend/src/components/"`

## Implementation
- [ ] Write the component/feature
- [ ] Add ARIA attributes to all visual indicators (role="img", aria-label)
- [ ] Use stable references for hook return values (module-level constants in mocks)
- [ ] Clear timers before setting new ones (FRONTEND_RULES #2)
- [ ] No stale closures in useEffect/useCallback (FRONTEND_RULES #5, #6)

## Post-flight Checklist
- [ ] Run frontend tests: `cd frontend && npx vitest run src/test/`
- [ ] Run mock validation: `cd frontend && npm run validate:mocks`
- [ ] If new api.js export: update `createApiMock()` in test-utils.jsx, then run validate:mocks
- [ ] If new component: add to at least one test file
- [ ] Check axe accessibility: aria-label on span/div needs role="img" (FRONTEND_RULES #8, #9)

## Acceptance Criteria
- All frontend tests pass (except known flakes documented in lessons.md)
- Mock validation passes (`npm run validate:mocks`)
- No new axe-core violations
- All visual indicators have ARIA attributes
- No React key warnings in test output
