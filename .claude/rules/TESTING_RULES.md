# Testing Rules

Distilled from lessons learned. Read before writing any test code.

## Mock Management

1. **vi.mock must include ALL exports used by child components**: React component tree imports deeply. Mock the ENTIRE shared module, not just what the test directly uses.

2. **Adding exports to shared modules requires updating ALL test mocks**: When adding to api.js: grep `vi.mock.*lib/api`, add mock to every file, run full suite. Use `createApiMock()` factory.

3. **When changing mock targets in production code, update ALL test files**: `grep -r "old_pattern" tests/` — fix every occurrence.

4. **vi.clearAllMocks() clears state, NOT implementations**: After clearing, mocks become `vi.fn()` returning undefined. Re-set implementations in each test or use `mockResolvedValueOnce()`.

5. **mockRejectedValue pollutes subsequent tests**: Wrap in try/finally and restore original mock. Or use `mockRejectedValueOnce()` which auto-resets.

6. **Test mocks must match actual export shape**: Check named vs default export before writing vi.mock. `grep "export" source/file` takes 2 seconds.

7. **MagicMock streams: set readline.return_value = b""**: For subprocess stdout mocked with MagicMock, drain threads need EOF sentinel to terminate.

8. **TanStack Query configurable hooks**: Use `vi.fn()` wrapper for per-test overrides: `const mock = vi.fn(() => defaultResult)` then `mock.mockReturnValue(customResult)` per test.

9. **TanStack Query v5 extra context arg**: Test mutations with `fn.mock.calls[0][0]` not `toHaveBeenCalledWith`.

## Test Isolation

10. **Module-level state leaks across tests**: Rate limiters, caches, etc. at module scope need `clear()` in conftest/beforeEach teardown.

11. **Test fixtures: use tmp_path, never hardcoded paths**: `"folder_path": "F:/TestProject"` accidentally matches real filesystem. Always use tmp_path.

12. **Frontend test pollution**: Tests pass alone but fail in suite — dynamic import module caching + vi.mock leaks. Use `describe.skip` for known flakes.

## Assertions & Selectors

13. **getAllByText when text appears in multiple components**: "All" buttons, "Latent Underground" headings — use `getAllByText()[0]` or `getByRole` with name option.

14. **Match component prop interfaces exactly**: Check `export default function Component({ ...props })` destructuring. Props not in destructuring are silently ignored.

15. **SwarmControls Stop button opens ConfirmDialog first**: Click trigger → wait for alertdialog → click confirm button inside dialog.

16. **HTML5 input max blocks form silently**: If `value > max`, onSubmit never fires. Update min/max when changing defaults.

## Async Testing

17. **vi.useFakeTimers blocks waitFor**: Use `await act(async () => { await vi.advanceTimersByTimeAsync(100) })` instead.

18. **SSE endpoints can't be tested with httpx ASGI transport**: Test 404 case normally. Test generator logic as unit test. Use `asyncio.wait_for` with short timeout.

19. **Async loadLogs races with ws state updates**: Render with null props first, await async effect, then re-render with prop data.

20. **Flaky timeout tests: add explicit timeout**: `it('name', async () => { ... }, 15000)` for heavy setup or dynamic imports.

## Schema & Versions

21. **Schema version assertions: use database.SCHEMA_VERSION**: Never hardcode `assert version == 3`. Use the constant.

22. **replace_all on version assertions over-replaces**: Use targeted edits. Some tests insert specific versions without running migrations.

23. **Don't hardcode version strings**: Always reference `app.version` or shared constant. Grep for old strings when bumping.

24. **Vite chunk name extraction**: Use `name.split('.')[0].split('-')[0]` — hashes can contain hyphens.

25. **App-level rendering always times out in jsdom**: Never render full App. Test at component level. Use describe.skip or e2e for full-page tests.
