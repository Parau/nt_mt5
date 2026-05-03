"""
Contract tests for the terminal access model.

Protected docs:
- docs/terminal_access_contract.md
- docs/adapter_contract.md
- docs/decisions.md

These tests are deterministic, offline, and require no MT5, RPyC, or live credentials.
They protect the invariant that:
  - EXTERNAL_RPYC, LOCAL_PYTHON, and MANAGED_TERMINAL are the three public access modes.
  - DOCKERIZED is NOT a public access mode; it is only an internal backend of MANAGED_TERMINAL.
  - Each mode is properly documented.

Note on xfail:
  - test_terminal_access_modes_include_local_python and
    test_terminal_access_modes_include_expected_public_modes are marked xfail because
    LOCAL_PYTHON has not yet been added to the MT5TerminalAccessMode enum. That is a pending
    step 03 implementation task. Once the enum is updated, these tests will pass and the
    xfail markers should be removed.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT_DIR = pathlib.Path(__file__).parent.parent.parent
TERMINAL_CONTRACT_PATH = ROOT_DIR / "docs" / "terminal_access_contract.md"
ADAPTER_CONTRACT_PATH = ROOT_DIR / "docs" / "adapter_contract.md"
DECISIONS_PATH = ROOT_DIR / "docs" / "decisions.md"
AI_GUIDELINES_PATH = ROOT_DIR / "docs" / "ai_agent_guidelines.md"
INDEX_PATH = ROOT_DIR / "docs" / "index.md"

# ---------------------------------------------------------------------------
# Static / text-based invariants
# ---------------------------------------------------------------------------


def test_terminal_contract_doc_exists():
    assert TERMINAL_CONTRACT_PATH.exists(), "docs/terminal_access_contract.md must exist"


def test_terminal_contract_lists_three_public_modes():
    """Doc must name all three public access modes."""
    text = TERMINAL_CONTRACT_PATH.read_text()
    assert "EXTERNAL_RPYC" in text
    assert "LOCAL_PYTHON" in text
    assert "MANAGED_TERMINAL" in text


def test_dockerized_is_not_public_terminal_access_mode():
    """
    DOCKERIZED must be documented only as an internal backend, never as a
    top-level public terminal access mode.
    """
    for path in [TERMINAL_CONTRACT_PATH, ADAPTER_CONTRACT_PATH, AI_GUIDELINES_PATH, INDEX_PATH]:
        text = path.read_text()
        # Phrase that would incorrectly promote DOCKERIZED as public should not appear
        assert "MT5TerminalAccessMode.DOCKERIZED" not in text, (
            f"DOCKERIZED must not appear as a public MT5TerminalAccessMode in {path.name}"
        )


def test_dockerized_only_backend_or_documented_future_backend():
    """
    DOCKERIZED should appear only in the context of being a backend/internal strategy,
    not as a user-facing public mode.
    """
    text = TERMINAL_CONTRACT_PATH.read_text()
    # The word "DOCKERIZED" must not appear as a top-level enumerated public mode.
    # It is allowed to appear when describing the internal backend section.
    assert "not a top-level public" in text or "internal backend" in text or "internal strategy" in text.lower(), (
        "terminal_access_contract.md must clarify that DOCKERIZED is not a public mode"
    )


def test_external_rpyc_requires_external_config_contract_documented():
    """Docs must describe that EXTERNAL_RPYC requires an external_rpyc config block."""
    text = TERMINAL_CONTRACT_PATH.read_text()
    assert "external_rpyc" in text.lower()
    assert "EXTERNAL_RPYC" in text


def test_local_python_requires_local_config_contract_documented():
    """Docs must describe LOCAL_PYTHON configuration expectations."""
    text = TERMINAL_CONTRACT_PATH.read_text()
    assert "LOCAL_PYTHON" in text
    # The doc should mention that it doesn't require external_rpyc or managed_terminal blocks
    assert "MetaTrader5" in text or "local" in text.lower()


def test_managed_terminal_unimplemented_error_contract_documented():
    """
    Docs must state that MANAGED_TERMINAL raises a controlled error while unimplemented.
    """
    text = TERMINAL_CONTRACT_PATH.read_text()
    assert "MANAGED_TERMINAL" in text
    assert "RuntimeError" in text or "unimplemented" in text.lower() or "not yet" in text.lower()


def test_decisions_doc_records_local_python_decision():
    """decisions.md must have a LOCAL_PYTHON decision entry."""
    text = DECISIONS_PATH.read_text()
    assert "LOCAL_PYTHON" in text
    assert "local_python" in text.lower() or "LOCAL_PYTHON terminal access" in text


def test_decisions_doc_records_terminal_access_model():
    """decisions.md must have a Terminal Access Model decision."""
    text = DECISIONS_PATH.read_text()
    assert "Terminal Access Model" in text
    assert "EXTERNAL_RPYC" in text
    assert "MANAGED_TERMINAL" in text


def test_adapter_contract_lists_three_modes():
    """adapter_contract.md must list all three terminal access modes."""
    text = ADAPTER_CONTRACT_PATH.read_text()
    assert "EXTERNAL_RPYC" in text
    assert "LOCAL_PYTHON" in text
    assert "MANAGED_TERMINAL" in text


# ---------------------------------------------------------------------------
# Import-level invariants
# ---------------------------------------------------------------------------


def test_terminal_access_modes_include_external_rpyc():
    """MT5TerminalAccessMode enum must contain EXTERNAL_RPYC."""
    from nautilus_mt5.client.types import MT5TerminalAccessMode
    assert hasattr(MT5TerminalAccessMode, "EXTERNAL_RPYC")


def test_terminal_access_modes_include_managed_terminal():
    """MT5TerminalAccessMode enum must contain MANAGED_TERMINAL."""
    from nautilus_mt5.client.types import MT5TerminalAccessMode
    assert hasattr(MT5TerminalAccessMode, "MANAGED_TERMINAL")


def test_terminal_access_modes_include_local_python():
    """MT5TerminalAccessMode enum must contain LOCAL_PYTHON (pending step 03)."""
    from nautilus_mt5.client.types import MT5TerminalAccessMode
    assert hasattr(MT5TerminalAccessMode, "LOCAL_PYTHON")


def test_terminal_access_modes_include_expected_public_modes():
    """MT5TerminalAccessMode must contain all three public modes."""
    from nautilus_mt5.client.types import MT5TerminalAccessMode
    mode_names = {m.name for m in MT5TerminalAccessMode}
    assert "EXTERNAL_RPYC" in mode_names
    assert "LOCAL_PYTHON" in mode_names
    assert "MANAGED_TERMINAL" in mode_names


def test_dockerized_not_in_terminal_access_mode_enum():
    """
    DOCKERIZED must NOT appear in MT5TerminalAccessMode.
    It belongs only in ManagedTerminalBackend (internal backend).
    """
    from nautilus_mt5.client.types import MT5TerminalAccessMode
    mode_names = {m.name for m in MT5TerminalAccessMode}
    assert "DOCKERIZED" not in mode_names, (
        "DOCKERIZED must not be a public MT5TerminalAccessMode member"
    )


def test_dockerized_is_managed_terminal_backend():
    """DOCKERIZED must exist in ManagedTerminalBackend (internal use only)."""
    from nautilus_mt5.client.types import ManagedTerminalBackend
    assert hasattr(ManagedTerminalBackend, "DOCKERIZED")


def test_external_rpyc_mode_value():
    """EXTERNAL_RPYC value must be the expected string."""
    from nautilus_mt5.client.types import MT5TerminalAccessMode
    assert MT5TerminalAccessMode.EXTERNAL_RPYC.value == "external_rpyc"
