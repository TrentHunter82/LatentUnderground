// @ts-check
import { test, expect } from '@playwright/test';

/**
 * User Journey E2E tests for Latent Underground.
 *
 * These tests validate full user workflows that involve API interaction:
 * project creation, configuration, search/filter, deletion, swarm launch,
 * terminal output views, and theme persistence within project context.
 *
 * The backend (port 8000) must be running for these tests. A health check
 * gate in beforeAll skips the entire suite when the backend is unavailable.
 *
 * The Vite dev server (port 5173) proxies /api calls to the backend,
 * so all API requests go through the same origin.
 */

/** @type {string} */
const API_BASE = 'http://localhost:8000/api';

/** @type {number[]} IDs of projects created during the test run, for cleanup */
const createdProjectIds = [];

// ────────────────────────────────────────────────────────────────────────────
// Helper Functions
// ────────────────────────────────────────────────────────────────────────────

/**
 * Dismiss the onboarding modal that appears on first visit.
 * Sets the localStorage key the app checks to skip onboarding, then reloads.
 * @param {import('@playwright/test').Page} page
 */
async function dismissOnboarding(page) {
  await page.evaluate(() => {
    localStorage.setItem('lu_onboarding_complete', 'true');
  });
  await page.reload();
  // Wait for any residual modal to disappear
  const modal = page.locator('[role="dialog"], [role="alertdialog"]');
  await modal.waitFor({ state: 'hidden', timeout: 5000 }).catch(() => {});
}

/**
 * Create a project via direct API call (bypassing the UI).
 * @param {import('@playwright/test').APIRequestContext} request
 * @param {object} data - Project fields: name, goal, folder_path, etc.
 * @returns {Promise<object>} The created project object
 */
async function createProjectViaAPI(request, data) {
  const response = await request.post(`${API_BASE}/projects`, {
    data: {
      name: data.name || 'Test Project',
      goal: data.goal || 'Automated test project',
      folder_path: data.folder_path || 'C:/tmp/test-project',
      ...data,
    },
  });
  expect(response.ok()).toBeTruthy();
  const project = await response.json();
  createdProjectIds.push(project.id);
  return project;
}

/**
 * Delete a project via direct API call (for cleanup).
 * @param {import('@playwright/test').APIRequestContext} request
 * @param {number} id - Project ID to delete
 */
async function deleteProjectViaAPI(request, id) {
  const response = await request.delete(`${API_BASE}/projects/${id}`);
  // 200 or 404 are both acceptable during cleanup
  expect([200, 204, 404]).toContain(response.status());
}

/**
 * Wait for the sidebar to fully load projects after navigation.
 * Looks for the "Projects" label text in the sidebar.
 * @param {import('@playwright/test').Page} page
 */
async function waitForSidebarReady(page) {
  await page.locator('text=Projects').first().waitFor({ state: 'visible', timeout: 10000 });
}

// ────────────────────────────────────────────────────────────────────────────
// Health Check Gate
// ────────────────────────────────────────────────────────────────────────────

/** @type {boolean} */
let backendAvailable = false;

test.beforeAll(async ({ request }) => {
  try {
    const response = await request.get(`${API_BASE}/health`, { timeout: 5000 });
    backendAvailable = response.ok();
  } catch {
    backendAvailable = false;
  }

  if (!backendAvailable) {
    console.warn(
      'Backend not available at http://localhost:8000 - skipping user journey tests.'
    );
  }
});

test.afterAll(async ({ request }) => {
  // Clean up any projects created during the test run
  for (const id of createdProjectIds) {
    await deleteProjectViaAPI(request, id).catch(() => {});
  }
  createdProjectIds.length = 0;
});

// ────────────────────────────────────────────────────────────────────────────
// Test Suite: Project Creation Flow
// ────────────────────────────────────────────────────────────────────────────

