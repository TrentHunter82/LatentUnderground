import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: { ...globals.browser, __APP_VERSION__: 'readonly' },
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    rules: {
      'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]' }],
      // React Compiler lint rules are advisory (this project does not run the
      // compiler). Keep them visible as warnings rather than build-breaking
      // errors; the bug-catching classic rules (rules-of-hooks, exhaustive-deps)
      // stay as errors.
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/purity': 'warn',
      'react-hooks/immutability': 'warn',
      'react-hooks/preserve-manual-memoization': 'warn',
      'react-hooks/refs': 'warn',
      'react-hooks/globals': 'warn',
    },
  },
  {
    // Test files & scripts: vitest globals (describe/it/expect/vi/...) and node globals (global).
    // react-refresh (a Vite HMR rule for route components) is irrelevant for test
    // utilities and shared mocks, which legitimately export non-component helpers.
    files: ['**/*.test.{js,jsx}', 'src/test/**/*.{js,jsx}', 'scripts/**/*.js'],
    languageOptions: {
      globals: { ...globals.vitest, ...globals.node },
    },
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
  {
    // Build/test config files and Playwright e2e specs run under Node.
    files: ['*.config.{js,ts}', 'e2e/**/*.{js,ts}', 'playwright.config.{js,ts}'],
    languageOptions: {
      globals: { ...globals.node },
    },
  },
])
