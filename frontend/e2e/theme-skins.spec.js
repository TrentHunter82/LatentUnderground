// @ts-check
import { test, expect } from '@playwright/test';

/**
 * End-to-end coverage for the multi-skin theme system (Phase 1+2).
 *
 * These behaviours CANNOT be exercised in jsdom (lessons #411/#413): the no-flash
 * bootstrap in index.html runs an inline <script> before paint, and the real CSS
 * cascade / data-skin attribute only exist in a true browser. So they live here.
 *
 * Contract (see frontend/src/hooks/useTheme.jsx + index.html bootstrap):
 *   - localStorage 'latent-theme'  ∈ {dark, light, system}        → toggles `.light` on <html>
 *   - localStorage 'latent-skin'   ∈ {analog,obsidian,blueprint,terminal} → <html data-skin="…">
 *   - invalid / missing skin falls back to 'analog'
 *   - skin axis is orthogonal to the light/dark mode axis
 *   - SkinToggle (top bar) cycles analog → obsidian → blueprint → terminal → analog
 */

const SKIN_KEY = 'latent-skin';
const MODE_KEY = 'latent-theme';
const SKIN_ORDER = ['analog', 'obsidian', 'blueprint', 'terminal'];

/**
 * Navigate to the app with the onboarding modal pre-dismissed (via addInitScript so it
 * is set before any page script runs, on every navigation incl. reloads). The skin/mode
 * keys are deliberately NOT seeded here so tests can drive persistence themselves.
 */
async function gotoApp(page) {
  await page.addInitScript(() => {
    try { localStorage.setItem('lu_onboarding_complete', 'true'); } catch { /* ignore */ }
  });
  await page.goto('/');
}

const html = (page) => page.locator('html');
const skinToggle = (page) => page.getByRole('button', { name: /theme skin/i });

/** Open Settings (lazy-loaded, client-side only) and return the ThemePicker radiogroup. */
async function openThemePicker(page) {
  await page.getByRole('button', { name: 'Open settings' }).click();
  const group = page.getByRole('radiogroup', { name: 'Theme skin' });
  await group.waitFor({ state: 'visible' });
  return group;
}

test.describe('Theme skins — no-flash bootstrap', () => {
  test('defaults to the analog skin when nothing is stored', async ({ page }) => {
    await gotoApp(page);
    await page.evaluate((k) => localStorage.removeItem(k), SKIN_KEY);
    await page.reload();
    await expect(html(page)).toHaveAttribute('data-skin', 'analog');
  });

  test('restores a persisted skin on load', async ({ page }) => {
    await gotoApp(page);
    await page.evaluate(([k, v]) => localStorage.setItem(k, v), [SKIN_KEY, 'terminal']);
    await page.reload();
    await expect(html(page)).toHaveAttribute('data-skin', 'terminal');
  });

  test('falls back to analog for an invalid stored skin (bootstrap allowlist)', async ({ page }) => {
    await gotoApp(page);
    await page.evaluate(([k, v]) => localStorage.setItem(k, v), [SKIN_KEY, 'not-a-real-skin']);
    await page.reload();
    await expect(html(page)).toHaveAttribute('data-skin', 'analog');
  });

  test('every registry skin round-trips through the bootstrap', async ({ page }) => {
    await gotoApp(page);
    for (const skin of SKIN_ORDER) {
      await page.evaluate(([k, v]) => localStorage.setItem(k, v), [SKIN_KEY, skin]);
      await page.reload();
      await expect(html(page)).toHaveAttribute('data-skin', skin);
    }
  });
});

test.describe('Theme skins — SkinToggle', () => {
  test('is present in the app shell with an accessible name', async ({ page }) => {
    await gotoApp(page);
    await expect(skinToggle(page)).toBeVisible();
  });

  test('cycles analog → obsidian → blueprint → terminal → analog and wraps', async ({ page }) => {
    await gotoApp(page);
    await page.evaluate((k) => localStorage.removeItem(k), SKIN_KEY);
    await page.reload();
    await expect(html(page)).toHaveAttribute('data-skin', 'analog');

    // One click per remaining skin, ending back at analog (full wrap).
    const expectedAfterEachClick = ['obsidian', 'blueprint', 'terminal', 'analog'];
    for (const expected of expectedAfterEachClick) {
      await skinToggle(page).click();
      await expect(html(page)).toHaveAttribute('data-skin', expected);
    }
  });

  test('persists the chosen skin across a real reload', async ({ page }) => {
    await gotoApp(page);
    await page.evaluate((k) => localStorage.removeItem(k), SKIN_KEY);
    await page.reload();

    await skinToggle(page).click(); // analog → obsidian
    await expect(html(page)).toHaveAttribute('data-skin', 'obsidian');
    expect(await page.evaluate((k) => localStorage.getItem(k), SKIN_KEY)).toBe('obsidian');

    await page.reload(); // gotoApp's init script only sets onboarding — skin must come from storage
    await expect(html(page)).toHaveAttribute('data-skin', 'obsidian');
  });
});

