# LatentUnderground — Theme System & Reskins (Phase 1)

Multi-skin reskin layer on top of the existing light/dark mode. COMPLETE & verified.

## Claude-1 [Backend/Core]
- [x] Reskin validation guardrail at `backend/themes/` (stdlib, zero deps): validates
      image_manifest.json (required fields, unique paths, PNG signature, path-traversal
      rejection) + design tokens (REQUIRED_TOKENS regression guard + CSS color validity).
      CLI: `cd backend && python -m themes.validate [--json]`. 19/19 unittests pass.
- [x] Deliberately NO `/api/themes` router — the theme system is client-side, so a
      backend theme API would be dead code.

## Claude-2 [Frontend/Interface]
- [x] `lib/themes.js` skin registry (analog/obsidian/blueprint) — single source of truth.
- [x] `useTheme` orthogonal skin axis (`data-skin` attr + `latent-skin` persistence);
      legacy light/dark mode contract preserved.
- [x] `index.css` Obsidian + Blueprint skins, dark + light variants, `:not(.light)`-scoped.
- [x] `ThemePicker` (accessible radiogroup, roving tabindex) in Settings → Appearance.
- [x] No-flash bootstrap in `index.html` (applies `.light` + `data-skin` before paint).
- [x] Rendered-palette e2e (`e2e/theme-skins.spec.js` → "rendered palette (real cascade)"):
      reads the resolved `var()` cascade off `getComputedStyle` in a REAL browser and asserts
      each skin paints a distinct, non-empty body background + accent, and that light≠dark per
      skin. Closes lesson #446 — the one regression class (deleted/broken skin CSS block) that
      every attribute-only test stays green through. Verified 2/2 pass on the Edge channel
      (bundled Chromium download is sandbox-blocked here); ESLint 0.

## Claude-3 [Integration/Testing]
- [x] Theme test suites: phase26-theme-skins, theme-picker-keyboard, theme-skins-integration.
      All registry-driven (iterate `SKINS`/`SKIN_IDS`) so the Terminal skin + any future
      skin are covered automatically — no hardcoded 3-skin lists. 49 theme tests total.
- [x] Quality gate: whole repo green; fixed SettingsPanel mock regressions + a load flake.
- [x] Quality gate (re-cert, this run): killed the timeout-flake CLASS at root. A full run
      hit 4 timeout failures (phase15/phase5/phase17) — `vi.setConfig({testTimeout})` proved
      unreliable under parallel load (phase15 fell back to the 5000ms default). Replaced 26
      scattered/inconsistent timeout band-aids (24 per-test `}, NNNNN)` + 2 `vi.setConfig`)
      with ONE authoritative `testTimeout:30000`/`hookTimeout:30000` in vite.config.js.
      VERIFIED STABLE: frontend 806 pass / 24 skip / 0 fail across TWO consecutive full runs,
      backend themes 19/19 + `themes.validate` PASS, ESLint 0 errors, build OK. See lessons.md.
