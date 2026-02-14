import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

/**
 * Creates a fresh QueryClient configured for testing.
 * - retry: false — don't retry failed queries in tests
 * - gcTime: 0 — garbage collect immediately to prevent leaks between tests
 */
export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
    logger: {
      log: () => {},
      warn: () => {},
      error: () => {},
    },
  })
}

/**
 * Wrapper component that provides QueryClientProvider for tests.
 * Usage: render(<TestQueryWrapper><Dashboard /></TestQueryWrapper>)
 */
export function TestQueryWrapper({ children }) {
  const queryClient = createTestQueryClient()
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  )
}

// ============================================================
// Shared TanStack Query Hook Mock Factories
// ============================================================
// Module-level constants ensure stable references (prevents infinite re-renders).
// Use in vi.mock() blocks: vi.mock('../hooks/useProjectQuery', () => mockProjectQueryHooks)
// Override per-test with vi.fn() pattern for configurable hooks.

/** Default project list data */
export const mockProjectsData = [
  { id: 1, name: 'Test Project', goal: 'Test goal', status: 'stopped', config: '{}', created_at: '2025-01-01T00:00:00' },
]

/** Default single project data */
export const mockProjectData = {
  id: 1, name: 'Test Project', goal: 'Test goal', status: 'stopped', config: '{}',
  created_at: '2025-01-01T00:00:00', updated_at: '2025-01-01T00:00:00',
}

/** Default swarm status data */
export const mockSwarmStatusData = {
  project_id: 1, status: 'stopped', swarm_pid: null, process_alive: false,
  agents: [], signals: {}, tasks: { total: 0, done: 0, percent: 0 },
  phase: { Phase: 1, MaxPhases: 3 },
}

/** Default swarm agents data */
export const mockSwarmAgentsData = { agents: [] }

/** Default project stats data */
export const mockProjectStatsData = {
  project_id: 1, total_runs: 0, avg_duration_seconds: null, total_tasks_completed: 0,
}

/** projectKeys factory (matches useProjectQuery.js) */
export const mockProjectKeys = {
  all: ['projects'],
  lists: () => ['projects', 'list'],
  list: (f) => ['projects', 'list', f],
  details: () => ['projects', 'detail'],
  detail: (id) => ['projects', 'detail', id],
  stats: (id) => ['projects', 'detail', id, 'stats'],
  health: (id) => ['projects', 'detail', id, 'health'],
  quota: (id) => ['projects', 'detail', id, 'quota'],
  guardrails: (id) => ['projects', 'detail', id, 'guardrails'],
}

/** templateKeys factory (matches useProjectQuery.js) */
export const mockTemplateKeys = {
  all: ['templates'],
  list: () => ['templates', 'list'],
}

/** swarmKeys factory (matches useSwarmQuery.js) */
export const mockSwarmKeys = {
  all: ['swarm'],
  status: (id) => ['swarm', 'status', id],
  history: (id) => ['swarm', 'history', id],
  agents: (id) => ['swarm', 'agents', id],
  output: (id, f) => ['swarm', 'output', id, f],
  events: (id, f) => ['swarm', 'events', id, f],
  logs: (id) => ['swarm', 'logs', id],
  logSearch: (id, f) => ['swarm', 'logSearch', id, f],
}

/** Default useProjectQuery mock return values (stable references) */
export const mockProjectQueryDefaults = {
  useProjectsResult: { data: mockProjectsData, isLoading: false, error: null },
  useProjectResult: { data: mockProjectData, isLoading: false, error: null, refetch: () => {} },
  useProjectStatsResult: { data: mockProjectStatsData, isLoading: false, error: null },
  useProjectHealthResult: { data: { project_id: 1, crash_rate: 0, status: 'healthy', trend: 'stable', run_count: 0 }, isLoading: false, error: null },
  useProjectQuotaResult: { data: { project_id: 1, quota: {}, usage: {} }, isLoading: false, error: null },
  useProjectGuardrailsResult: { data: null, isLoading: false, error: null },
  useTemplatesResult: { data: [], isLoading: false, error: null },
}

/** Default useSwarmQuery mock return values (stable references) */
export const mockSwarmQueryDefaults = {
  useSwarmStatusResult: { data: mockSwarmStatusData, isLoading: false, error: null },
  useSwarmHistoryResult: { data: { runs: [] }, isLoading: false, error: null },
  useSwarmAgentsResult: { data: mockSwarmAgentsData, isLoading: false, error: null, isSuccess: true },
  useSwarmOutputResult: { data: { lines: [], next_offset: 0, total: 0 }, isLoading: false, error: null },
  useAgentEventsResult: { data: { events: [] }, isLoading: false, error: null },
  useLogsResult: { data: { logs: [] }, isLoading: false, error: null },
  useLogSearchResult: { data: { results: [] }, isLoading: false, error: null },
}

