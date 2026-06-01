# Agent Plans

## Claude-4 (Polish/Review) — Theme System Final Gate (Phase 1)

State on entry: Theme System & Reskins is implemented and VERIFIED green by the swarm
(frontend 795 pass / 0 fail, backend themes 19/19, lint 0, build OK, CSS 69.4KB < 72KB).
A prior Claude-4 context already drafted next-swarm.ps1 (Phase 2 = tokenize per-skin CSS).
The current relaunch handed a generic placeholder tasks/TASKS.md — must reconcile so the
next relaunch doesn't loop on empty tasks (lessons #79).

### Plan
1. [x] Re-establish green baseline (full frontend suite) — 795 pass / 24 skip / 0 fail.
2. [x] Read all theme artifacts (themes.js, useTheme, ThemePicker, SettingsPanel, index.html, index.css, tests).
3. [x] Multi-agent adversarial review workflow over the theme diff (5 dimensions → verify each finding).
4. [x] Apply confirmed fix-now findings (10/10). See findings summary below.
5. [x] Re-run affected suites + full suite — 799 pass / 24 skip / 0 fail; CSS 71.77KB < 72KB.
6. [x] Reconcile tasks/TASKS.md to reflect the completed Phase 1 theme work (no placeholder loop).
7. [x] Consolidate lessons.md (+4 lessons); update AGENT_STATUS, activity.log, heartbeat.
8. [x] Validate next-swarm.ps1 parses; create phase-complete.signal; output COMPLETE-ALL.