test.describe('Theme skins — orthogonality with light/dark mode', () => {
  test('a skin and a light mode coexist independently', async ({ page }) => {
    await gotoApp(page);
    await page.evaluate(([sk, mk, skin, mode]) => {
      localStorage.setItem(sk, skin);
      localStorage.setItem(mk, mode);
    }, [SKIN_KEY, MODE_KEY, 'terminal', 'light']);
    await page.reload();

    // Both axes applied at once, neither clobbering the other.
    await expect(html(page)).toHaveClass(/light/);
    await expect(html(page)).toHaveAttribute('data-skin', 'terminal');
  });

  test('changing the skin does not disturb the persisted light mode', async ({ page }) => {
    await gotoApp(page);
    await page.evaluate(([mk, mode]) => localStorage.setItem(mk, mode), [MODE_KEY, 'light']);
    await page.reload();
    await expect(html(page)).toHaveClass(/light/);

    await skinToggle(page).click();
    // Mode axis untouched by the skin toggle.
    await expect(html(page)).toHaveClass(/light/);
    expect(await page.evaluate((k) => localStorage.getItem(k), MODE_KEY)).toBe('light');
  });
});

test.describe('Theme skins — ThemePicker radiogroup (Settings → Appearance)', () => {
  test.beforeEach(async ({ page }) => {
    await gotoApp(page);
    await page.evaluate((k) => localStorage.removeItem(k), SKIN_KEY);
    await page.reload();
  });

  test('renders one radio per registry skin, with analog initially checked', async ({ page }) => {
    const group = await openThemePicker(page);
    await expect(group.getByRole('radio')).toHaveCount(SKIN_ORDER.length);
    await expect(group.getByRole('radio', { name: /analog/i })).toHaveAttribute('aria-checked', 'true');
  });

  test('Arrow keys move selection AND focus (WAI-ARIA radiogroup, wrapping)', async ({ page }) => {
    const group = await openThemePicker(page);
    const radio = (name) => group.getByRole('radio', { name });

    // Start from the single tab stop (the checked radio).
    await radio(/analog/i).focus();
    await expect(radio(/analog/i)).toBeFocused();

    // ArrowDown: analog → obsidian — selection, focus, and the live data-skin all advance.
    await page.keyboard.press('ArrowDown');
    await expect(radio(/obsidian/i)).toBeFocused();
    await expect(radio(/obsidian/i)).toHaveAttribute('aria-checked', 'true');
    await expect(radio(/analog/i)).toHaveAttribute('aria-checked', 'false');
    await expect(html(page)).toHaveAttribute('data-skin', 'obsidian');

    // ArrowRight is an alias for ArrowDown: obsidian → blueprint.
    await page.keyboard.press('ArrowRight');
    await expect(radio(/blueprint/i)).toBeFocused();
    await expect(html(page)).toHaveAttribute('data-skin', 'blueprint');

    // ArrowUp: blueprint → obsidian.
    await page.keyboard.press('ArrowUp');
    await expect(radio(/obsidian/i)).toBeFocused();
    await expect(html(page)).toHaveAttribute('data-skin', 'obsidian');

    // ArrowUp wraps past the first entry: obsidian → analog → terminal.
    await page.keyboard.press('ArrowUp'); // → analog
    await expect(html(page)).toHaveAttribute('data-skin', 'analog');
    await page.keyboard.press('ArrowUp'); // wraps → terminal (last)
    await expect(radio(/terminal/i)).toBeFocused();
    await expect(html(page)).toHaveAttribute('data-skin', 'terminal');
  });

  test('Home and End jump to the first and last skin', async ({ page }) => {
    const group = await openThemePicker(page);
    const radio = (name) => group.getByRole('radio', { name });

    await radio(/analog/i).focus();

    await page.keyboard.press('End');
    await expect(radio(/terminal/i)).toBeFocused();
    await expect(html(page)).toHaveAttribute('data-skin', 'terminal');

    await page.keyboard.press('Home');
    await expect(radio(/analog/i)).toBeFocused();
    await expect(html(page)).toHaveAttribute('data-skin', 'analog');
  });

  test('clicking a radio selects that skin and persists it', async ({ page }) => {
    const group = await openThemePicker(page);
    await group.getByRole('radio', { name: /blueprint/i }).click();
    await expect(group.getByRole('radio', { name: /blueprint/i })).toHaveAttribute('aria-checked', 'true');
    await expect(html(page)).toHaveAttribute('data-skin', 'blueprint');
    expect(await page.evaluate((k) => localStorage.getItem(k), SKIN_KEY)).toBe('blueprint');
  });
});

