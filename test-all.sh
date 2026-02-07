#!/usr/bin/env bash
# CI-ready test script: runs both backend and frontend test suites.
# Exit on first failure (strict mode).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXIT_CODE=0

echo "========================================"
echo "  Latent Underground - Full Test Suite"
echo "========================================"
echo ""

# --- Backend Tests ---
echo "[1/2] Running backend tests (pytest)..."
echo "----------------------------------------"
cd "$SCRIPT_DIR/backend"
if uv run pytest --tb=short -q; then
    echo ""
    echo "  Backend tests: PASSED"
else
    echo ""
    echo "  Backend tests: FAILED"
    EXIT_CODE=1
fi
echo ""

# --- Frontend Tests ---
echo "[2/2] Running frontend tests (vitest)..."
echo "----------------------------------------"
cd "$SCRIPT_DIR/frontend"
if npm test; then
    echo ""
    echo "  Frontend tests: PASSED"
else
    echo ""
    echo "  Frontend tests: FAILED"
    EXIT_CODE=1
fi
echo ""

# --- Summary ---
echo "========================================"
if [ $EXIT_CODE -eq 0 ]; then
    echo "  ALL TESTS PASSED"
else
    echo "  SOME TESTS FAILED"
fi
echo "========================================"

exit $EXIT_CODE
