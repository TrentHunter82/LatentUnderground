# Latent Underground - Phase 28: TanStack Query Completion & Log Aggregation

## Context
v2.3.0 with 2227+ tests (1488 backend + 739 frontend, 8 skipped). Phase 27 was a review-only phase — Claude-1/Claude-2 did not activate. Claude-3 completed test mock consolidation (carry-forward from Phase 26). Claude-4 ran security review (zero issues), code review, and version bump. All tests green.

**Architecture notes:**
- Backend: All 60+ endpoints stable, circuit breaker + guardrails + checkpoints fully implemented
- Frontend: TanStack Query partially adopted (App/Dashboard/ProjectView use hooks). SwarmControls, TerminalOutput, LogViewer, FileEditor still use raw fetch via api.js
- Test infrastructure: Shared mock factories (createProjectQueryMock, createSwarmQueryMock, createApiMock) in test-utils.jsx. Missing: `useProjectGuardrails` hook in factory
- Performance: React.lazy code splitting done but bundle impact not measured
- Circuit breaker config: Frontend sends flat fields matching backend ProjectConfig model

**Carry-forward items (from Phase 26/27):**
1. Agent log aggregation endpoints (Claude-1) — never started
2. TanStack Query migration for SwarmControls/TerminalOutput/LogViewer (Claude-1) — never started
3. Preload hints (Claude-2) — never started
4. Bundle size optimization (Claude-2) — never started
5. Lighthouse audit & FCP/TTI measurement (Claude-3) — never started
6. useProjectGuardrails missing from test mock factory (Claude-3 fix)

## Claude-1 [Backend/Core]

### Agent Log Aggregation (carry-forward x2)
- [ ] Add `GET /api/swarm/agents/{project_id}/{agent_name}/logs` endpoint: returns last N lines from agent's output log file (default 100, max 1000). Uses `_agent_log_files` paths from drain threads.
- [ ] Add `GET /api/swarm/output/{project_id}/tail?lines=N` endpoint: returns last N lines from combined output buffer efficiently (itertools.islice from end of deque)
- [ ] Implement log file rotation for agent output logs: max 10MB per file, keep 3 rotations. Use `LU_OUTPUT_LOG_MAX_MB` and `LU_OUTPUT_LOG_ROTATE_KEEP` config vars (already defined in config.py)

### TanStack Query Migration - Remaining Components (carry-forward)
- [ ] Create new mutation hooks in useMutations.js: `useSendInput`, `useSendDirective`, `useUpdatePrompt` (for components still using raw api.js calls)
- [ ] Migrate SwarmControls.jsx to use TanStack Query mutations (`useLaunchSwarm`, `useStopSwarm` already exist; wire them up, remove manual loading/error state)
- [ ] Migrate TerminalOutput.jsx polling to use `useSwarmOutput` query with `refetchInterval` (replace manual setTimeout polling loop)
- [ ] Migrate LogViewer.jsx to use TanStack Query for log fetching (new `useLogs` hook)
- [ ] Migrate FileEditor.jsx to TanStack Query for file read/write

## Claude-2 [Frontend/Interface]

### Route-Level Preloading (carry-forward) ✅ DONE by Claude-2
- [x] Add `onMouseEnter` preload for ProjectView: preloads JS chunk on Sidebar hover (+ NewProject on "+ New Project" hover)
- [x] Route-level prefetching: chunk preload on hover eliminates loading spinner on navigation

### Bundle Size Optimization (carry-forward) ✅ DONE by Claude-2
- [x] Measured bundle: 254KB index, 174KB highlight, 161KB markdown, 79KB ProjectView — already well code-split with 24 lazy chunks
- [x] Audited npm deps: all 9 production + all dev dependencies actively used, zero removable
- [x] axe-core already dev-only (vitest-axe), highlight.js already lazy-loaded via code splitting
- [x] No unused api.js exports found — all are referenced by components

### Guardrail Results Display (carry-forward, partially done) ✅ DONE by Claude-2
- [x] Dashboard guardrail results display verified working (pass/fail per rule with color-coded icons)
- [x] SwarmHistory `failed_guardrail` indicator already existed (triangle warning icon + "guardrail" text)
- [x] Added expandable guardrail results row in SwarmHistory: clicking chevron shows per-rule pass/fail detail inline

## Claude-3 [Integration/Testing]

### Test Mock Factory Fix
- [ ] Add `useProjectGuardrails` hook to `createProjectQueryMock()` in test-utils.jsx (missing — will cause failures when components start using it)
- [ ] Add `useLogs` hook mock to `createSwarmQueryMock()` if Claude-1 creates it during TanStack migration

### TanStack Query Migration Tests
- [ ] Add tests for migrated SwarmControls (mutation trigger, loading state, cache invalidation after launch/stop)
- [ ] Add tests for migrated TerminalOutput (polling interval, abort on unmount, per-agent filtering with query key)
- [ ] Add tests for migrated LogViewer (search query, pagination, refetch on filter change)

### Performance Verification (carry-forward)
- [ ] Run Lighthouse audit on production build (score targets: Performance 90+, Accessibility 100, Best Practices 90+)
- [ ] Measure FCP/TTI: compare before/after React performance optimizations (startTransition, useDeferredValue)
- [ ] Document results in tasks/todo.md with specific numbers

## Claude-4 [Polish/Review]
- [ ] Code review: Agent log aggregation endpoints follow existing patterns (security, pagination, error handling)
- [ ] Code review: TanStack Query migration preserves all existing behavior (no regressions)
- [ ] Code review: Bundle optimization changes are measurable improvements
- [ ] Security review: new endpoints have proper auth, input validation, rate limiting
- [ ] Update CHANGELOG.md with Phase 28 features, bump version to v2.4.0
- [ ] FINAL: Full test suite passes, zero regressions