- [x] E2E theme coverage (Hardening/Visual-QA phase): added `e2e/theme-skins.spec.js` (13 tests)
      covering behaviour jsdom CANNOT reach — the index.html no-flash bootstrap (persisted skin
      applied on load, invalid→analog fallback, all 4 registry skins round-trip), the top-bar
      SkinToggle cycling analog→obsidian→blueprint→terminal→analog + reload persistence,
      skin/mode orthogonality, AND the Settings→Appearance ThemePicker radiogroup in a real
      browser (Arrow/Home/End move selection+focus+`data-skin` together with wrapping, roving
      tabindex, click-to-select persistence). Also FIXED a tautological existing test in
      `e2e/app.spec.js` ("persists theme preference") that wrote the WRONG localStorage key
      (`theme` instead of `latent-theme`, the key the app reads) and only asserted the key it
      set still existed — it now seeds `latent-theme` and asserts the app applies `.light`.
      VERIFIED via the FULL e2e harness: **41 passed / 0 failed / 18 skipped** (user-journey
      tests self-skip cleanly when the backend is down — by design) on a real browser engine
      (system Edge — bundled Chromium download was blocked in this sandbox; tests are
      browser-agnostic and run on the committed config's chromium project in CI). ESLint 0 on e2e.

## Claude-4 [Polish/Review]
- [x] Code review all agent work — 20-agent adversarial review of the theme diff
      (15 findings → 10 confirmed fix-now, 5 rejected with sound reasoning).
- [x] Fix issues found in review:
  - [x] a11y: SettingsPanel focus trap now excludes `tabindex="-1"` (roving-tabindex radios).
  - [x] CSS: per-skin `.btn-neon-danger:hover` (obsidian dark/light, blueprint dark/light) +
        blueprint `.retro-panel-glow` — eliminates Analog mint-palette bleed on interaction.
  - [x] tests: `createThemeMock()` factory in test-utils.jsx; migrated 10 files off
        partial/duplicated `useTheme` mocks; added focus-movement assertions.
  - [x] guard: `theme-registry-sync.test.js` enforces themes.js ↔ index.html ↔ index.css SSOT.
- [x] Final verification: frontend 799 pass / 24 skip / 0 fail (39 files), ESLint 0 errors,
      build OK, CSS 71.77KB < 72KB budget.
- [x] FINAL: `next-swarm.ps1` generated for Phase 2 (tokenize per-skin CSS to custom
      properties — shrinks the bundle, frees the thin budget, makes a 4th skin cheap).
- [x] WCAG AA contrast audit (Hardening/Visual-QA phase — the Claude-4 task next-swarm.ps1
      planned): added `theme-contrast-audit.test.js` (9 tests). jsdom can't resolve `var()`,
      so it reads index.css, resolves each skin×mode token cascade as the browser would, and
      COMPUTES (never estimates) the real WCAG 2.1 relative-luminance ratio of --body-fg/--body-bg
      (≥ 4.5:1, SC 1.4.3) and --neon-green/--body-bg accent (≥ 3:1, SC 1.4.11/large-text).
      Contexts are derived from SKIN_IDS so a 5th skin is audited automatically (no drift; mirrors
      theme-registry-sync). MEASURED: text 11.35–14.20:1 (huge margin); accent 3.43–17.15:1
      (tightest analog-light 3.43, blueprint-light 4.65, terminal-light 4.60) — ALL PASS. Proved
      the guard discriminates (black/white=21.00; bad pairs compute 1.2:1 and trip the threshold).
      Full suite after add: frontend 815 pass / 24 skip / 0 fail (42 files), ESLint 0 on the new file.
- [x] Hardening review + verify (full suite/build/lint green; budgets tightened not bumped): re-certified
      the integrated tree after all concurrent Phase-3 landings — frontend 815 pass / 24 skip / 0 fail (42
      files), build OK, ESLint 0 errors, backend `themes.validate` PASS. Endorsed Claude-3's vite.config
      timeout consolidation. BUDGET TIGHTENED (not bumped): CSS limit 76KB → 75KB in BOTH bundle-size.test.js
      and phase27-performance.test.jsx (real size 74234B/72.5KB; ~2.5KB headroom — a full reskin trips it,
      forcing a deliberate bump-with-justification rather than silent creep). Both budget files green at 75KB.
- [x] FINAL: regenerated `next-swarm.ps1` as a COMPLETION SENTINEL. The Hardening phase is done, so the old
      script would have regenerated already-complete tasks and spun the stale-task agent loop (lessons #79).
      It now counts unchecked `[ ]` in TASKS.md: 0 → prints "COMPLETE & VERIFIED AT ALL LEVELS" and exits 0
      WITHOUT relaunching; the relaunch path stays functional if open tasks ever exist. Fixed a real
      Windows-PowerShell-5.1 parse failure (UTF-8 em-dash in a no-BOM .ps1 → ANSI mis-decode → bogus
      "missing terminator"; now ASCII-clean, `ParseFile` OK) and a cosmetic lesson-count bug. Ran it: exits 0,
      no relaunch. (New lesson recorded: .ps1 from non-PowerShell tools must be ASCII / UTF-8-with-BOM.)

> Phase 1 is complete and verified. The CSS budget headroom is now ~0.2KB; Phase 2's
> tokenization refactor is the planned structural fix (see next-swarm.ps1).
