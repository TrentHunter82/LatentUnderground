# Latent Underground - Task Board (Phase 5)

## Claude-1 [Backend/Core] - Deployment and infrastructure

- [x] Add Docker support: Dockerfile + docker-compose.yml for single-command deployment
- [x] Add environment configuration: .env file support for host, port, database path
- [x] Add database backup/export endpoint (GET /api/backup -> SQLite dump)
- [x] Add swarm templates table and CRUD endpoints (save/load project configs as presets)
- [x] Add process reconnection: detect and reattach to running subprocesses after restart
- [x] Signal: Create .claude/signals/backend-ready.signal

## Claude-2 [Frontend/Interface] - UX and advanced features

- [x] Add swarm template selector in NewProject form (dropdown of saved presets)
- [x] Add mini-graph sparkline showing task completion rate over time in Dashboard
- [x] Add keyboard navigation for tabs (arrow keys, Home/End)
- [x] Add responsive mobile layout improvements (tab overflow scroll, collapsible panels)
- [x] Add project export button (download project config + history as JSON)
- [x] Signal: Create .claude/signals/frontend-ready.signal

## Claude-3 [Integration/Testing] - Test hardening and E2E

- [x] Add tests for Docker build and startup
- [x] Add tests for environment configuration loading
- [x] Add tests for swarm template CRUD
- [x] Add E2E test: full project lifecycle (create -> configure -> launch -> stop -> history)
- [x] Add accessibility tests (tab navigation, ARIA attributes, screen reader compatibility)
- [x] Signal: Create .claude/signals/tests-passing.signal

## Claude-4 [Polish/Review] - Final quality gate

- [x] Review all Phase 5 code changes for quality and consistency
- [x] Verify no regressions: all Phase 4 tests still pass (266+)
- [x] Security review: Docker config, env handling, backup endpoint
- [x] Bug fixes: migration exception handling, output buffer leak, column whitelist
- [x] FINAL: Generate next-swarm.ps1 for Phase 6 (if needed) or mark project complete

## Completion Criteria
- [x] Application deployable via Docker with single command
- [x] Swarm templates can be saved and loaded
- [x] All tests pass (backend + frontend, including new Phase 5 tests)
