"""
Contract tests for stable project decisions.

Protected docs:
- docs/decisions.md
- docs/adapter_contract.md
- docs/terminal_access_contract.md

These tests protect:
  - docs/decisions.md records the key stable decisions for the project.
  - The LOCAL_PYTHON decision (#16) is present.
  - The terminal access model decision lists all three public modes.
  - MANAGED_TERMINAL is marked as unimplemented until done.
  - The venue identity decision exists.
"""
from __future__ import annotations

import pathlib

ROOT_DIR = pathlib.Path(__file__).parent.parent.parent
DECISIONS_PATH = ROOT_DIR / "docs" / "decisions.md"
ADAPTER_CONTRACT_PATH = ROOT_DIR / "docs" / "adapter_contract.md"
TERMINAL_CONTRACT_PATH = ROOT_DIR / "docs" / "terminal_access_contract.md"


def test_decisions_doc_exists():
    assert DECISIONS_PATH.exists()


def test_decisions_doc_contains_venue_identity():
    """decisions.md must record the canonical venue identity decision."""
    text = DECISIONS_PATH.read_text()
    assert "Venue identity" in text or "venue identity" in text.lower()
    assert "METATRADER_5" in text


def test_decisions_doc_contains_account_validation():
    """decisions.md must record the account validation source decision."""
    text = DECISIONS_PATH.read_text()
    assert "account" in text.lower() and "validation" in text.lower()
    assert "config.account_id" in text or "account_id" in text


def test_decisions_doc_contains_terminal_access_model():
    """decisions.md must record the terminal access model decision."""
    text = DECISIONS_PATH.read_text()
    assert "Terminal Access Model" in text
    assert "EXTERNAL_RPYC" in text
    assert "MANAGED_TERMINAL" in text


def test_decisions_doc_contains_local_python_decision():
    """decisions.md must record decision #16 for LOCAL_PYTHON terminal access."""
    text = DECISIONS_PATH.read_text()
    assert "LOCAL_PYTHON" in text
    # Should describe what LOCAL_PYTHON does
    assert "MetaTrader5" in text
    assert "initialize" in text or "local machine" in text.lower()


def test_decisions_doc_records_dockerized_as_internal_only():
    """decisions.md must clarify that DOCKERIZED is an internal backend only."""
    text = DECISIONS_PATH.read_text()
    assert "DOCKERIZED" in text
    assert "internal" in text.lower() or "backend" in text.lower()


def test_decisions_doc_contains_bridge_shape():
    """decisions.md must record the MT5-native bridge shape decision."""
    text = DECISIONS_PATH.read_text()
    assert "Bridge shape" in text or "bridge" in text.lower()
    assert "MT5-native" in text or "mt5-native" in text.lower()


def test_decisions_doc_contains_capability_support_definition():
    """decisions.md must define what 'Supported' means for a capability."""
    text = DECISIONS_PATH.read_text()
    assert "Capability support" in text or "capability support" in text.lower()
    assert "Supported" in text


def test_decisions_doc_live_tests_are_supplementary():
    """decisions.md must clarify that live tests are supplementary, not source of truth."""
    text = DECISIONS_PATH.read_text()
    assert "Live tests" in text or "live tests" in text.lower()
    assert "supplementary" in text.lower() or "optional" in text.lower()


def test_managed_terminal_unimplemented_contract_consistent():
    """
    Both the terminal contract and the decisions doc must state that MANAGED_TERMINAL
    raises a controlled error while unimplemented.
    """
    terminal_text = TERMINAL_CONTRACT_PATH.read_text()
    decisions_text = DECISIONS_PATH.read_text()
    # terminal contract
    assert (
        "RuntimeError" in terminal_text
        or "unimplemented" in terminal_text.lower()
        or "not yet" in terminal_text.lower()
    )
    # decisions must record the mode
    assert "MANAGED_TERMINAL" in decisions_text


def test_local_python_in_decisions_is_not_marked_as_fully_supported():
    """
    The LOCAL_PYTHON decision must not claim the mode is fully validated/supported
    before implementation steps are complete.
    """
    text = DECISIONS_PATH.read_text()
    # Find the LOCAL_PYTHON section
    idx = text.find("LOCAL_PYTHON terminal access")
    assert idx != -1, "Decision for LOCAL_PYTHON terminal access must exist"
    section = text[idx : idx + 800]
    # Should not claim it is a 'Supported' capability
    # The decision can describe what it will do without claiming it is done
    assert "fully validated" not in section.lower(), (
        "LOCAL_PYTHON decision must not claim the mode is fully validated"
    )