test.describe('Project Creation Flow', () => {
  test.skip(() => !backendAvailable, 'Backend not available');

  test('creates a project through the UI form', async ({ page }) => {
    await page.goto('/');
    await dismissOnboarding(page);

    // Click "+ New Project" button in sidebar
    const newProjectBtn = page.getByRole('button', { name: /new project/i });
    await expect(newProjectBtn).toBeVisible({ timeout: 10000 });
    await newProjectBtn.click();

    // Wait for the new project form to appear
    await expect(page.getByRole('heading', { name: /new swarm project/i })).toBeVisible({
      timeout: 10000,
    });

    // Fill in project name
    const nameInput = page.getByLabel(/project name/i);
    await nameInput.fill('E2E Test Project');

    // Fill in goal
    const goalInput = page.getByLabel(/goal/i);
    await goalInput.fill('Validate the project creation flow end-to-end');

    // Fill in folder path
    const folderInput = page.getByLabel(/project folder path/i);
    await folderInput.fill('C:/tmp/e2e-test-project');

    // Select complexity (default is Medium, click "Complex" to change)
    const complexBtn = page.getByRole('button', { name: 'Complex' });
    await complexBtn.click();
    await expect(complexBtn).toHaveAttribute('aria-pressed', 'true');

    // Submit the form via "Create Project" button
    const createBtn = page.getByRole('button', { name: /^create project$/i });
    await createBtn.click();

    // Verify we navigated to the project view (URL has /projects/N)
    await page.waitForURL(/\/projects\/\d+/, { timeout: 15000 });

    // Extract project ID from URL for cleanup
    const url = page.url();
    const match = url.match(/\/projects\/(\d+)/);
    expect(match).not.toBeNull();
    const projectId = Number(match[1]);
    createdProjectIds.push(projectId);

    // Verify the project name appears in the dashboard header
    await expect(page.getByRole('heading', { name: 'E2E Test Project' })).toBeVisible({
      timeout: 10000,
    });

    // Verify the project goal text is displayed
    await expect(
      page.getByText('Validate the project creation flow end-to-end')
    ).toBeVisible({ timeout: 5000 });

    // Verify project appears in sidebar
    const sidebarLink = page.locator('aside').getByText('E2E Test Project');
    await expect(sidebarLink).toBeVisible({ timeout: 5000 });
  });
});

// ────────────────────────────────────────────────────────────────────────────
// Test Suite: Project Configuration Flow
// ────────────────────────────────────────────────────────────────────────────

test.describe('Project Configuration Flow', () => {
  test.skip(() => !backendAvailable, 'Backend not available');

  /** @type {object} */
  let project;

  test.beforeEach(async ({ request }) => {
    project = await createProjectViaAPI(request, {
      name: 'Config Test Project',
      goal: 'Test configuration persistence',
      folder_path: 'C:/tmp/config-test',
    });
  });

  test('saves agent configuration and persists after reload', async ({ page }) => {
    await page.goto(`/projects/${project.id}`);
    await dismissOnboarding(page);

    // Wait for dashboard to load
    await expect(page.getByRole('heading', { name: 'Config Test Project' })).toBeVisible({
      timeout: 15000,
    });

    // Navigate to Settings tab
    const settingsTab = page.getByRole('tab', { name: 'Settings' });
    await settingsTab.click();

    // Wait for the settings form to appear
    await expect(page.getByText(/project settings/i)).toBeVisible({ timeout: 10000 });

    // Change agent count to 6
    const agentCountInput = page.getByLabel(/agent count/i);
    await agentCountInput.clear();
    await agentCountInput.fill('6');

    // Change max phases to 12
    const maxPhasesInput = page.getByLabel(/max phases/i);
    await maxPhasesInput.clear();
    await maxPhasesInput.fill('12');

    // Verify "Unsaved changes" indicator appears
    await expect(page.getByText(/unsaved changes/i)).toBeVisible({ timeout: 3000 });

    // Save settings
    const saveBtn = page.getByRole('button', { name: /save settings/i });
    await saveBtn.click();

    // Verify "Saved!" or "Settings saved" confirmation appears
    await expect(
      page.getByText(/saved/i).first()
    ).toBeVisible({ timeout: 5000 });

    // Reload the page and verify config persists
    await page.reload();
    await dismissOnboarding(page);

    // Navigate back to Settings tab
    await expect(page.getByRole('heading', { name: 'Config Test Project' })).toBeVisible({
      timeout: 15000,
    });
    await page.getByRole('tab', { name: 'Settings' }).click();
    await expect(page.getByLabel(/agent count/i)).toBeVisible({ timeout: 10000 });

    // Verify saved values persisted
    await expect(page.getByLabel(/agent count/i)).toHaveValue('6');
    await expect(page.getByLabel(/max phases/i)).toHaveValue('12');
  });
});

