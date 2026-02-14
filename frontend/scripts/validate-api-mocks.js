/**
 * validate-api-mocks.js
 *
 * Compares exports from src/lib/api.js against keys in createApiMock()
 * from src/test/test-utils.jsx. Reports drift and exits non-zero if
 * the two sets are out of sync.
 *
 * Usage: node scripts/validate-api-mocks.js
 */

import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(__dirname, '..')

// ---------------------------------------------------------------------------
// 1. Extract exported names from api.js
// ---------------------------------------------------------------------------

const apiSource = readFileSync(resolve(ROOT, 'src/lib/api.js'), 'utf-8')

const apiExports = new Set()

// Match:  export function NAME(
//         export const NAME =
//         export { NAME }           (not currently used but future-proof)
const exportPatterns = [
  /export\s+function\s+(\w+)\s*\(/g,
  /export\s+const\s+(\w+)\s*=/g,
  /export\s+let\s+(\w+)\s*=/g,
  /export\s+var\s+(\w+)\s*=/g,
]

for (const re of exportPatterns) {
  let m
  while ((m = re.exec(apiSource)) !== null) {
    apiExports.add(m[1])
  }
}

// ---------------------------------------------------------------------------
// 2. Extract keys from createApiMock() in test-utils.jsx
// ---------------------------------------------------------------------------

const testUtilsSource = readFileSync(
  resolve(ROOT, 'src/test/test-utils.jsx'),
  'utf-8',
)

// Locate the body of createApiMock — from "return {" to the matching "}"
// We find the function, then extract the object literal it returns.
const fnStart = testUtilsSource.indexOf('export function createApiMock')
if (fnStart === -1) {
  console.error('ERROR: Could not find createApiMock in test-utils.jsx')
  process.exit(2)
}

const returnIdx = testUtilsSource.indexOf('return {', fnStart)
if (returnIdx === -1) {
  console.error(
    'ERROR: Could not find "return {" inside createApiMock in test-utils.jsx',
  )
  process.exit(2)
}

// Walk from the opening brace to find the matching closing brace
const braceStart = testUtilsSource.indexOf('{', returnIdx)
let depth = 0
let braceEnd = -1
for (let i = braceStart; i < testUtilsSource.length; i++) {
  if (testUtilsSource[i] === '{') depth++
  else if (testUtilsSource[i] === '}') {
    depth--
    if (depth === 0) {
      braceEnd = i
      break
    }
  }
}

if (braceEnd === -1) {
  console.error('ERROR: Could not find matching closing brace for createApiMock return object')
  process.exit(2)
}

const objectBody = testUtilsSource.slice(braceStart + 1, braceEnd)

const mockKeys = new Set()

// Match bare identifier keys:  someKey: vi.fn()
// Skip ...overrides and comment lines
const keyPattern = /^\s*(\w+)\s*:/gm
let km
while ((km = keyPattern.exec(objectBody)) !== null) {
  mockKeys.add(km[1])
}

// ---------------------------------------------------------------------------
// 3. Compare
// ---------------------------------------------------------------------------

const missingFromMock = [...apiExports].filter((k) => !mockKeys.has(k)).sort()
const extraInMock = [...mockKeys].filter((k) => !apiExports.has(k)).sort()

console.log(`api.js exports:       ${apiExports.size}`)
console.log(`createApiMock keys:   ${mockKeys.size}`)
console.log()

let drifted = false

if (missingFromMock.length > 0) {
  drifted = true
  console.log(
    `MISSING from createApiMock (${missingFromMock.length}):`,
  )
  for (const name of missingFromMock) {
    console.log(`  - ${name}`)
  }
  console.log()
}

if (extraInMock.length > 0) {
  drifted = true
  console.log(
    `EXTRA in createApiMock (not exported by api.js) (${extraInMock.length}):`,
  )
  for (const name of extraInMock) {
    console.log(`  - ${name}`)
  }
  console.log()
}

if (drifted) {
  console.log('FAIL: api.js exports and createApiMock are out of sync.')
  process.exit(1)
} else {
  console.log('OK: api.js exports and createApiMock keys are in sync.')
  process.exit(0)
}
