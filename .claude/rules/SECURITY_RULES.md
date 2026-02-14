# Security Rules

Non-negotiable security patterns. Violations are blocking issues in code review.

1. **Bind local-only servers to 127.0.0.1**: Never use `0.0.0.0` unless network access is intentional. This exposes the API to the entire LAN.

2. **Validate all model fields that become subprocess args**: `Field(ge=1, le=24)` for agent_count/max_phases. `max_length` on strings stored in DB. Unbounded fields = resource exhaustion.

3. **ReDoS protection for user-supplied regex**: `re.compile()` + `asyncio.wait_for(asyncio.to_thread(search), timeout=5.0)` + pattern length cap (200 chars) + input size cap (1MB). Copy from existing `searchSwarmOutput` implementation.

4. **HTTP path traversal**: HTTP clients normalize `..` segments. Test security with realistic non-allowlisted paths, not `../../etc/passwd`. The allowlist approach is the correct mechanism.

5. **When changing auth skip paths, update tests**: After removing an endpoint from `_AUTH_SKIP_PATHS`, grep for tests asserting the old behavior (200 without auth). Update every match.

6. **CORS restricted to localhost only**: Origins 5173 (Vite dev) and 8000 (FastAPI). Adding other origins requires explicit justification.

7. **File API restricts to allowlisted paths**: Never bypass the path allowlist check. Any new file endpoint must validate against the allowlist.

8. **API key via LU_API_KEY env var**: Empty = auth disabled. Skips /api/health, /docs. WebSocket requires ?token= parameter.