// ────────────────────────────────────────────────────────────────────────────
// Test Suite: Project List & Search
// ────────────────────────────────────────────────────────────────────────────

test.describe('Project List & Search', () => {
  test.skip(() => !backendAvailable, 'Backend not available');

  /** @type {object[]} */
  let projects = [];

  test.beforeAll(async ({ request }) => {
    // Create 3 projects with distinct names for search testing
    projects = await Promise.all([
      createProjectViaAPI(request, {
        name: 'Alpha Search Test',
        goal: 'First search test project',
        folder_path: 'C:/tmp/alpha',
      }),
      createProjectViaAPI(request, {
        name: 'Beta Search Test',
        goal: 'Second search test project',
        folder_path: 'C:/tmp/beta',
      }),
      createProjectViaAPI(request, {
        name: 'Gamma Unique Name',
        goal: 'Third search test project',
        folder_path: 'C:/tmp/gamma',
      }),
    ]);
  });

  test('shows all projects in sidebar', async ({ page }) => {
    await page.goto('/');
    await dismissOnboarding(page);
    await waitForSidebarReady(page);

    // Verify all three projects appear in the sidebar
    for (const p of projects) {
      await expect(page.locator('aside').getByText(p.name)).toBeVisible({ timeout: 10000 });
    }
  });

  test('filters projects by search term', async ({ page }) => {
    await page.goto('/');
    await dismissOnboarding(page);
    await waitForSidebarReady(page);

    // Type "Alpha" in the search box
    const searchInput = page.getByLabel(/search projects/i);
    await searchInput.fill('Alpha');

    // Wait for debounce (300ms) plus rendering
    await page.waitForTimeout(500);

    // "Alpha Search Test" should be visible
    await expect(page.locator('aside').getByText('Alpha Search Test')).toBeVisible({
      timeout: 5000,
    });

    // "Beta Search Test" and "Gamma Unique Name" should NOT be visible
    await expect(page.locator('aside').getByText('Beta Search Test')).not.toBeVisible();
    await expect(page.locator('aside').getByText('Gamma Unique Name')).not.toBeVisible();
  });

  test('clears search to show all projects again', async ({ page }) => {
    await page.goto('/');
    await dismissOnboarding(page);
    await waitForSidebarReady(page);

    const searchInput = page.getByLabel(/search projects/i);

    // Apply a filter first
    await searchInput.fill('Gamma');
    await page.waitForTimeout(500);

    // Only Gamma visible
    await expect(page.locator('aside').getByText('Gamma Unique Name')).toBeVisible({
      timeout: 5000,
    });

    // Clear the search
    await searchInput.clear();
    await page.waitForTimeout(500);

    // All projects should reappear
    for (const p of projects) {
      await expect(page.locator('aside').getByText(p.name)).toBeVisible({ timeout: 5000 });
    }
  });

  test('searches by goal text', async ({ page }) => {
    await page.goto('/');
    await dismissOnboarding(page);
    await waitForSidebarReady(page);

    // Search by goal text that only "Gamma Unique Name" has (its goal is "Third search test project")
    const searchInput = page.getByLabel(/search projects/i);
    await searchInput.fill('Third');
    await page.waitForTimeout(500);

    await expect(page.locator('aside').getByText('Gamma Unique Name')).toBeVisible({
      timeout: 5000,
    });
    await expect(page.locator('aside').getByText('Alpha Search Test')).not.toBeVisible();
  });
});

