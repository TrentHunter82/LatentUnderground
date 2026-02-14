# Frontend Rules

Distilled from lessons learned. Read before writing any frontend code.

## React Patterns

1. **Match props to actual API response schema**: Verify the actual API response shape before coding. `phase.current` vs `Phase` — check the endpoint, don't assume.

2. **Clear timers before setting new ones**: `if (ref.current) clearTimeout(ref.current)` before `ref.current = setTimeout(...)`. Prevents timer accumulation.

3. **Toast setTimeout needs cleanup tracking**: Store timeout IDs in `useRef(new Map())`. Clear specific ones on dismiss, clear all on unmount.

4. **Toast retry callbacks must not capture DOM events**: Extract core logic into event-free function. React synthetic events are pooled and become stale.

5. **useEffect polling: compute decisions from fresh response, not stale state**: Derived values outside useEffect are captured at closure creation time. Branch on response data inside the callback.

6. **useCallback deps must include all referenced state**: If useCallback calls another function that reads state, include that state in deps or use a ref.

7. **Debounce breaks synchronous test assertions**: When adding debounce, update tests to use `await waitFor(() => expect(...))`.

## Accessibility

8. **ARIA on visual indicators**: For status dots, LEDs, badges — add `role="img"` and `aria-label`. Required by axe 4.11.

9. **aria-label on span/div requires role="img"**: axe 4.11 enforces aria-prohibited-attr without a valid ARIA role.

10. **ARIA tablist children**: Only `role="tab"` or `role="presentation"` allowed. Move toolbar elements outside the tablist.

11. **Shape-based indicators need processAgents prop**: `agentStatus()` checks `processInfo` from `processAgents` prop, not `agents.alive`. Pass both props.

## Testing Components

12. **ResizeObserver polyfill in test setup**: jsdom doesn't implement ResizeObserver/IntersectionObserver/matchMedia. Add polyfills in setup.js.

13. **axe heading-order: disable in component tests**: Components with h3 fail heading-order when rendered without parent h1/h2. Only test heading hierarchy in full-page tests.

14. **TanStack Query hooks: stable references prevent infinite re-renders**: Extract mock data as module-level constants. `const _data = [...]; useProjects: () => ({ data: _data })`.

15. **vi.resetModules() breaks React context providers**: Don't use when test has static provider imports AND dynamic component imports. Accept as known flakes.

## Performance

16. **useEffect dependency arrays**: New object/array references trigger re-renders. Memoize with useMemo/useCallback or use module-level constants.
