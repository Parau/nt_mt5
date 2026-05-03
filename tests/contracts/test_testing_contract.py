"""
Contract tests for test quality rules.

Protected docs:
- docs/testing_contract.md
- docs/ai_agent_guidelines.md

These tests protect:
  - No test ends with `assert True`.
  - No known internal monkeypatch anti-patterns are used.
"""
from __future__ import annotations

import pathlib
import re

ROOT_DIR = pathlib.Path(__file__).parent.parent.parent
TESTS_DIR = ROOT_DIR / "tests"

# Monkeypatching internal Nautilus state is fragile and discouraged.
FORBIDDEN_MONKEYPATCH_TARGETS = [
    r'monkeypatch\.setattr\([^,]+,\s*["\']_cache["\']',
    r'monkeypatch\.setattr\([^,]+,\s*["\']_clock["\']',
    r'monkeypatch\.setattr\([^,]+,\s*["\']_msgbus["\']',
]


def _all_test_files() -> list[pathlib.Path]:
    return list(TESTS_DIR.rglob("test_*.py"))


def test_no_assert_true_in_tests():
    """
    No test file should end with a bare `assert True` statement.
    Such assertions prove nothing about adapter behavior.
    """
    violations = []
    for test_file in _all_test_files():
        content = test_file.read_text()
        lines = content.splitlines()
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped == "assert True":
                violations.append(f"{test_file.relative_to(ROOT_DIR)}:{i}: bare `assert True`")
    assert not violations, (
        "Bare `assert True` found in test files (proves nothing):\n"
        + "\n".join(violations)
    )


def test_no_known_internal_monkeypatch_patterns():
    """
    Tests must not monkeypatch known Nautilus internal attributes (_cache, _clock, _msgbus).
    These are fragile and couple tests to implementation internals.
    """
    violations = []
    for test_file in _all_test_files():
        content = test_file.read_text()
        for pattern in FORBIDDEN_MONKEYPATCH_TARGETS:
            matches = re.findall(pattern, content)
            if matches:
                violations.append(
                    f"{test_file.relative_to(ROOT_DIR)}: "
                    f"forbidden monkeypatch of internal attribute"
                )
    assert not violations, (
        "Forbidden monkeypatch patterns found (avoid patching _cache/_clock/_msgbus):\n"
        + "\n".join(violations)
    )


def test_tests_directory_has_expected_subdirectories():
    """
    The tests directory must contain the minimum expected subdirectories.
    """
    required = ["unit", "integration", "acceptance"]
    for subdir in required:
        assert (TESTS_DIR / subdir).is_dir(), (
            f"tests/{subdir}/ must exist as part of the minimum test structure"
        )


def test_contracts_directory_exists():
    """The tests/contracts/ directory must exist (this test is self-validating)."""
    assert (TESTS_DIR / "contracts").is_dir()


# Documented in docs/testing_contract.md — "Directory layout" section.
# Update this set only when the testing_contract.md layout table is updated first.
_EXPECTED_TEST_SUBDIRS = {
    "acceptance",
    "contracts",
    "integration",
    "integration_tests",
    "live",
    "memory",
    "performance",
    "support",
    "test_data",
    "unit",
}


def test_tests_directory_has_only_expected_subdirectories():
    """
    The top-level subdirectories of tests/ must match the documented layout exactly.

    If you need to add a new directory, update docs/testing_contract.md first
    (the "Directory layout" table and decision rules), then extend _EXPECTED_TEST_SUBDIRS here.
    """
    actual = {p.name for p in TESTS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")}
    unexpected = actual - _EXPECTED_TEST_SUBDIRS
    missing = _EXPECTED_TEST_SUBDIRS - actual
    problems = []
    if unexpected:
        problems.append(
            "Unexpected directories (add to docs/testing_contract.md layout table first):\n"
            + "\n".join(f"  tests/{d}/" for d in sorted(unexpected))
        )
    if missing:
        problems.append(
            "Documented directories not found (remove from _EXPECTED_TEST_SUBDIRS if intentional):\n"
            + "\n".join(f"  tests/{d}/" for d in sorted(missing))
        )
    assert not problems, "\n".join(problems)
