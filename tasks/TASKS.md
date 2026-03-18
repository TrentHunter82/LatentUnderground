# Latent Underground Add Featutures

Latent Underground Add Featutures

## Claude-1 [Backend/Core]
- [x] Analyze project structure and identify specific tasks
- [ ] Fix sqlite3.connect() missing timeout in _monitor_pid (deadlock risk)
- [ ] Add mmap_size PRAGMA to ConnectionPool for consistency with init_db
- [ ] Fix project deletion cleanup - clean ALL swarm tracking dicts
- [ ] Add ETag middleware size limit to prevent OOM on large responses
- [ ] Fix auto-queue failure to properly log and update project status
- [ ] Add rate limit status info to /status endpoint response
- [ ] Add POST /agents/{project_id}/restart-all bulk restart endpoint
- [ ] Fix/document broken /input endpoint (stdin=DEVNULL makes it non-functional)
- [ ] Run backend tests to verify all changes pass

## Claude-2 [Frontend/Interface]
- [ ] Set up UI scaffolding
- [ ] Implement main interface components
- [ ] Connect to backend APIs

## Claude-3 [Integration/Testing]
- [ ] Write unit tests for core modules
- [ ] Write integration tests
- [ ] Verify all components work together

## Claude-4 [Polish/Review]
- [ ] Code review all agent work
- [ ] Fix issues found in review
- [ ] FINAL: Generate next-swarm.ps1 for next phase

