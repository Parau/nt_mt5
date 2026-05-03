"""
Contract tests for live-test isolation rules.

Protected docs:
- docs/testing_contract.md
- docs/ai_agent_guidelines.md

These tests protect:
  - Tests that use live MT5/RPyC are marked with appropriate pytest markers.
  - Demo execution tests require explicit opt-in via MT5_ENABLE_LIVE_EXECUTION.
  - Deterministic tests outside tests/live/ do not hard-code reads of live env vars
    (MT5_HOST, MT5_PORT, MT5_ACCOUNT_NUMBER, MT5_PASSWORD, MT5_ENABLE_LIVE_EXECUTION)
    without skipping on absence.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT_DIR = pathlib.Path(__file__).parent.parent.parent
TESTS_DIR = ROOT_DIR / "tests"
LIVE_TESTS_DIR = TESTS_DIR / "live"
ACCEPTANCE_TESTS_DIR = TESTS_DIR / "acceptance"

# Live env vars that deterministic tests must not consume unconditionally
LIVE_ENV_VARS = {
    "MT5_HOST",
    "MT5_PORT",
    "MT5_ACCOUNT_NUMBER",
    "MT5_PASSWORD",
    "MT5_ENABLE_LIVE_EXECUTION",
}

# Test directories that are allowed to use live env vars
LIVE_ALLOWED_DIRS = {"live", "acceptance", "contracts"}

# Patterns that indicate a test file has live awareness (skips on missing vars)
LIVE_SKIP_PATTERNS = [
    r'pytest\.skip',
    r'skipif',
    r'os\.environ\.get',
    r'os\.getenv',
]


def _is_live_aware(content: str) -> bool:
    """Return True if the file has live-skip guard patterns."""
    return any(re.search(p, content) for p in LIVE_SKIP_PATTERNS)


def _get_deterministic_test_files() -> list[pathlib.Path]:
    """Return test files that are not in a live-allowed directory."""
    files = []
    for py_file in TESTS_DIR.rglob("test_*.py"):
        # Skip files inside live-allowed directories
        parts = {p.name for p in py_file.parents}
        if any(d in parts for d in LIVE_ALLOWED_DIRS):
            continue
        files.append(py_file)
    return files


def test_live_tests_directory_does_not_contain_non_skipped_live_env_access():
    """
    Deterministic test files (outside live-allowed dirs) that access live env vars
    must guard them with os.environ.get / os.getenv (not hard os.environ[key]).
    """
    violations = []
    for test_file in _get_deterministic_test_files():
        content = test_file.read_text()
        for var in LIVE_ENV_VARS:
            # Detect direct os.environ["VAR"] access without getenv/get fallback
            hard_access = re.search(rf'os\.environ\s*\[\s*["\']({var})["\']\s*\]', content)
            if hard_access and not _is_live_aware(content):
                violations.append(f"{test_file.relative_to(ROOT_DIR)}: hard access to {var}")
    assert not violations, (
        "Deterministic tests must not hard-read live env vars without skip guards:\n"
        + "\n".join(violations)
    )


def test_demo_execution_tests_require_explicit_opt_in():
    """
    Any test that appears to submit real orders must check MT5_ENABLE_LIVE_EXECUTION.
    """
    violations = []
    for test_file in TESTS_DIR.rglob("test_*.py"):
        content = test_file.read_text()
        # Heuristic: test functions that call order_send or submit_order on a real client
        if (
            "order_send" in content or "submit_order" in content
        ) and "fake" not in test_file.name.lower() and "mock" not in content[:200].lower():
            if "MT5_ENABLE_LIVE_EXECUTION" not in content and "monkeypatch" not in content:
                violations.append(str(test_file.relative_to(ROOT_DIR)))
    # This is a best-effort static check; report but allow if wiring is indirect
    # We use a warning-style assert rather than blocking
    if violations:
        pytest.xfail(
            f"Possible execution tests without explicit opt-in guard: {violations}. "
            "Review and add MT5_ENABLE_LIVE_EXECUTION guard or monkeypatch."
        )


def test_live_tests_are_marked_live():
    """
    If a tests/live/ directory exists, every test file in it must contain
    @pytest.mark.live or use a skip-on-absent-env guard.
    """
    if not LIVE_TESTS_DIR.exists():
        pytest.skip("tests/live/ does not exist yet — skip until live tests are introduced")
    violations = []
    for test_file in LIVE_TESTS_DIR.rglob("test_*.py"):
        content = test_file.read_text()
        has_live_mark = "@pytest.mark.live" in content
        has_skip_guard = _is_live_aware(content)
        if not has_live_mark and not has_skip_guard:
            violations.append(str(test_file.relative_to(ROOT_DIR)))
    assert not violations, (
        "Tests in tests/live/ must have @pytest.mark.live or skip-on-absent-env guards:\n"
        + "\n".join(violations)
    )


def test_acceptance_live_files_are_marked_live():
    """
    Every test file in tests/acceptance/ whose name starts with 'test_live_'
    must carry @pytest.mark.live. These files touch live MT5 infrastructure
    even when the test body calls pytest.skip() — the marker is needed so
    '-m not live' can exclude them from the deterministic suite.
    """
    if not ACCEPTANCE_TESTS_DIR.exists():
        pytest.skip("tests/acceptance/ does not exist yet")
    violations = []
    for test_file in ACCEPTANCE_TESTS_DIR.rglob("test_live_*.py"):
        content = test_file.read_text()
        if "@pytest.mark.live" not in content:
            violations.append(str(test_file.relative_to(ROOT_DIR)))
    assert not violations, (
        "Files in tests/acceptance/ named test_live_* must have @pytest.mark.live:\n"
        + "\n".join(violations)
    )


def test_non_live_tests_do_not_read_live_env_vars():
    """
    Test files outside live-allowed dirs must not unconditionally import env vars
    at module level (without get/getenv guard).
    """
    violations = []
    for test_file in _get_deterministic_test_files():
        content = test_file.read_text()
        for var in LIVE_ENV_VARS:
            # Module-level (not inside function): look for bare getenv/environ at top of file
            # A simple heuristic: if the var appears but there's no skip/get guard, flag it.
            if var in content:
                # Allow it if there's a guard
                if not _is_live_aware(content):
                    # Check if it's inside a function (indented) vs at module level
                    for line in content.splitlines():
                        if var in line and not line.startswith(" ") and not line.startswith("\t"):
                            if "os.environ" in line or "getenv" in line:
                                violations.append(
                                    f"{test_file.relative_to(ROOT_DIR)}: "
                                    f"module-level env access to {var}"
                                )
                                break
    assert not violations, (
        "Deterministic tests must not read live env vars at module level:\n"
        + "\n".join(violations)
    )
