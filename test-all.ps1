# test-all.ps1 - Run all backend and frontend tests
# Usage: powershell -ExecutionPolicy Bypass -File test-all.ps1
# Returns non-zero exit code on any failure

$ErrorActionPreference = "Stop"
$failed = $false

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Latent Underground - Full Test Suite  " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Backend tests
Write-Host "[1/3] Running backend tests (pytest)..." -ForegroundColor Yellow
Push-Location backend
try {
    & uv run pytest tests/ -v
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: Backend tests failed" -ForegroundColor Red
        $failed = $true
    } else {
        Write-Host "PASS: Backend tests" -ForegroundColor Green
    }
} catch {
    Write-Host "FAIL: Backend tests errored: $_" -ForegroundColor Red
    $failed = $true
}
Pop-Location
Write-Host ""

# Frontend tests
Write-Host "[2/3] Running frontend tests (vitest)..." -ForegroundColor Yellow
Push-Location frontend
try {
    & npx vitest run
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: Frontend tests failed" -ForegroundColor Red
        $failed = $true
    } else {
        Write-Host "PASS: Frontend tests" -ForegroundColor Green
    }
} catch {
    Write-Host "FAIL: Frontend tests errored: $_" -ForegroundColor Red
    $failed = $true
}
Pop-Location
Write-Host ""

# Frontend build
Write-Host "[3/3] Verifying frontend build..." -ForegroundColor Yellow
Push-Location frontend
try {
    & npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: Frontend build failed" -ForegroundColor Red
        $failed = $true
    } else {
        Write-Host "PASS: Frontend build" -ForegroundColor Green
    }
} catch {
    Write-Host "FAIL: Frontend build errored: $_" -ForegroundColor Red
    $failed = $true
}
Pop-Location
Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Cyan
if ($failed) {
    Write-Host "  RESULT: SOME TESTS FAILED" -ForegroundColor Red
    exit 1
} else {
    Write-Host "  RESULT: ALL TESTS PASSED" -ForegroundColor Green
    exit 0
}
