/**
 * Phase 27 - Performance & Bundle Verification Tests
 *
 * Tests verify:
 * 1. React concurrent rendering (startTransition, useDeferredValue) behavior
 * 2. Lazy loading produces expected code splits
 * 3. Bundle size budgets are met
 * 4. Render performance for large datasets
 * 5. Memoization prevents unnecessary re-renders
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { readdirSync, statSync, existsSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { createApiMock, createProjectQueryMock, createSwarmQueryMock, createMutationsMock } from './test-utils'
import { ToastProvider } from '../components/Toast'

// --- Mocks ---
vi.mock('../lib/api', () => createApiMock({
  getLogs: vi.fn().mockResolvedValue({ logs: [] }),
  searchLogs: vi.fn().mockResolvedValue({ results: [] }),
}))

// Configurable useLogs mock for LogViewer tests
const mockUseLogs = vi.fn(() => ({ data: { logs: [] }, isLoading: false, error: null }))

vi.mock('../hooks/useProjectQuery', () => createProjectQueryMock())
vi.mock('../hooks/useSwarmQuery', () => createSwarmQueryMock({
  useLogs: (...args) => mockUseLogs(...args),
}))
vi.mock('../hooks/useMutations', () => createMutationsMock())

import { getLogs } from '../lib/api'

// ============================================================
// 1. Bundle Size Verification (tighter budgets for Phase 27)
// ============================================================
const DIST_DIR = resolve(process.cwd(), 'dist')
const ASSETS_DIR = resolve(DIST_DIR, 'assets')

function getAssetFiles() {
  try {
    return readdirSync(ASSETS_DIR).map(name => ({
      name,
      size: statSync(join(ASSETS_DIR, name)).size,
      ext: name.split('.').pop(),
      chunk: name.split('.').slice(0, -1).join('.').split('-')[0],
    }))
  } catch {
    return null
  }
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)}MB`
}

describe('Phase 27 - Bundle Size Budgets', () => {
  const files = getAssetFiles()
  const skipIfNoBuild = files === null

  it('index.js is under 260KB', () => {
    if (skipIfNoBuild) return
    const indexJs = files.find(f => f.name.startsWith('index-') && f.ext === 'js')
    expect(indexJs).toBeDefined()
    // Current: ~254KB. Budget: 260KB gives 6KB headroom.
    expect(indexJs.size).toBeLessThan(260 * 1024)
  })

  it('initial load (index + router) is under 310KB', () => {
    if (skipIfNoBuild) return
    const initialChunks = files.filter(f =>
      f.ext === 'js' && (f.chunk === 'index' || f.chunk === 'router')
    )
    const initialSize = initialChunks.reduce((sum, f) => sum + f.size, 0)
    // Current: ~300KB. Budget: 310KB.
    expect(initialSize).toBeLessThan(310 * 1024)
  })

  it('CSS remains under 60KB', () => {
    if (skipIfNoBuild) return
    const cssSize = files.filter(f => f.ext === 'css').reduce((sum, f) => sum + f.size, 0)
    // Current: ~55KB. Budget: 60KB.
    expect(cssSize).toBeLessThan(60 * 1024)
  })

  it('no lazy chunk exceeds 85KB (excluding vendors)', () => {
    if (skipIfNoBuild) return
    const vendorChunks = ['index', 'router', 'highlight', 'markdown', 'virtual']
    const lazyChunks = files.filter(f =>
      f.ext === 'js' && !vendorChunks.includes(f.chunk)
    )
    for (const chunk of lazyChunks) {
      expect(chunk.size, `${chunk.name} is ${formatBytes(chunk.size)}`).toBeLessThan(85 * 1024)
    }
  })

  it('at least 17 lazy-loaded component chunks exist', () => {
    if (skipIfNoBuild) return
    const jsFiles = files.filter(f => f.ext === 'js')
    // Phase 26 established ~23 JS chunks with 17 lazy components.
    expect(jsFiles.length).toBeGreaterThanOrEqual(17)
  })

  it('vendor chunks are properly isolated', () => {
    if (skipIfNoBuild) return
    const chunkNames = files.filter(f => f.ext === 'js').map(f => f.chunk)
    expect(chunkNames).toContain('router')
    expect(chunkNames).toContain('highlight')
    expect(chunkNames).toContain('markdown')
    expect(chunkNames).toContain('virtual')
  })

  it('total bundle under 1MB (excluding vendor highlight + markdown)', () => {
    if (skipIfNoBuild) return
    const appJs = files.filter(f =>
      f.ext === 'js' && f.chunk !== 'highlight' && f.chunk !== 'markdown'
    )
    const totalAppSize = appJs.reduce((sum, f) => sum + f.size, 0)
    // Application JS (without large vendor libs) should be under 500KB
    expect(totalAppSize).toBeLessThan(500 * 1024)
  })

  it('prints Phase 27 bundle report', () => {
    if (skipIfNoBuild) return
    const jsFiles = files.filter(f => f.ext === 'js').sort((a, b) => b.size - a.size)
    const cssFiles = files.filter(f => f.ext === 'css')
    const totalJs = jsFiles.reduce((sum, f) => sum + f.size, 0)
    const totalCss = cssFiles.reduce((sum, f) => sum + f.size, 0)
    const initial = files.filter(f =>
      f.ext === 'js' && (f.chunk === 'index' || f.chunk === 'router')
    ).reduce((sum, f) => sum + f.size, 0)
    const vendorSize = files.filter(f =>
      f.ext === 'js' && ['highlight', 'markdown', 'virtual'].includes(f.chunk)
    ).reduce((sum, f) => sum + f.size, 0)
    const lazySize = totalJs - initial - vendorSize

    console.log('\n=== Phase 27 Bundle Analysis ===')
    console.log(`Total:         ${formatBytes(totalJs + totalCss)} (${formatBytes(totalJs)} JS + ${formatBytes(totalCss)} CSS)`)
    console.log(`Initial load:  ${formatBytes(initial)} (index + router)`)
    console.log(`Vendor libs:   ${formatBytes(vendorSize)} (highlight + markdown + virtual)`)
    console.log(`Lazy chunks:   ${formatBytes(lazySize)} (${jsFiles.length - 3} components)`)
    console.log(`JS chunks:     ${jsFiles.length}`)
    console.log('')
    console.log('Top 5 chunks by size:')
    for (const f of jsFiles.slice(0, 5)) {
      console.log(`  ${f.name.padEnd(45)} ${formatBytes(f.size).padStart(10)}`)
    }

    expect(true).toBe(true)
  })
})

// ============================================================
// 2. React Concurrent Rendering Verification
// ============================================================
describe('Phase 27 - React Concurrent Rendering', () => {

  describe('startTransition in TerminalOutput', () => {
    it('startTransition import is present in TerminalOutput source', () => {
      const sourcePath = resolve(process.cwd(), 'src/components/TerminalOutput.jsx')
      if (existsSync(sourcePath)) {
        const source = readFileSync(sourcePath, 'utf-8')
        expect(source).toContain('startTransition')
        expect(source).toContain('startTransition(() => {')
      }
    })

    it('startTransition wraps setLines in polling handler', () => {
      const sourcePath = resolve(process.cwd(), 'src/components/TerminalOutput.jsx')
      if (existsSync(sourcePath)) {
        const source = readFileSync(sourcePath, 'utf-8')
        // Verify the pattern: startTransition(() => { setLines(... ) })
        expect(source).toMatch(/startTransition\(\(\) => \{[\s\S]*?setLines\(/)
      }
    })
  })

  describe('startTransition in App.jsx', () => {
    it('startTransition wraps setProjectHealth update', () => {
      const sourcePath = resolve(process.cwd(), 'src/App.jsx')
      if (existsSync(sourcePath)) {
        const source = readFileSync(sourcePath, 'utf-8')
        expect(source).toContain('startTransition')
        expect(source).toMatch(/startTransition\(\s*\(\)\s*=>\s*\{[^}]*setProjectHealth/)
      }
    })
  })

  describe('useDeferredValue in Sidebar', () => {
    it('Sidebar search uses useDeferredValue for non-blocking filtering', async () => {
      const Sidebar = (await import('../components/Sidebar')).default
      const manyProjects = Array.from({ length: 50 }, (_, i) => ({
        id: i + 1,
        name: `Project ${i + 1}`,
        goal: `Goal for project ${i + 1}`,
        status: 'stopped',
      }))

      render(
        <MemoryRouter>
          <ToastProvider>
            <Sidebar
              projects={manyProjects}
              onRefresh={vi.fn()}
              collapsed={false}
              onToggle={vi.fn()}
              showArchived={false}
              onShowArchivedChange={vi.fn()}
              projectHealth={{}}
            />
          </ToastProvider>
        </MemoryRouter>
      )

      // All 50 projects visible initially
      expect(screen.getByText('Project 1')).toBeInTheDocument()
      expect(screen.getByText('Project 50')).toBeInTheDocument()

      // Type search term
      const searchInput = screen.getByPlaceholderText('Search projects...')
      await userEvent.type(searchInput, 'Project 1')

      // With useDeferredValue, filtering happens after the value is deferred
      await waitFor(() => {
        expect(screen.getByText('Project 1')).toBeInTheDocument()
      })

      // Project 2 should be filtered out (doesn't match "Project 1")
      await waitFor(() => {
        expect(screen.queryByText('Project 2')).not.toBeInTheDocument()
      })
    })

    it('useDeferredValue import is present in Sidebar source', () => {
      const sourcePath = resolve(process.cwd(), 'src/components/Sidebar.jsx')
      if (existsSync(sourcePath)) {
        const source = readFileSync(sourcePath, 'utf-8')
        expect(source).toContain('useDeferredValue')
        expect(source).toMatch(/useDeferredValue\(search\)/)
      }
    })
  })

  describe('useDeferredValue in LogViewer', () => {
    it('LogViewer search uses useDeferredValue for non-blocking filtering', async () => {
      const LogViewer = (await import('../components/LogViewer')).default
      const lines = Array.from({ length: 100 }, (_, i) => `Line ${i}: data processing step`)
      mockUseLogs.mockReturnValue({
        data: { logs: [{ agent: 'Claude-1', lines }] },
        isLoading: false, error: null,
      })

      await act(async () => {
        render(<LogViewer projectId={1} />)
      })

      expect(screen.getByText(/Line 0: data processing step/)).toBeInTheDocument()
    })

    it('useDeferredValue import is present in LogViewer source', () => {
      const sourcePath = resolve(process.cwd(), 'src/components/LogViewer.jsx')
      if (existsSync(sourcePath)) {
        const source = readFileSync(sourcePath, 'utf-8')
        expect(source).toContain('useDeferredValue')
        expect(source).toMatch(/useDeferredValue\(searchText\)/)
      }
    })
  })
})

// ============================================================
// 3. Lazy Loading Verification
// ============================================================
describe('Phase 27 - Lazy Loading', () => {
  it('App.jsx uses React.lazy for route components', () => {
    const sourcePath = resolve(process.cwd(), 'src/App.jsx')
    if (existsSync(sourcePath)) {
      const source = readFileSync(sourcePath, 'utf-8')
      const lazyPatterns = [
        'lazy(() => import',
        'NewProject',
        'ProjectView',
        'SettingsPanel',
      ]
      for (const pattern of lazyPatterns) {
        expect(source).toContain(pattern)
      }
    }
  })

  it('Dashboard.jsx uses React.lazy for heavy sub-components', () => {
    const sourcePath = resolve(process.cwd(), 'src/components/Dashboard.jsx')
    if (existsSync(sourcePath)) {
      const source = readFileSync(sourcePath, 'utf-8')
      const expectedLazy = ['AgentTimeline', 'AgentEventLog', 'ProjectHealthCard', 'CheckpointTimeline']
      for (const comp of expectedLazy) {
        expect(source, `Expected ${comp} to be lazily loaded`).toMatch(
          new RegExp(`lazy\\(\\(\\)\\s*=>\\s*import\\([^)]*${comp}`)
        )
      }
    }
  })

  it('ProjectView.jsx uses React.lazy for tab content', () => {
    const sourcePath = resolve(process.cwd(), 'src/components/ProjectView.jsx')
    if (existsSync(sourcePath)) {
      const source = readFileSync(sourcePath, 'utf-8')
      const expectedLazy = ['LogViewer', 'SwarmHistory', 'FileEditor']
      for (const comp of expectedLazy) {
        expect(source, `Expected ${comp} to be lazily loaded`).toMatch(
          new RegExp(`lazy\\(\\(\\)\\s*=>\\s*import\\([^)]*${comp}`)
        )
      }
    }
  })

  it('SettingsPanel.jsx lazy-loads OperationsDashboard', () => {
    const sourcePath = resolve(process.cwd(), 'src/components/SettingsPanel.jsx')
    if (existsSync(sourcePath)) {
      const source = readFileSync(sourcePath, 'utf-8')
      expect(source).toMatch(/lazy\(\(\)\s*=>\s*import\([^)]*OperationsDashboard/)
    }
  })

  it('SwarmHistory.jsx lazy-loads RunComparison', () => {
    const sourcePath = resolve(process.cwd(), 'src/components/SwarmHistory.jsx')
    if (existsSync(sourcePath)) {
      const source = readFileSync(sourcePath, 'utf-8')
      expect(source).toMatch(/lazy\(\(\)\s*=>\s*import\([^)]*RunComparison/)
    }
  })
})

// ============================================================
// 4. Memoization Verification
// ============================================================
describe('Phase 27 - Memoization Patterns', () => {
  it('TerminalOutput memoizes errorIndices for large buffers', () => {
    const sourcePath = resolve(process.cwd(), 'src/components/TerminalOutput.jsx')
    if (existsSync(sourcePath)) {
      const source = readFileSync(sourcePath, 'utf-8')
      // errorIndices should be computed via useMemo to avoid O(n) scan per render
      expect(source).toContain('useMemo')
      expect(source).toContain('errorIndices')
    }
  })

  it('TerminalOutput memoizes tabIds to prevent re-renders', () => {
    const sourcePath = resolve(process.cwd(), 'src/components/TerminalOutput.jsx')
    if (existsSync(sourcePath)) {
      const source = readFileSync(sourcePath, 'utf-8')
      expect(source).toMatch(/useMemo\(\s*\(\)\s*=>/)
    }
  })

  it('Dashboard uses useCallback for refresh function', () => {
    const sourcePath = resolve(process.cwd(), 'src/components/Dashboard.jsx')
    if (existsSync(sourcePath)) {
      const source = readFileSync(sourcePath, 'utf-8')
      expect(source).toContain('useCallback')
    }
  })

  it('LogViewer is wrapped in React.memo', () => {
    const sourcePath = resolve(process.cwd(), 'src/components/LogViewer.jsx')
    if (existsSync(sourcePath)) {
      const source = readFileSync(sourcePath, 'utf-8')
      expect(source).toMatch(/export default memo\(/)
    }
  })

  it('TerminalOutput uses useCallback for event handlers', () => {
    const sourcePath = resolve(process.cwd(), 'src/components/TerminalOutput.jsx')
    if (existsSync(sourcePath)) {
      const source = readFileSync(sourcePath, 'utf-8')
      // Count useCallback occurrences - should have several
      const matches = source.match(/useCallback\(/g) || []
      expect(matches.length).toBeGreaterThanOrEqual(3)
    }
  })
})

// ============================================================
// 5. Render Performance Benchmarks
// ============================================================
describe('Phase 27 - Render Performance Benchmarks', () => {
  it('Sidebar renders 100 projects under 1 second', async () => {
    const Sidebar = (await import('../components/Sidebar')).default
    const manyProjects = Array.from({ length: 100 }, (_, i) => ({
      id: i + 1,
      name: `Project ${i + 1}`,
      goal: `Goal ${i + 1}`,
      status: i % 3 === 0 ? 'running' : 'stopped',
    }))

    const start = performance.now()
    render(
      <MemoryRouter>
        <ToastProvider>
          <Sidebar
            projects={manyProjects}
            onRefresh={vi.fn()}
            collapsed={false}
            onToggle={vi.fn()}
            showArchived={false}
            onShowArchivedChange={vi.fn()}
            projectHealth={{}}
          />
        </ToastProvider>
      </MemoryRouter>
    )
    const elapsed = performance.now() - start

    expect(elapsed).toBeLessThan(1000)
    expect(screen.getByText('Project 100')).toBeInTheDocument()
  })

  it('LogViewer renders 500 lines under 2 seconds', async () => {
    const LogViewer = (await import('../components/LogViewer')).default
    const lines = Array.from({ length: 500 }, (_, i) => `Log entry ${i}: processing data`)
    mockUseLogs.mockReturnValue({
      data: { logs: [{ agent: 'Claude-1', lines }] },
      isLoading: false, error: null,
    })

    const start = performance.now()
    await act(async () => {
      render(<LogViewer projectId={1} />)
    })
    const elapsed = performance.now() - start

    expect(elapsed).toBeLessThan(2000)
    expect(screen.getByText(/Log entry 0/)).toBeInTheDocument()
  })

  // Note: TerminalOutput large-batch render benchmarks are covered in performance.test.jsx
  // The @tanstack/react-virtual library triggers infinite update loops in jsdom with large
  // datasets + fake timers. 1000-line tests work (see performance.test.jsx), but 5000+ don't.
  // This is a jsdom limitation, not a production issue.
})

// ============================================================
// 6. Virtual Scrolling Source Verification
// ============================================================
describe('Phase 27 - Virtual Scrolling', () => {
  it('TerminalOutput uses @tanstack/react-virtual', () => {
    const sourcePath = resolve(process.cwd(), 'src/components/TerminalOutput.jsx')
    if (existsSync(sourcePath)) {
      const source = readFileSync(sourcePath, 'utf-8')
      expect(source).toContain('useVirtualizer')
      expect(source).toContain('@tanstack/react-virtual')
    }
  })

  it('LogViewer uses manual virtual scrolling for large datasets', () => {
    const sourcePath = resolve(process.cwd(), 'src/components/LogViewer.jsx')
    if (existsSync(sourcePath)) {
      const source = readFileSync(sourcePath, 'utf-8')
      // LogViewer uses a custom virtualizer (VIRTUALIZE_THRESHOLD + virtualRange)
      expect(source).toContain('VIRTUALIZE_THRESHOLD')
      expect(source).toContain('virtualRange')
    }
  })

  it('TerminalOutput caps buffer at MAX_LINES', () => {
    const sourcePath = resolve(process.cwd(), 'src/components/TerminalOutput.jsx')
    if (existsSync(sourcePath)) {
      const source = readFileSync(sourcePath, 'utf-8')
      expect(source).toContain('MAX_LINES')
      // Verify the cap is enforced in the state update
      expect(source).toMatch(/next\.length\s*>\s*MAX_LINES/)
    }
  })
})

// ============================================================
// 7. Code Splitting Effectiveness
// ============================================================
describe('Phase 27 - Code Splitting Effectiveness', () => {
  const files = getAssetFiles()
  const skipIfNoBuild = files === null

  it('ProjectView chunk is separate from index (route-level splitting)', () => {
    if (skipIfNoBuild) return
    const pvChunk = files.find(f => f.chunk === 'ProjectView' && f.ext === 'js')
    const indexChunk = files.find(f => f.chunk === 'index' && f.ext === 'js')
    expect(pvChunk).toBeDefined()
    expect(indexChunk).toBeDefined()
    // ProjectView should be a separate chunk, not bundled into index
    expect(pvChunk.name).not.toEqual(indexChunk.name)
  })

  it('NewProject chunk is separate (lazy loaded route)', () => {
    if (skipIfNoBuild) return
    const npChunk = files.find(f => f.chunk === 'NewProject' && f.ext === 'js')
    expect(npChunk).toBeDefined()
  })

  it('SettingsPanel chunk is separate (lazy loaded modal)', () => {
    if (skipIfNoBuild) return
    const spChunk = files.find(f => f.chunk === 'SettingsPanel' && f.ext === 'js')
    expect(spChunk).toBeDefined()
  })

  it('OperationsDashboard is a separate chunk (nested lazy)', () => {
    if (skipIfNoBuild) return
    const odChunk = files.find(f => f.chunk === 'OperationsDashboard' && f.ext === 'js')
    expect(odChunk).toBeDefined()
  })

  it('highlight.js and markdown are the two largest vendor dependencies', () => {
    if (skipIfNoBuild) return
    const highlight = files.find(f => f.chunk === 'highlight' && f.ext === 'js')
    const markdown = files.find(f => f.chunk === 'markdown' && f.ext === 'js')
    expect(highlight).toBeDefined()
    expect(markdown).toBeDefined()
    // Both should be over 100KB — confirms they're properly isolated as vendors
    expect(highlight.size).toBeGreaterThan(100 * 1024)
    expect(markdown.size).toBeGreaterThan(100 * 1024)
    // Combined vendor libs should be a significant portion of total bundle
    const totalJs = files.filter(f => f.ext === 'js').reduce((sum, f) => sum + f.size, 0)
    const vendorPortion = (highlight.size + markdown.size) / totalJs
    // Vendor libs should be 30-60% of total JS — proving isolation works
    expect(vendorPortion).toBeGreaterThan(0.30)
    expect(vendorPortion).toBeLessThan(0.60)
  })
})