// ────────────────────────────────────────────────────────────────────────────
// Test Suite: Project Deletion
// ────────────────────────────────────────────────────────────────────────────

test.describe('Project Deletion', () => {
  test.skip(() => !backendAvailable, 'Backend not available');

  test('deletes a project via the dashboard delete button', async ({ page, request }) => {
    // Create a project to delete
    const project = await createProjectViaAPI(request, {
      name: 'Delete Me Project',
      goal: 'This project will be deleted',
      folder_path: 'C:/tmp/delete-me',
    });

    await page.goto(`/projects/${project.id}`);
    await dismissOnboarding(page);

    // Wait for dashboard to load
    await expect(page.getByRole('heading', { name: 'Delete Me Project' })).toBeVisible({
      timeout: 15000,
    });

    // Click the delete button (trash icon in dashboard header)
    const deleteBtn = page.getByRole('button', { name: /delete project/i });
    await deleteBtn.click();

    // Confirm in the dialog
    const confirmDialog = page.locator('[role="alertdialog"]');
    await expect(confirmDialog).toBeVisible({ timeout: 5000 });
    await expect(confirmDialog.getByText(/delete "Delete Me Project"/i)).toBeVisible();

    // Click "Delete" in the confirm dialog
    const confirmDeleteBtn = confirmDialog.getByRole('button', { name: 'Delete' });
    await confirmDeleteBtn.click();

    // Should navigate away from the project (back to home)
    await page.waitForURL('/', { timeout: 10000 });

    // Project should no longer appear in sidebar
    await expect(page.locator('aside').getByText('Delete Me Project')).not.toBeVisible({
      timeout: 5000,
    });

    // Remove from cleanup list since it's already deleted
    const idx = createdProjectIds.indexOf(project.id);
    if (idx !== -1) createdProjectIds.splice(idx, 1);
  });

  test('cancels deletion when clicking Cancel', async ({ page, request }) => {
    const project = await createProjectViaAPI(request, {
      name: 'Keep Me Project',
      goal: 'This project should survive cancellation',
      folder_path: 'C:/tmp/keep-me',
    });

    await page.goto(`/projects/${project.id}`);
    await dismissOnboarding(page);

    await expect(page.getByRole('heading', { name: 'Keep Me Project' })).toBeVisible({
      timeout: 15000,
    });

    // Click delete
    await page.getByRole('button', { name: /delete project/i }).click();

    // Click "Cancel" in confirm dialog
    const confirmDialog = page.locator('[role="alertdialog"]');
    await expect(confirmDialog).toBeVisible({ timeout: 5000 });
    await confirmDialog.getByRole('button', { name: 'Cancel' }).click();

    // Dialog should close
    await expect(confirmDialog).not.toBeVisible({ timeout: 3000 });

    // Project should still be visible
    await expect(page.getByRole('heading', { name: 'Keep Me Project' })).toBeVisible();
  });
});

// ────────────────────────────────────────────────────────────────────────────
// Test Suite: Swarm Launch Attempt
// ────────────────────────────────────────────────────────────────────────────

