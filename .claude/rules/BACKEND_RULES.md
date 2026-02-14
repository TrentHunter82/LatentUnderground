# Backend Rules

Distilled from lessons learned. Read before writing any backend code.

## Python / FastAPI

1. **Use HTTPException, not error dicts**: Always `raise HTTPException(status_code=..., detail=...)`. Never return `{"error": "..."}` with 200 status.

2. **Pydantic validation → 422, not 400**: Pydantic Field validation errors return 422. Only business logic errors raised explicitly in handlers return 400.

3. **Pydantic model ordering**: Define models in dependency order (leaf first, composite last). Forward references cause NameError at import time.

4. **`from .module import NAME` creates a frozen copy**: Use `from . import module` and reference `module.ATTR` at call time for values tests need to override (DB_PATH, config).

5. **FastAPI Depends() override**: `app.dependency_overrides[get_db] = mock_fn` is the ONLY way to mock Depends() in tests. `patch()` doesn't work.

6. **get_db() is an async generator**: Use `async with aiosqlite.connect(...)` in tests, never `await get_db()`.

7. **Validate model fields that become subprocess args**: Any field passed to subprocess must have `Field(ge=..., le=...)` bounds and `max_length` on strings.

## Async / Subprocess

8. **Never call blocking I/O from async coroutines**: `proc.wait()`, `proc.communicate()`, `thread.join()` must be wrapped in `asyncio.to_thread()`.

9. **On Windows, use subprocess.Popen + daemon threads**: `asyncio.create_subprocess_exec` fails under uvicorn's reloader (SelectorEventLoop). Use `subprocess.Popen` instead.

10. **stdin=subprocess.DEVNULL for --print mode**: Claude Code `--print` blocks waiting for stdin EOF. Always use DEVNULL.

11. **Cache shared refs before TOCTOU checks**: `pool = _pool; if pool and not pool._closed:` — prevent reference changing between check and use.

12. **Supervisor tasks: clean up in finally block**: Any long-running task in a tracking dict must `finally: dict.pop(key)` to prevent memory leaks.

13. **Don't clean up shared locks while held**: Never delete a lock from a dict inside a function called while that lock is held. Clean up on project deletion, not swarm stop.

14. **Supervisor must not clean itself up**: Split cleanup: agent-only cleanup (safe from supervisor) vs full cleanup including supervisor cancel (for external callers).

## SQLite

15. **ORDER BY timestamps need tiebreaker**: `ORDER BY created_at DESC, id DESC` — same-second inserts are non-deterministic without tiebreaker.

16. **aiosqlite.Row factory required**: Set `db.row_factory = aiosqlite.Row` before using `row["column"]` string indexing.

17. **ConnectionPool must set all per-connection PRAGMAs**: `synchronous=NORMAL`, `temp_store=MEMORY`, `cache_size=-16000`, `foreign_keys=ON`, `busy_timeout=5000`. Not just WAL mode.

## Security

18. **Bind to 127.0.0.1, not 0.0.0.0**: Local-only tools must not expose to the network.

19. **ReDoS protection for user regex**: `re.compile()` + `asyncio.wait_for(to_thread(search), timeout=5.0)` + pattern cap (200 chars) + input cap (1MB).

20. **Prometheus histogram: handle overflow**: `for/else` — durations exceeding all buckets land in the largest bucket.
