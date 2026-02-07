# Latent Underground - Task Board (Phase 2)

## Claude-1 [Backend/Core] - Production serving, error recovery, API improvements

- [x] Serve frontend build from FastAPI (mount dist/ as static files, SPA fallback for client routes)
- [x] Add startup validation: check for required directories, create if missing
- [x] Persist swarm PID in database so server restart doesn't lose track of running processes
- [x] Add process health check: verify if stored PID is still running
- [x] Add GET /api/swarm/output/{project_id} endpoint to stream subprocess stdout/stderr
- [x] Add rate limiting to file write endpoint (prevent rapid-fire saves)
- [x] Add updated_at auto-update trigger or middleware for all project mutations
- [x] Move watch/unwatch endpoints from main.py into a dedicated router
- [x] Signal: Create .claude/signals/backend-ready.signal

## Claude-2 [Frontend/Interface] - UX polish, error handling, responsive design

- [x] Add error toast/notification system (replace console.error in SwarmControls)
- [x] Add confirmation dialog before stopping a running swarm
- [x] Add loading skeletons for dashboard components (replace plain "Loading..." text)
- [x] Make sidebar collapsible on small screens (responsive breakpoint)
- [x] Add keyboard shortcuts: Ctrl+S to save in file editor, Escape to cancel edit
- [x] Add project deletion with confirmation from sidebar context menu
- [x] Show last-modified timestamp on file editor
- [x] Add syntax highlighting for markdown code blocks (lightweight: highlight.js or prism)
- [x] Signal: Create .claude/signals/frontend-ready.signal

## Claude-3 [Integration/Testing] - Browser testing, real integration, CI

- [x] Add frontend unit tests with Vitest (at minimum: api.js, useWebSocket hook)
- [x] Test frontend build serves correctly from FastAPI static mount
- [x] Test full browser workflow: create project -> launch -> dashboard updates -> stop
- [x] Test WebSocket reconnection behavior (kill server, restart, verify auto-reconnect)
- [x] Test file editor save/reload cycle with concurrent external modifications
- [x] Add CI-ready test script that runs both backend and frontend tests
- [x] Signal: Create .claude/signals/tests-passing.signal

## Claude-4 [Polish/Review] - Final quality gate

- [x] Review all Phase 2 code changes for quality and consistency
- [x] Verify no regressions: all Phase 1 tests still pass
- [x] Performance review: check for unnecessary re-renders, excessive API calls
- [x] Security review: verify CORS, path validation, subprocess handling
- [x] Update README.md with Phase 2 changes and production deployment notes
- [x] FINAL: Generate next-swarm.ps1 for Phase 3 (if needed) or mark project complete

## Completion Criteria
- [x] cd backend && uv run python run.py serves both API and frontend on port 8000
- [x] Full workflow works in browser without dev server
- [x] Error states are handled gracefully with user-visible feedback
- [x] All tests pass (backend + frontend)
- [x] No console errors or warnings in production build