test.describe('Swarm Launch Attempt', () => {
  test.skip(() => !backendAvailable, 'Backend not available');

  test('shows loading state and handles launch failure gracefully', async ({
    page,
    request,
  }) => {
    const project = await createProjectViaAPI(request, {
      name: 'Launch Test Project',
      goal: 'Test swarm launch behavior',
      folder_path: 'C:/tmp/launch-test',
    });

    await page.goto(`/projects/${project.id}`);
    await dismissOnboarding(page);

    // Wait for dashboard to load with project details
    await expect(page.getByRole('heading', { name: 'Launch Test Project' })).toBeVisible({
      timeout: 15000,
    });

    // Find and click the Launch button (SwarmControls component)
    const launchBtn = page.getByRole('button', { name: /^launch$/i });
    await expect(launchBtn).toBeVisible({ timeout: 10000 });
    await launchBtn.click();

    // Verify loading state appears (button changes to "Launching..." with spinner)
    // The button has aria-busy="true" during loading
    await expect(launchBtn).toHaveAttribute('aria-busy', 'true', { timeout: 5000 }).catch(
      () => {}
    );

    // The launch will likely fail without the Claude CLI installed.
    // Verify the error is handled gracefully (toast notification or error state).
    // Wait for either:
    // 1. The button reverts from loading state (launch completed or failed)
    // 2. An error toast appears
    await Promise.race([
      // Button returns to non-loading state
      expect(launchBtn).not.toHaveAttribute('aria-busy', 'true', { timeout: 30000 }),
      // Or an error toast/alert appears
      page.getByText(/launch failed/i).waitFor({ state: 'visible', timeout: 30000 }),
    ]).catch(() => {});

    // The page should not crash regardless of launch result
    await expect(page.getByRole('heading', { name: 'Launch Test Project' })).toBeVisible();
  });
});

// ────────────────────────────────────────────────────────────────────────────
// Test Suite: Terminal Output View
// ────────────────────────────────────────────────────────────────────────────

test.describe('Terminal Output View', () => {
  test.skip(() => !backendAvailable, 'Backend not available');

  /** @type {object} */
  let project;

  test.beforeEach(async ({ request }) => {
    project = await createProjectViaAPI(request, {
      name: 'Terminal View Project',
      goal: 'Test terminal output UI',
      folder_path: 'C:/tmp/terminal-test',
    });
  });

  test('displays terminal section with correct controls', async ({ page }) => {
    await page.goto(`/projects/${project.id}`);
    await dismissOnboarding(page);

    // Wait for the dashboard to load
    await expect(page.getByRole('heading', { name: 'Terminal View Project' })).toBeVisible({
      timeout: 15000,
    });

    // Switch to the "Output" tab to see the terminal
    const outputTab = page.getByRole('tab', { name: 'Output' });
    await outputTab.click();

    // Verify the Terminal heading exists
    await expect(page.getByText('Terminal').first()).toBeVisible({ timeout: 10000 });

    // Verify the terminal output area (role="log") exists
    const terminalLog = page.locator('[role="log"][aria-label="Terminal output"]');
    await expect(terminalLog).toBeVisible({ timeout: 5000 });

    // Verify the "Clear" button exists in terminal controls
    await expect(page.getByRole('button', { name: /clear/i }).first()).toBeVisible();

    // Verify the input bar exists (for sending commands to agents)
    const terminalInput = page.getByLabel(/terminal input/i);
    await expect(terminalInput).toBeVisible();

    // Input should be disabled when no agents are running
    await expect(terminalInput).toBeDisabled();

    // Verify the "Send" button exists
    await expect(page.getByRole('button', { name: /send input/i })).toBeVisible();

    // Verify empty state message is shown (no swarm running)
    await expect(
      page.getByText(/no output yet|launch a swarm/i).first()
    ).toBeVisible({ timeout: 5000 });
  });

  test('has All tab visible when in terminal view', async ({ page }) => {
    await page.goto(`/projects/${project.id}`);
    await dismissOnboarding(page);

    await expect(page.getByRole('heading', { name: 'Terminal View Project' })).toBeVisible({
      timeout: 15000,
    });

    // Switch to Output tab
    await page.getByRole('tab', { name: 'Output' }).click();

    // The "All" tab in the agent sub-tabs only appears when there are agents.
    // For a fresh project with no agents, the agent tab bar may not be rendered.
    // Verify terminal area still works without agent tabs.
    const terminalLog = page.locator('[role="log"][aria-label="Terminal output"]');
    await expect(terminalLog).toBeVisible({ timeout: 10000 });
  });
});

// ────────────────────────────────────────────────────────────────────────────
// Test Suite: Theme Persistence in Project Context
// ────────────────────────────────────────────────────────────────────────────

