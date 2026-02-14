#!/usr/bin/env python3
"""Pre-flight validation script for Latent Underground.

Runs 5 checks to catch drift issues before they become test failures.
Suitable for CI or manual pre-commit usage.

Usage:
    uv run python scripts/pre_checks.py
"""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

passed = 0
failed = 0
warnings = 0
_checks: list = []


def check(name: str):
    """Decorator to register a check function."""
    def decorator(fn):
        _checks.append((name, fn))
        return fn
    return decorator


def run_checks():
    """Execute all registered checks."""
    global passed, failed, warnings
    for name, fn in _checks:
        print(f"\n{'='*60}")
        print(f"CHECK: {name}")
        print(f"{'='*60}")
        try:
            result = fn()
            if result is True:
                print(f"  PASS")
                passed += 1
            elif result == "warn":
                print(f"  WARN (non-blocking)")
                warnings += 1
            else:
                print(f"  FAIL")
                failed += 1
        except Exception as e:
            print(f"  FAIL (exception: {e})")
            failed += 1


# ---------------------------------------------------------------------------
# Check 1: api.js exports match createApiMock() keys
# ---------------------------------------------------------------------------
@check("api.js exports match createApiMock() keys")
def check_mock_sync():
    script = FRONTEND / "scripts" / "validate-api-mocks.js"
    if not script.exists():
        print("  validate-api-mocks.js not found — skipping")
        return "warn"

    result = subprocess.run(
        ["node", str(script)],
        cwd=str(FRONTEND),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  {result.stdout.strip()}")
        if result.stderr.strip():
            print(f"  {result.stderr.strip()}")
        return False
    print(f"  {result.stdout.strip()}")
    return True


# ---------------------------------------------------------------------------
# Check 2: All test files that mock api.js use createApiMock()
# ---------------------------------------------------------------------------
@check("All test files use createApiMock() for api.js mocks")
def check_mock_pattern():
    test_dir = FRONTEND / "src" / "test"
    if not test_dir.exists():
        print("  Test directory not found — skipping")
        return "warn"

    # Pattern: vi.mock('../lib/api' or "../../lib/api") with inline factory NOT using createApiMock
    old_pattern = re.compile(
        r"""vi\.mock\(\s*['"]\.\./(lib/api|\.\.?/lib/api)['"]\s*,\s*\(\)\s*=>\s*\(\s*\{""",
    )
    create_pattern = re.compile(r"createApiMock")

    violations = []
    for test_file in sorted(test_dir.glob("*.test.jsx")):
        content = test_file.read_text(encoding="utf-8", errors="replace")
        # Find vi.mock calls for api.js
        if "vi.mock" in content and "/api" in content:
            # Check if it uses the old inline pattern without createApiMock
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                if old_pattern.search(line) and not create_pattern.search(line):
                    violations.append(f"  {test_file.name}:{i}")

    if violations:
        print(f"  {len(violations)} file(s) use inline api.js mocks instead of createApiMock():")
        for v in violations:
            print(v)
        return False

    # Count how many test files mock api.js at all
    mock_count = 0
    for test_file in sorted(test_dir.glob("*.test.jsx")):
        content = test_file.read_text(encoding="utf-8", errors="replace")
        if "vi.mock" in content and "/api" in content:
            mock_count += 1

    print(f"  {mock_count} test files mock api.js — all use createApiMock()")
    return True


# ---------------------------------------------------------------------------
# Check 3: Schema contracts not stale
# ---------------------------------------------------------------------------
@check("Schema contracts are up-to-date")
def check_schema_freshness():
    contracts = FRONTEND / "src" / "schemas" / "api-contracts.json"
    responses = BACKEND / "app" / "models" / "responses.py"
    project_model = BACKEND / "app" / "models" / "project.py"

    if not contracts.exists():
        print("  api-contracts.json not found — run: uv run python backend/scripts/export_schemas.py")
        return "warn"

    if not responses.exists() or not project_model.exists():
        print("  Model files not found — skipping")
        return "warn"

    contracts_mtime = contracts.stat().st_mtime
    models_mtime = max(responses.stat().st_mtime, project_model.stat().st_mtime)

    if models_mtime > contracts_mtime:
        delta = models_mtime - contracts_mtime
        print(f"  Models modified {delta:.0f}s after contracts were generated")
        print("  Run: uv run python backend/scripts/export_schemas.py")
        return False

    print(f"  Contracts are newer than model files")
    return True


# ---------------------------------------------------------------------------
# Check 4: No hardcoded version strings outside config.py
# ---------------------------------------------------------------------------
@check("No hardcoded version strings outside config.py")
def check_version_strings():
    # Get the canonical version from config.py
    config_path = BACKEND / "app" / "config.py"
    config_text = config_path.read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION[^=]*=\s*["\']([^"\']+)["\']', config_text)
    if not match:
        print("  Cannot find APP_VERSION in config.py")
        return False

    version = match.group(1)
    print(f"  Canonical version: {version}")

    # Check routes for hardcoded version strings (common offender)
    violations = []
    routes_dir = BACKEND / "app" / "routes"
    for py_file in sorted(routes_dir.glob("*.py")):
        content = py_file.read_text(encoding="utf-8", errors="replace")
        # Look for version-like strings that match the pattern but aren't using config
        for i, line in enumerate(content.split("\n"), 1):
            # Skip comments and imports
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("import") or stripped.startswith("from"):
                continue
            # Look for quoted version strings like "2.2.0" that aren't part of config references
            if f'"{version}"' in line or f"'{version}'" in line:
                if "APP_VERSION" not in line and "config." not in line:
                    violations.append(f"  {py_file.name}:{i}: {stripped[:80]}")

    # Also check main.py
    main_path = BACKEND / "app" / "main.py"
    if main_path.exists():
        content = main_path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("import") or stripped.startswith("from"):
                continue
            if f'"{version}"' in line or f"'{version}'" in line:
                if "APP_VERSION" not in line and "config." not in line:
                    violations.append(f"  main.py:{i}: {stripped[:80]}")

    if violations:
        print(f"  {len(violations)} hardcoded version string(s) found:")
        for v in violations:
            print(v)
        return False

    print(f"  No hardcoded version strings in routes or main.py")
    return True


# ---------------------------------------------------------------------------
# Check 5: conftest.py cleans all swarm.py module-level dicts
# ---------------------------------------------------------------------------
@check("conftest.py cleans all swarm.py module-level state")
def check_conftest_coverage():
    swarm_path = BACKEND / "app" / "routes" / "swarm.py"
    conftest_path = BACKEND / "tests" / "conftest.py"

    swarm_text = swarm_path.read_text(encoding="utf-8")
    conftest_text = conftest_path.read_text(encoding="utf-8")

    # Find all module-level mutable state in swarm.py (dicts, lists, sets)
    # Pattern: _name: type = {} or _name = {} at module level (not indented)
    mutable_pattern = re.compile(
        r"^(_[a-z_]+)\s*(?::\s*[^=]+)?\s*=\s*(\{|\[|deque|set|dict|list)",
        re.MULTILINE,
    )

    swarm_dicts = set()
    for m in mutable_pattern.finditer(swarm_text):
        name = m.group(1)
        # Exclude locks (threading.Lock) — they don't need clearing
        line = swarm_text[m.start():swarm_text.index("\n", m.start())]
        if "Lock()" in line:
            continue
        swarm_dicts.add(name)

    # Find all .clear() calls in conftest teardown section
    # The teardown is after "yield _app" — find that section
    yield_pos = conftest_text.find("yield _app")
    if yield_pos == -1:
        yield_pos = conftest_text.find("yield app")
    if yield_pos == -1:
        print("  Cannot find yield in conftest.py")
        return False

    teardown_section = conftest_text[yield_pos:]
    cleared = set()
    for m in re.finditer(r"(_[a-z_]+)\.clear\(\)", teardown_section):
        cleared.add(m.group(1))

    missing = swarm_dicts - cleared
    if missing:
        print(f"  {len(missing)} module-level dict(s) NOT cleared in conftest teardown:")
        for name in sorted(missing):
            print(f"    {name}")
        print(f"\n  Cleared ({len(cleared)}): {', '.join(sorted(cleared))}")
        print(f"  In swarm.py ({len(swarm_dicts)}): {', '.join(sorted(swarm_dicts))}")
        return False

    print(f"  All {len(swarm_dicts)} mutable state vars are cleared in teardown")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Latent Underground — Pre-flight Validation")
    print(f"Project root: {ROOT}")

    run_checks()

    print(f"\n{'='*60}")
    print(f"SUMMARY: {passed} passed, {failed} failed, {warnings} warnings")
    print(f"{'='*60}")

    if failed > 0:
        print("\nFix the above issues before proceeding.")
        sys.exit(1)
    else:
        print("\nAll checks passed!")
        sys.exit(0)