/**
 * Rendered-palette coverage — the one thing jsdom physically cannot check (lesson #446:
 * "jsdom can't compute var() cascades, and no test checks rendered colors").
 *
 * Every test ABOVE asserts the *wiring* (the `data-skin` attribute / `.light` class / radio
 * state). None proves the wiring produces a distinct, painted palette: if a skin's entire
 * token block in index.css were deleted, or a `var(--x)` reference broke, `data-skin="terminal"`
 * would still be set — so every attribute test stays green while the page renders identically
 * to analog. These tests read the resolved cascade off getComputedStyle in a REAL browser and
 * assert each skin paints a distinct, non-empty palette: the regression guard the attribute
 * tests structurally cannot be.
 */
test.describe('Theme skins — rendered palette (real cascade)', () => {
  /**
   * Persist {skin, mode}, reload so the no-flash bootstrap applies them pre-paint, then read
   * the resolved token cascade off <html> plus the rendered body background (a painted value,
   * so a broken var() reference surfaces as transparent/empty rather than a valid color).
   */
  async function readPalette(page, skin, mode) {
    await page.evaluate(
      ([sk, mk, s, m]) => {
        localStorage.setItem(sk, s);
        localStorage.setItem(mk, m);
      },
      [SKIN_KEY, MODE_KEY, skin, mode],
    );
    await page.reload();
    await expect(html(page)).toHaveAttribute('data-skin', skin);
    return page.evaluate(() => {
      const cs = getComputedStyle(document.documentElement);
      const tok = (n) => cs.getPropertyValue(n).trim();
      return {
        bodyBg: tok('--body-bg'),
        panelBg: tok('--panel-bg'),
        panelBorder: tok('--panel-border'),
        accent: tok('--color-crt-green'),
        // Resolved, painted value — empty/transparent here means the cascade never reached
        // a real element (deleted block or broken var reference).
        renderedBodyBg: getComputedStyle(document.body).backgroundColor,
      };
    });
  }

  test('every skin resolves a distinct, non-empty painted palette (dark mode)', async ({ page }) => {
    await gotoApp(page);
    const palettes = {};
    for (const skin of SKIN_ORDER) {
      palettes[skin] = await readPalette(page, skin, 'dark');
    }

    // 1. Every token + the painted background resolves to a real value for every skin.
    for (const skin of SKIN_ORDER) {
      const p = palettes[skin];
      expect(p.bodyBg, `${skin} --body-bg`).not.toBe('');
      expect(p.panelBg, `${skin} --panel-bg`).not.toBe('');
      expect(p.panelBorder, `${skin} --panel-border`).not.toBe('');
      expect(p.accent, `${skin} --color-crt-green`).not.toBe('');
      // A broken/missing block would leave this transparent or unset, not a valid rgb().
      expect(p.renderedBodyBg, `${skin} painted body background`).toMatch(/^rg(b|ba)\(/);
    }

    // 2. The PAINTED background is distinct across all four skins — proves each skin's CSS
    //    block is present AND that the cascade actually reaches the rendered <body>.
    const rendered = SKIN_ORDER.map((s) => palettes[s].renderedBodyBg);
    expect(
      new Set(rendered).size,
      `distinct painted body backgrounds, got: ${rendered.join(' | ')}`,
    ).toBe(SKIN_ORDER.length);

    // 3. The accent token is distinct across all four skins (catches a skin that only
    //    overrode --body-bg but dropped its accent override).
    const accents = SKIN_ORDER.map((s) => palettes[s].accent);
    expect(
      new Set(accents).size,
      `distinct accents, got: ${accents.join(' | ')}`,
    ).toBe(SKIN_ORDER.length);
  });

  test('light mode paints a different background than dark for the same skin', async ({ page }) => {
    await gotoApp(page);
    // Proves the mode axis also reaches the painted cascade, per skin — not just the
    // `.light` class wiring already covered above.
    for (const skin of SKIN_ORDER) {
      const dark = await readPalette(page, skin, 'dark');
      const light = await readPalette(page, skin, 'light');
      expect(
        light.renderedBodyBg,
        `${skin}: light (${light.renderedBodyBg}) must differ from dark (${dark.renderedBodyBg})`,
      ).not.toBe(dark.renderedBodyBg);
    }
  });
});