/**
 * Create a useProjectQuery mock object for vi.mock().
 * Usage: vi.mock('../hooks/useProjectQuery', () => createProjectQueryMock())
 * Override: vi.mock('../hooks/useProjectQuery', () => createProjectQueryMock({ useProjects: () => customResult }))
 */
export function createProjectQueryMock(overrides = {}) {
  const d = mockProjectQueryDefaults
  return {
    useProjects: () => d.useProjectsResult,
    useProject: () => d.useProjectResult,
    useProjectStats: () => d.useProjectStatsResult,
    useProjectHealth: () => d.useProjectHealthResult,
    useProjectQuota: () => d.useProjectQuotaResult,
    useProjectGuardrails: () => d.useProjectGuardrailsResult,
    useTemplates: () => d.useTemplatesResult,
    projectKeys: mockProjectKeys,
    templateKeys: mockTemplateKeys,
    ...overrides,
  }
}

/**
 * Create a useSwarmQuery mock object for vi.mock().
 * Usage: vi.mock('../hooks/useSwarmQuery', () => createSwarmQueryMock())
 * Override: vi.mock('../hooks/useSwarmQuery', () => createSwarmQueryMock({ useSwarmStatus: () => customResult }))
 */
export function createSwarmQueryMock(overrides = {}) {
  const d = mockSwarmQueryDefaults
  return {
    useSwarmStatus: () => d.useSwarmStatusResult,
    useSwarmHistory: () => d.useSwarmHistoryResult,
    useSwarmAgents: () => d.useSwarmAgentsResult,
    useSwarmOutput: () => d.useSwarmOutputResult,
    useAgentEvents: () => d.useAgentEventsResult,
    useLogs: () => d.useLogsResult,
    useLogSearch: () => d.useLogSearchResult,
    swarmKeys: mockSwarmKeys,
    ...overrides,
  }
}

// ============================================================
// Shared useMutations Mock Factory
// ============================================================
// Provides all 14 mutation hooks with sensible defaults.
// Use in vi.mock() blocks: vi.mock('../hooks/useMutations', () => createMutationsMock())
// Override per-test: vi.mock('../hooks/useMutations', () => createMutationsMock({ useLaunchSwarm: () => custom }))

const _defaultMutationResult = { mutateAsync: vi.fn(), isPending: false }

/**
 * Create a useMutations mock object for vi.mock().
 * Every exported hook is included with a default { mutateAsync, isPending } return.
 *
 * Usage: vi.mock('../hooks/useMutations', () => createMutationsMock())
 * Override: vi.mock('../hooks/useMutations', () => createMutationsMock({ useLaunchSwarm: () => ({ mutateAsync: vi.fn(), isPending: true }) }))
 */
export function createMutationsMock(overrides = {}) {
  return {
    useCreateProject: () => _defaultMutationResult,
    useUpdateProject: () => _defaultMutationResult,
    useDeleteProject: () => _defaultMutationResult,
    useUpdateProjectConfig: () => _defaultMutationResult,
    useLaunchSwarm: () => _defaultMutationResult,
    useStopSwarm: () => _defaultMutationResult,
    useSendDirective: () => _defaultMutationResult,
    useUpdateAgentPrompt: () => _defaultMutationResult,
    useArchiveProject: () => _defaultMutationResult,
    useUnarchiveProject: () => _defaultMutationResult,
    useStopSwarmAgent: () => _defaultMutationResult,
    useRestartAgent: () => _defaultMutationResult,
    useSendSwarmInput: () => _defaultMutationResult,
    useCreateTemplate: () => _defaultMutationResult,
    ...overrides,
  }
}

// ============================================================
// Shared api.js Mock Factory
// ============================================================
// Provides all 53 api.js exports with sensible defaults.
// Use in vi.mock() blocks: vi.mock('../lib/api', () => createApiMock())
// Override per-test: vi.mock('../lib/api', () => createApiMock({ getProject: vi.fn().mockResolvedValue(custom) }))

/**
 * Create an api.js mock object for vi.mock().
 * Every export from api.js is included with a default vi.fn() implementation.
 * This prevents "not a function" errors when components call unmocked API functions.
 *
 * Usage: vi.mock('../lib/api', () => createApiMock())
 * Override: vi.mock('../lib/api', () => createApiMock({ getProject: vi.fn().mockResolvedValue(myProject) }))
 */