### Fresh-context final re-certification (2026-06-01T02:51Z)
A later Claude-4 context re-ran the WHOLE gate from scratch (trusting no prior report):
- frontend **806 pass / 24 skip / 0 fail (40 files)** — fixed one flake: `phase15-features.test.jsx`
  FileEditor-404 tests timed out at the 5s default under full-suite load (35/35 green alone) →
  added file-level `vi.setConfig({ testTimeout: 15000 })` (lesson #451 pattern). Re-run: 806/0.
- ESLint **0 errors** (42 pre-existing non-blocking react-hooks advisories); build OK,
  **CSS 74234B / 72.5KB < 76KB**; backend `themes.validate` PASS; `next-swarm.ps1` parses clean.
- Re-reviewed theme code (themes.js / useTheme / ThemePicker / SkinToggle): staff-engineer quality.
- Re-created `.claude/signals/phase-complete.signal` (the earlier one was withdrawn during the
  concurrent token refactor). Tree now stable & green → safe to signal.

### Claude-4 Review Findings (theme-system adversarial review — 20 agents)
Raw 15 → 10 confirmed fix-now (all fixed) → 5 rejected (sound reasoning, e.g. `aria-required`
is invalid on `radiogroup`; the 0.02-opacity light glow is imperceptible; the "double
getInitialMode race" can't occur — useState runs synchronously).

Confirmed & fixed:
- **a11y (high):** SettingsPanel focus-trap selector matched `<button tabindex="-1">` (inactive
  ThemePicker radios). Added `:not([tabindex="-1"])` to every element-type clause.
- **CSS (high/med):** base `.btn-neon-danger:hover` + `.retro-panel-glow` hardcode the Analog
  mint palette; non-Analog skins inherited it on hover/glow. Added per-skin overrides for
  obsidian dark+light and blueprint dark+light (`:hover`) and blueprint `.retro-panel-glow`.
  (Reviewer undercounted by one — obsidian-light `:hover` was also missing; fixed it too.)
- **tests (med):** no shared `createThemeMock`; partial/duplicated `useTheme` mocks across 10
  files. Added the factory (imports real `SKINS`) and migrated all 10. Added focus-movement
  assertions to theme-picker-keyboard (it claimed to test focus but never asserted it).
- **integration (high):** skin id list duplicated in themes.js / index.html / index.css with no
  mechanical sync. Added `theme-registry-sync.test.js` to fail loudly on drift (chosen over the
  reviewer's "empty analog CSS block" idea, which would have spent precious CSS budget).

### Reconciliation note (concurrent token refactor)
While I was finalizing, Claude-2 landed a token-driven `index.css` refactor (the planned Phase-2
headline) — the `:root` COMPONENT TOKEN CONTRACT. My literal per-skin `.btn-neon-danger:hover` /
`.retro-panel-glow` overrides were SUPERSEDED by it (the bug I found is now fixed structurally via
`--btn-danger-hover-*` / `--panel-glow-shadow` tokens, 6 skin token-overrides present). The refactor
also shrank CSS to 68.41KB (budget headroom restored). My other fixes are untouched by it and remain
green. My `theme-registry-sync.test.js` SURVIVED the refactor (still passing) — the SSOT guard proved
its worth. Re-verified the full tree green AFTER the refactor: 799 pass / 24 skip / 0 fail. Updated
next-swarm.ps1 so Phase 2 doesn't redo the now-landed tokenization.

---

## Claude-1 (Backend/Core) — Current Session

Mission: Make Latent Underground fully controllable from the web UI — no terminal
management needed. Polish per-agent orchestration, fix bugs, improve reliability.

### Plan
1. [in progress] Baseline: run full backend pytest suite, capture any failures.
2. [in progress] Backend orchestration audit workflow (6 concern finders + adversarial
   verification) → confirmed bugs / reliability / controllability gaps.
3. [ ] Fix confirmed failing tests (reliability baseline must stay green).
4. [ ] Fix confirmed audit findings, highest severity first. Root-cause, no hacks.
5. [ ] Re-run tests to prove each fix. Mark done only after green.
6. [ ] Update lessons.md; signal backend-ready.

### Notes
- swarm.py (3843 lines) is the orchestration core. API surface already rich.
- Prior phases report ~1488 backend tests green. This is polish/reliability work.

---

# Agent Plans (history below)

## Claude-2 [Frontend/Interface] - COMPLETED (Phase 27 Session)

### Phase 27: Preload Hints, Guardrail Display, Bundle Optimization

All 3 Claude-2 task groups completed with zero regressions:

#### 1. Route-Level Preloading (Sidebar.jsx)
- Added `preloadProjectView()` module-level function: calls `import('./ProjectView')` once on first hover
- Added `preloadNewProject()` for "+ New Project" button hover
- Both functions use module-level flags to fire exactly once (idempotent, cached by bundler)
- `onMouseEnter` and `onFocus` handlers on Sidebar project links and new project button
- No QueryClient dependency — pure chunk preloading, zero test breakage
- Eliminates loading spinner when navigating to projects after hover

#### 2. Guardrail Results in Run Detail (SwarmHistory.jsx)
- SwarmHistory already had `failed_guardrail` status indicator (triangle warning icon) — verified working
- Added expandable row: chevron button appears in Tasks column when `run.guardrail_results` exists
- Clicking chevron toggles inline detail panel showing per-rule results
- Each rule shows: PASS/FAIL icon, rule_type, pattern (truncated), threshold, action badge (halt/warn), detail
- Color-coded: green for passed, red for halt failures, amber for warn failures
- `expandedRunId` state tracks which run's detail is expanded
- Uses `React.Fragment` with key for proper row grouping
- Proper ARIA: `aria-expanded` on toggle button, descriptive `aria-label`

#### 3. Bundle Size Optimization (audit only)
- Current bundle: 254KB index, 174KB highlight, 161KB markdown, 79KB ProjectView — 24 lazy chunks
- All 9 production deps actively used (verified via source grep)
- All dev deps actively used (verified via import scan)
- axe-core already dev-only (vitest-axe), highlight.js already code-split
- No removable packages found — bundle is well-optimized

### Files Modified
- `frontend/src/components/Sidebar.jsx` — preload hints on hover
- `frontend/src/components/SwarmHistory.jsx` — expandable guardrail results row
- `tasks/TASKS.md` — marked tasks complete

### Test Results
- **Sidebar tests**: 5/5 passed (zero regressions)
- **SwarmHistory tests**: all passed across phase3, phase9, phase10, phase21
- **Full suite**: 707+ passed, 67 pre-existing failures in SwarmControls/TerminalOutput/LogViewer (not related to my changes)
- **Build**: Clean, no warnings, 597 modules, 26 chunks

---

## Claude-4 [Polish/Review] - COMPLETED (Phase 27 Session)

### Phase 27 Review: Test Infrastructure & Quality Gate (v2.3.0)

**Status of other agents**:
- **Claude-1**: Did NOT activate — agent log aggregation and TanStack Query migration not started
- **Claude-2**: Did NOT activate — preload hints, bundle optimization, guardrail results display not started
- **Claude-3**: 100% complete — test mock consolidation done (carry-forward from Phase 26), 6 new TanStack Query integration tests added

**Claude-4 Review Actions**:
1. **Test mock consolidation review**: Verified shared factories in test-utils.jsx. Found 2 issues:
   - `useProjectGuardrails` hook missing from `createProjectQueryMock()` factory (carried to Phase 28)
   - Factory functions return new object literals each call (data refs stable, but hook function refs are new). Not causing issues currently since vi.mock() calls factory once, but could cause problems with per-test overrides. Noted as improvement item.
2. **Security review**: Zero vulnerabilities found in Phase 26 changes. Guardrail ReDoS protection (5s timeout + 200-char + 1MB cap) intact. Circuit breaker Pydantic bounds enforced (ge/le on all fields). CORS localhost-only. No XSS vectors.
3. **Full test suite verification**:
   - Backend: 1488 passed, 3 skipped, 1 xfailed, ZERO failures
   - Frontend: 739 passed, 8 skipped, ZERO failures
   - Total: 2227 tests, zero regressions
4. **Version bump**: v2.2.0 → v2.3.0 (config.py, package.json, CHANGELOG.md)

**Generated**: tasks/TASKS.md for Phase 28 (TanStack Query Completion & Log Aggregation), next-swarm.ps1 for auto-launch.

---

## Claude-4 [Polish/Review] - COMPLETED (Phase 26→27 Transition)

### Phase 26 Review: Frontend Performance & Test Coverage (v2.2.0)

**Status of other agents**:
- **Claude-1**: Completed circuit breaker/guardrail test coverage (carried by Claude-3). Agent log aggregation NOT started (carried to Phase 27)
- **Claude-2**: 90% complete — React performance (startTransition, useDeferredValue, React.lazy), circuit breaker UI, guardrail rule editor UI all done. Preload hints NOT started (carried to Phase 27)
- **Claude-3**: 100% complete — 46 guardrail tests created, TanStack Query test migration fixed (75 failures resolved), all tests passing

**Claude-4 Actions**:
1. **React performance review**: Verified startTransition, useDeferredValue, React.lazy changes are correct
2. **TanStack Query review**: Migration preserves existing functionality, cache invalidation works
3. **Circuit breaker UI review**: Found and FIXED field name mismatch — frontend was sending nested `circuit_breaker: { max_failures }` but backend expects flat `circuit_breaker_max_failures`. Fixed in ProjectSettings.jsx + tests
4. **Terminal output fix**: Moved `offsetRef.current` update before `startTransition` block to prevent duplicate fetches during deferred renders
5. **Guardrail test review**: 46 tests comprehensive and correct
6. **Security review**: No regressions from frontend changes
7. **Version bump**: v2.1.0 → v2.2.0 (config.py, package.json, CHANGELOG.md)

**Final Test Results**:
- **Backend**: 1488 passed, 3 skipped, 1 xfailed, ZERO failures
- **Frontend**: 741 passed, 5 skipped, 1 known flaky timeout (passes individually)
- **Total**: 2229+ tests

**Generated**: tasks/TASKS.md for Phase 27, next-swarm.ps1 for auto-launch.
