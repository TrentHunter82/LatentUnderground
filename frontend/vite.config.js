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