export function createApiMock(overrides = {}) {
  return {
    // Auth
    setApiKey: vi.fn(),
    clearApiKey: vi.fn(),
    getStoredApiKey: vi.fn().mockReturnValue(null),

    // Abort
    createAbortable: vi.fn().mockReturnValue({ signal: undefined, abort: vi.fn() }),

    // Projects
    getProjects: vi.fn().mockResolvedValue([]),
    getProject: vi.fn().mockResolvedValue({}),
    createProject: vi.fn().mockResolvedValue({ id: 1 }),
    updateProject: vi.fn().mockResolvedValue({}),
    deleteProject: vi.fn().mockResolvedValue({}),

    // Swarm control
    launchSwarm: vi.fn().mockResolvedValue({ status: 'launched' }),
    stopSwarm: vi.fn().mockResolvedValue({ status: 'stopped' }),
    getSwarmStatus: vi.fn().mockResolvedValue({ status: 'stopped', agents: [], signals: {}, tasks: { total: 0, done: 0, percent: 0 } }),
    sendSwarmInput: vi.fn().mockResolvedValue({}),
    getSwarmAgents: vi.fn().mockResolvedValue({ agents: [] }),
    stopSwarmAgent: vi.fn().mockResolvedValue({}),

    // Files
    getFile: vi.fn().mockResolvedValue({ content: '', path: '' }),
    putFile: vi.fn().mockResolvedValue({}),

    // Logs
    getLogs: vi.fn().mockResolvedValue({ lines: [] }),
    searchLogs: vi.fn().mockResolvedValue({ results: [] }),

    // Swarm data
    getSwarmHistory: vi.fn().mockResolvedValue({ runs: [] }),
    getSwarmOutput: vi.fn().mockResolvedValue({ lines: [], next_offset: 0, total: 0 }),
    getProjectStats: vi.fn().mockResolvedValue({ total_runs: 0 }),
    updateProjectConfig: vi.fn().mockResolvedValue({}),

    // Directory browsing
    browseDirectory: vi.fn().mockResolvedValue({ entries: [] }),

    // Templates
    getTemplates: vi.fn().mockResolvedValue([]),
    getTemplate: vi.fn().mockResolvedValue({}),
    createTemplate: vi.fn().mockResolvedValue({ id: 1 }),
    updateTemplate: vi.fn().mockResolvedValue({}),
    deleteTemplate: vi.fn().mockResolvedValue({}),

    // Webhooks
    getWebhooks: vi.fn().mockResolvedValue([]),
    createWebhook: vi.fn().mockResolvedValue({ id: 1 }),
    updateWebhook: vi.fn().mockResolvedValue({}),
    deleteWebhook: vi.fn().mockResolvedValue({}),

    // Archival
    archiveProject: vi.fn().mockResolvedValue({}),
    unarchiveProject: vi.fn().mockResolvedValue({}),
    getProjectsWithArchived: vi.fn().mockResolvedValue([]),

    // Agent events & output search
    getAgentEvents: vi.fn().mockResolvedValue({ events: [] }),
    searchSwarmOutput: vi.fn().mockResolvedValue({ results: [] }),
    compareRuns: vi.fn().mockResolvedValue({}),

    // Directives
    sendDirective: vi.fn().mockResolvedValue({}),
    getDirectiveStatus: vi.fn().mockResolvedValue({}),
    updateAgentPrompt: vi.fn().mockResolvedValue({}),
    restartAgent: vi.fn().mockResolvedValue({}),

    // System
    getSystemInfo: vi.fn().mockResolvedValue({}),
    getSystemHealth: vi.fn().mockResolvedValue({ status: 'healthy' }),
    getMetrics: vi.fn().mockResolvedValue(''),
    getHealthTrends: vi.fn().mockResolvedValue({ trends: [] }),

    // Project health/quota/guardrails
    getProjectHealth: vi.fn().mockResolvedValue({ status: 'healthy' }),
    getProjectQuota: vi.fn().mockResolvedValue({}),
    getProjectGuardrails: vi.fn().mockResolvedValue(null),

    // Run checkpoints
    getRunCheckpoints: vi.fn().mockResolvedValue({ checkpoints: [] }),

    // Agent logs & output tail
    getAgentLogs: vi.fn().mockResolvedValue({ lines: [], total_lines: 0 }),
    getOutputTail: vi.fn().mockResolvedValue({ lines: [], total: 0 }),

    // Watch
    startWatch: vi.fn().mockResolvedValue({}),
    stopWatch: vi.fn().mockResolvedValue({}),

    ...overrides,
  }
}