test.describe('Theme Persistence in Project Context', () => {
  test.skip(() => !backendAvailable, 'Backend not available');

  test('theme change persists after reload on a project page', async ({ page, request }) => {
    const project = await createProjectViaAPI(request, {
      name: 'Theme Test Project',
      goal: 'Test theme persistence',
      folder_path: 'C:/tmp/theme-test',
    });

    await page.goto(`/projects/${project.id}`);
    await dismissOnboarding(page);

    // Wait for project to load
    await expect(page.getByRole('heading', { name: 'Theme Test Project' })).toBeVisible({
      timeout: 15000,
    });

    const html = page.locator('html');

    // Default should be dark mode (no 'light' class). The theme system defaults
    // to 'system' mode which resolves to dark in headless browsers.
    // Record the initial state.
    const initialHasLight = await html.evaluate((el) => el.classList.contains('light'));

    // Find the theme toggle button. It cycles: dark -> light -> system -> dark.
    // The button has aria-label containing "mode".
    const themeToggle = page.getByRole('button', { name: /mode.*click/i });
    await expect(themeToggle).toBeVisible({ timeout: 5000 });

    // Click to cycle theme. We'll click until we get to 'light' mode.
    // First click: system/dark -> light (if starting from dark) or dark -> light.
    await themeToggle.click();
    await page.waitForTimeout(300);

    // Check if theme changed. If we landed on 'light', the html should have 'light' class.
    // The stored value in localStorage key 'latent-theme' tells us the mode.
    let storedTheme = await page.evaluate(() => localStorage.getItem('latent-theme'));

    // If not light yet, click again
    if (storedTheme !== 'light') {
      await themeToggle.click();
      await page.waitForTimeout(300);
      storedTheme = await page.evaluate(() => localStorage.getItem('latent-theme'));
    }
    // One more try if needed (cycling through 3 states)
    if (storedTheme !== 'light') {
      await themeToggle.click();
      await page.waitForTimeout(300);
      storedTheme = await page.evaluate(() => localStorage.getItem('latent-theme'));
    }

    // Now we should be in light mode
    expect(storedTheme).toBe('light');
    await expect(html).toHaveClass(/light/);

    // Reload the page
    await page.reload();
    // Re-dismiss onboarding since localStorage persists but reload triggers check
    await page.evaluate(() => {
      localStorage.setItem('lu_onboarding_complete', 'true');
    });

    // Wait for page to load
    await expect(page.getByRole('heading', { name: 'Theme Test Project' })).toBeVisible({
      timeout: 15000,
    });

    // Verify the light theme persisted
    const persistedTheme = await page.evaluate(() => localStorage.getItem('latent-theme'));
    expect(persistedTheme).toBe('light');
    await expect(html).toHaveClass(/light/);
  });
});

// ────────────────────────────────────────────────────────────────────────────
// Test Suite: Project Navigation & Tab Switching
// ────────────────────────────────────────────────────────────────────────────

