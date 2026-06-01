import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { visualizer } from 'rollup-plugin-visualizer'
import { readFileSync } from 'fs'

const pkg = JSON.parse(readFileSync('./package.json', 'utf-8'))

export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version || '0.1.0'),
  },
  plugins: [
    react(),
    tailwindcss(),
    visualizer({ filename: 'bundle-stats.html', gzipSize: true, template: 'treemap' }),
  ],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    exclude: ['e2e/**', 'node_modules/**'],
    // Authoritative timeouts (single source of truth). Many suites dynamic-import
    // heavy components (FileEditor, react-markdown, highlight.js) inside test bodies;
    // under full-suite parallel load the shared transform pipeline saturates and a
    // <2s isolated test can stall >15s. A generous ceiling here absorbs that tail
    // deterministically. Genuine hangs (full-App renders) are guarded by describe.skip.
    // NOTE: prefer this over per-test `}, 15000)` args or `vi.setConfig({testTimeout})`
    // — the latter is applied per-worker at runtime and is NOT reliable under parallel
    // load (observed falling back to the 5000ms default). See tasks/lessons.md.
    testTimeout: 30000,
    hookTimeout: 30000,
  },
  build: {
    target: 'es2020',
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('react-router-dom') || id.includes('@remix-run') || id.includes('turbo-stream')) {
              return 'router'
            }
            if (id.includes('highlight.js') || id.includes('rehype-highlight')) {
              return 'highlight'
            }
            if (id.includes('react-markdown') || id.includes('remark-gfm') || id.includes('micromark') || id.includes('mdast') || id.includes('unified') || id.includes('unist') || id.includes('hast')) {
              return 'markdown'
            }
            if (id.includes('@tanstack/react-virtual') || id.includes('@tanstack/virtual-core')) {
              return 'virtual'
            }
            if (id.includes('dockview')) {
              return 'dockview'
            }
          }
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
