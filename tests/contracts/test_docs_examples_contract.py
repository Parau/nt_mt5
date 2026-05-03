"""
Contract tests for public docs/examples consistency.

Protected docs:
- docs/adapter_contract.md
- docs/terminal_access_contract.md
- README.md
- examples/

These tests protect:
  - README does not promote DOCKERIZED as a public mode.
  - README documents LOCAL_PYTHON as planned/in-implementation (not validated).
  - README documents MANAGED_TERMINAL as planned.
  - Examples use the correct public paths.
  - Execution examples require explicit opt-in.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT_DIR = pathlib.Path(__file__).parent.parent.parent
README_PATH = ROOT_DIR / "README.md"
EXAMPLES_DIR = ROOT_DIR / "examples"
TERMINAL_CONTRACT_PATH = ROOT_DIR / "docs" / "terminal_access_contract.md"
DECISIONS_PATH = ROOT_DIR / "docs" / "decisions.md"


def test_readme_exists():
    assert README_PATH.exists()


def test_readme_does_not_promote_dockerized_as_public_mode():
    """README must not list DOCKERIZED as a top-level public terminal access mode."""
    text = README_PATH.read_text()
    assert "MT5TerminalAccessMode.DOCKERIZED" not in text, (
        "README must not promote MT5TerminalAccessMode.DOCKERIZED as a public mode"
    )


def test_readme_mentions_external_rpyc_as_supported():
    """README must present EXTERNAL_RPYC as currently supported."""
    text = README_PATH.read_text()
    assert "EXTERNAL_RPYC" in text
    # Should be presented as currently supported
    assert "Currently Supported" in text or "supported" in text.lower()


def test_readme_documents_managed_terminal_as_planned():
    """README must present MANAGED_TERMINAL as planned/not yet operational."""
    text = README_PATH.read_text()
    assert "MANAGED_TERMINAL" in text
    assert "Planned" in text or "planned" in text.lower() or "not yet operational" in text.lower()


def test_readme_mentions_local_python_as_planned_or_in_implementation():
    """
    README must mention LOCAL_PYTHON as an option, but should NOT claim it is
    fully validated before the implementation steps are complete.
    """
    text = README_PATH.read_text()
    assert "LOCAL_PYTHON" in text, "README must mention LOCAL_PYTHON"
    # It should not claim full support without qualification
    # It must have a disclaimer that it is planned/in implementation
    assert (
        "Planned" in text
        or "planned" in text.lower()
        or "In Implementation" in text
        or "implementation" in text.lower()
        or "pending" in text.lower()
    ), "README must qualify LOCAL_PYTHON as planned or in implementation"


def test_readme_does_not_claim_local_python_fully_validated():
    """
    README must not present LOCAL_PYTHON as fully validated (Currently Supported)
    before test coverage is established.
    """
    text = README_PATH.read_text()
    # Find the LOCAL_PYTHON section and check it doesn't say "Currently Supported"
    local_python_idx = text.find("LOCAL_PYTHON")
    if local_python_idx != -1:
        # Get a window around LOCAL_PYTHON
        window = text[local_python_idx : local_python_idx + 300]
        assert "Currently Supported" not in window, (
            "README must not mark LOCAL_PYTHON as 'Currently Supported' before test coverage"
        )


def test_external_rpyc_example_exists():
    """The connect_with_external_rpyc.py example must exist."""
    example_path = EXAMPLES_DIR / "connect_with_external_rpyc.py"
    assert example_path.exists(), f"Example not found: {example_path}"


def test_external_rpyc_example_uses_current_public_path():
    """The EXTERNAL_RPYC example must use MT5TerminalAccessMode.EXTERNAL_RPYC."""
    example_path = EXAMPLES_DIR / "connect_with_external_rpyc.py"
    content = example_path.read_text()
    assert "MT5TerminalAccessMode.EXTERNAL_RPYC" in content, (
        "connect_with_external_rpyc.py must use MT5TerminalAccessMode.EXTERNAL_RPYC"
    )


def test_managed_terminal_example_is_marked_planned_or_placeholder():
    """
    The dockerized terminal example must use MANAGED_TERMINAL mode (not standalone DOCKERIZED)
    and must indicate it is a placeholder/future behavior.
    """
    example_path = EXAMPLES_DIR / "connect_with_dockerized_terminal.py"
    if not example_path.exists():
        pytest.skip("connect_with_dockerized_terminal.py not present — skipping")
    content = example_path.read_text()
    assert "MT5TerminalAccessMode.MANAGED_TERMINAL" in content, (
        "dockerized example must use MANAGED_TERMINAL mode, not a standalone DOCKERIZED mode"
    )
    assert "MT5TerminalAccessMode.DOCKERIZED" not in content, (
        "dockerized example must not use MT5TerminalAccessMode.DOCKERIZED directly"
    )


def test_examples_do_not_use_legacy_dockerized_gateway_as_primary_path():
    """No example file should use dockerized_gateway as the primary recommended path."""
    for example_file in EXAMPLES_DIR.glob("*.py"):
        content = example_file.read_text()
        # dockerized_gateway= at a config root is legacy; it should not be the primary path
        assert "dockerized_gateway=" not in content or "managed_terminal=" in content, (
            f"{example_file.name}: do not use legacy dockerized_gateway= as primary path"
        )


def test_execution_examples_require_explicit_opt_in():
    """
    Any example that may submit real orders must require MT5_ENABLE_LIVE_EXECUTION.
    """
    for example_file in EXAMPLES_DIR.glob("*.py"):
        content = example_file.read_text()
        # Only check examples that appear to submit orders
        if "order_send" in content or "submit_order" in content:
            assert "MT5_ENABLE_LIVE_EXECUTION" in content, (
                f"{example_file.name}: execution example must check MT5_ENABLE_LIVE_EXECUTION"
            )


def test_decisions_local_python_definition_is_clear():
    """decisions.md LOCAL_PYTHON decision must define what the mode does."""
    text = DECISIONS_PATH.read_text()
    # Decision #16 should be present
    assert "LOCAL_PYTHON" in text
    assert "MetaTrader5" in text or "local machine" in text.lower()