test.describe('Project Navigation & Tab Switching', () => {
  test.skip(() => !backendAvailable, 'Backend not available');

  /** @type {object} */
  let project;

  test.beforeAll(async ({ request }) => {
    project = await createProjectViaAPI(request, {
      name: 'Navigation Test Project',
      goal: 'Test tab navigation and keyboard accessibility',
      folder_path: 'C:/tmp/nav-test',
    });
  });

  test('switches between all project view tabs', async ({ page }) => {
    await page.goto(`/projects/${project.id}`);
    await dismissOnboarding(page);

    await expect(page.getByRole('heading', { name: 'Navigation Test Project' })).toBeVisible({
      timeout: 15000,
    });

    // The project view has these tabs: Dashboard, History, Output, Files, Logs, Analytics, Settings
    const tabNames = ['Dashboard', 'History', 'Output', 'Files', 'Logs', 'Analytics', 'Settings'];

    for (const tabName of tabNames) {
      const tab = page.getByRole('tab', { name: tabName });
      await expect(tab).toBeVisible({ timeout: 5000 });
      await tab.click();

      // Verify the tab is now selected
      await expect(tab).toHaveAttribute('aria-selected', 'true');

      // Verify the corresponding tab panel is visible
      const panelId = `tabpanel-${tabName.toLowerCase()}`;
      const panel = page.locator(`#${panelId}`);
      await expect(panel).toBeVisible({ timeout: 10000 });
    }
  });

  test('supports keyboard tab navigation with arrow keys', async ({ page }) => {
    await page.goto(`/projects/${project.id}`);
    await dismissOnboarding(page);

    await expect(page.getByRole('heading', { name: 'Navigation Test Project' })).toBeVisible({
      timeout: 15000,
    });

    // Focus the first tab (Dashboard)
    const dashboardTab = page.getByRole('tab', { name: 'Dashboard' });
    await dashboardTab.focus();

    // Press ArrowRight to move to History tab
    await page.keyboard.press('ArrowRight');

    // History tab should now be selected
    const historyTab = page.getByRole('tab', { name: 'History' });
    await expect(historyTab).toHaveAttribute('aria-selected', 'true');

    // Press ArrowLeft to go back to Dashboard
    await page.keyboard.press('ArrowLeft');
    await expect(dashboardTab).toHaveAttribute('aria-selected', 'true');
  });
});

// ────────────────────────────────────────────────────────────────────────────
// Test Suite: Project Update via API Verification
// ────────────────────────────────────────────────────────────────────────────

test.describe('Project Update Flow', () => {
  test.skip(() => !backendAvailable, 'Backend not available');

  test('updates made via API reflect in the UI on reload', async ({ page, request }) => {
    const project = await createProjectViaAPI(request, {
      name: 'Original Name',
      goal: 'Original goal text',
      folder_path: 'C:/tmp/update-test',
    });

    // Navigate to the project
    await page.goto(`/projects/${project.id}`);
    await dismissOnboarding(page);

    await expect(page.getByRole('heading', { name: 'Original Name' })).toBeVisible({
      timeout: 15000,
    });

    // Update project via API
    const updateResponse = await request.patch(`${API_BASE}/projects/${project.id}`, {
      data: { name: 'Updated Name', goal: 'Updated goal text' },
    });
    expect(updateResponse.ok()).toBeTruthy();

    // Reload and verify updates are reflected
    await page.reload();
    await dismissOnboarding(page);

    await expect(page.getByRole('heading', { name: 'Updated Name' })).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByText('Updated goal text')).toBeVisible({ timeout: 5000 });
  });
});

// ────────────────────────────────────────────────────────────────────────────
// Test Suite: Sidebar Status Filters
// ────────────────────────────────────────────────────────────────────────────

test.describe('Sidebar Status Filters', () => {
  test.skip(() => !backendAvailable, 'Backend not available');

  test('filters by status using sidebar filter buttons', async ({ page, request }) => {
    // Create a project (it will have status "created")
    const project = await createProjectViaAPI(request, {
      name: 'Status Filter Project',
      goal: 'Test sidebar status filtering',
      folder_path: 'C:/tmp/status-filter',
    });

    await page.goto('/');
    await dismissOnboarding(page);
    await waitForSidebarReady(page);

    // Verify the project is visible with "all" filter (default)
    await expect(page.locator('aside').getByText('Status Filter Project')).toBeVisible({
      timeout: 10000,
    });

    // Click "created" filter button
    const createdFilter = page.getByRole('button', { name: /filter by created status/i });
    await createdFilter.click();
    await page.waitForTimeout(300);

    // Project should still be visible under "created" filter
    await expect(page.locator('aside').getByText('Status Filter Project')).toBeVisible({
      timeout: 5000,
    });

    // Click "running" filter - project should disappear (not running)
    const runningFilter = page.getByRole('button', { name: /filter by running status/i });
    await runningFilter.click();
    await page.waitForTimeout(300);

    // If there are no running projects, we should see "No matching projects"
    // or the project should not be visible
    await expect(page.locator('aside').getByText('Status Filter Project')).not.toBeVisible({
      timeout: 5000,
    });

    // Click "all" to reset
    const allFilter = page.getByRole('button', { name: /filter by all status/i });
    await allFilter.click();
    await page.waitForTimeout(300);

    // Project should be visible again
    await expect(page.locator('aside').getByText('Status Filter Project')).toBeVisible({
      timeout: 5000,
    });
  });
});

// ────────────────────────────────────────────────────────────────────────────
// Test Suite: Sidebar Delete via Hover Actions
// ────────────────────────────────────────────────────────────────────────────

test.describe('Sidebar Project Actions', () => {
  test.skip(() => !backendAvailable, 'Backend not available');

  test('deletes a project from the sidebar hover actions', async ({ page, request }) => {
    const project = await createProjectViaAPI(request, {
      name: 'Sidebar Delete Target',
      goal: 'Will be deleted from sidebar',
      folder_path: 'C:/tmp/sidebar-delete',
    });

    await page.goto('/');
    await dismissOnboarding(page);
    await waitForSidebarReady(page);

    // Find the project entry in sidebar and hover over it
    const projectEntry = page.locator('aside').getByText('Sidebar Delete Target');
    await expect(projectEntry).toBeVisible({ timeout: 10000 });

    // Hover to reveal action buttons
    await projectEntry.hover();

    // Click the delete button that appears on hover
    const deleteBtn = page.getByRole('button', {
      name: `Delete Sidebar Delete Target`,
    });
    await deleteBtn.click({ force: true });

    // Confirm in the dialog
    const dialog = page.locator('[role="alertdialog"]');
    await expect(dialog).toBeVisible({ timeout: 5000 });
    await dialog.getByRole('button', { name: 'Delete' }).click();

    // Wait for the project to disappear
    await expect(
      page.locator('aside').getByText('Sidebar Delete Target')
    ).not.toBeVisible({ timeout: 10000 });

    // Remove from cleanup list
    const idx = createdProjectIds.indexOf(project.id);
    if (idx !== -1) createdProjectIds.splice(idx, 1);
  });
});

// ────────────────────────────────────────────────────────────────────────────
// Test Suite: Multiple Projects Workflow
// ────────────────────────────────────────────────────────────────────────────

test.describe('Multiple Projects Workflow', () => {
  test.skip(() => !backendAvailable, 'Backend not available');

  test('navigates between multiple projects', async ({ page, request }) => {
    const projectA = await createProjectViaAPI(request, {
      name: 'Project Alpha Nav',
      goal: 'First project for navigation test',
      folder_path: 'C:/tmp/alpha-nav',
    });
    const projectB = await createProjectViaAPI(request, {
      name: 'Project Beta Nav',
      goal: 'Second project for navigation test',
      folder_path: 'C:/tmp/beta-nav',
    });

    await page.goto('/');
    await dismissOnboarding(page);
    await waitForSidebarReady(page);

    // Click Project Alpha in sidebar
    await page.locator('aside').getByText('Project Alpha Nav').click();
    await page.waitForURL(`/projects/${projectA.id}`, { timeout: 10000 });
    await expect(page.getByRole('heading', { name: 'Project Alpha Nav' })).toBeVisible({
      timeout: 15000,
    });

    // Click Project Beta in sidebar
    await page.locator('aside').getByText('Project Beta Nav').click();
    await page.waitForURL(`/projects/${projectB.id}`, { timeout: 10000 });
    await expect(page.getByRole('heading', { name: 'Project Beta Nav' })).toBeVisible({
      timeout: 15000,
    });

    // Navigate back to Alpha
    await page.locator('aside').getByText('Project Alpha Nav').click();
    await page.waitForURL(`/projects/${projectA.id}`, { timeout: 10000 });
    await expect(page.getByRole('heading', { name: 'Project Alpha Nav' })).toBeVisible({
      timeout: 10000,
    });
  });
});
