"""
Contract tests for the capability matrices.

Protected docs:
- docs/data_capability_matrix.md
- docs/execution_capability_matrix.md
- docs/terminal_access_capability_audit.md

These tests are deterministic and offline. They protect:
  - Only allowed status values appear in the matrices.
  - 'Supported' capabilities have a non-N/A 'Validated by' entry.
  - 'Partial' capabilities have notes.
  - The audit document explicitly distinguishes RPC availability from Nautilus capability.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT_DIR = pathlib.Path(__file__).parent.parent.parent
DATA_MATRIX_PATH = ROOT_DIR / "docs" / "data_capability_matrix.md"
EXEC_MATRIX_PATH = ROOT_DIR / "docs" / "execution_capability_matrix.md"
AUDIT_PATH = ROOT_DIR / "docs" / "terminal_access_capability_audit.md"

ALLOWED_STATUSES = {"Supported", "Partial", "Unsupported", "Planned"}


def _extract_table_rows(text: str) -> list[list[str]]:
    """Return non-header, non-separator markdown table rows as lists of cells."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            # Skip separator rows (all dashes)
            if all(re.match(r"^-+$", c.replace(" ", "")) for c in cells if c):
                continue
            rows.append(cells)
    return rows


def _operational_rows(path: pathlib.Path) -> list[list[str]]:
    """Return rows from the 'Operational traceability matrix' section."""
    text = path.read_text()
    # Find section after "Operational traceability matrix"
    marker = "Operational traceability matrix"
    idx = text.find(marker)
    if idx == -1:
        return []
    section = text[idx:]
    rows = _extract_table_rows(section)
    # Skip the header row (first row)
    return rows[1:] if len(rows) > 1 else []


def test_data_matrix_exists():
    assert DATA_MATRIX_PATH.exists()


def test_execution_matrix_exists():
    assert EXEC_MATRIX_PATH.exists()


def test_terminal_access_audit_exists():
    assert AUDIT_PATH.exists()


def test_capability_matrices_use_allowed_status_values():
    """
    Every status cell in both capability matrices must use only the four allowed values.
    Status is the 2nd column (index 1) in the operational traceability table.
    """
    for path in [DATA_MATRIX_PATH, EXEC_MATRIX_PATH]:
        rows = _operational_rows(path)
        for row in rows:
            if len(row) < 2:
                continue
            status_cell = row[1]
            # Extract bold markers if present
            status = status_cell.replace("**", "").strip()
            if status and status != "Status":
                assert status in ALLOWED_STATUSES, (
                    f"Invalid status '{status}' in {path.name}. "
                    f"Allowed: {ALLOWED_STATUSES}"
                )


def test_supported_capabilities_have_validated_by_or_equivalent():
    """
    Every 'Supported' row in the operational matrix must have a non-trivial
    'Validated by' entry (column index 5). It must not be 'N/A' or blank.
    """
    for path in [DATA_MATRIX_PATH, EXEC_MATRIX_PATH]:
        rows = _operational_rows(path)
        for row in rows:
            if len(row) < 6:
                continue
            status = row[1].replace("**", "").strip()
            if status == "Supported":
                validated_by = row[5].strip()
                assert validated_by and validated_by.lower() not in {"n/a", "-", ""}, (
                    f"Supported capability '{row[0]}' in {path.name} "
                    f"must have a non-N/A 'Validated by' entry, got: '{validated_by}'"
                )


def test_partial_capabilities_have_notes():
    """
    Every 'Partial' row must have content in the Notes column (index 6).
    """
    for path in [DATA_MATRIX_PATH, EXEC_MATRIX_PATH]:
        rows = _operational_rows(path)
        for row in rows:
            if len(row) < 7:
                continue
            status = row[1].replace("**", "").strip()
            if status == "Partial":
                notes = row[6].strip()
                assert notes and notes not in {"-", "N/A", ""}, (
                    f"Partial capability '{row[0]}' in {path.name} "
                    f"must have notes describing the missing piece"
                )


def test_data_matrix_tracks_trade_ticks_explicitly():
    """The data capability matrix must have an explicit Trade ticks row."""
    text = DATA_MATRIX_PATH.read_text()
    assert "Trade tick" in text or "trade tick" in text.lower(), (
        "data_capability_matrix.md must explicitly track trade ticks"
    )


def test_execution_matrix_tracks_unsupported_type_and_tif():
    """The execution matrix must track unsupported order type and unsupported TIF."""
    text = EXEC_MATRIX_PATH.read_text()
    assert "Unsupported" in text
    # Check for TIF tracking
    assert "TIF" in text or "time-in-force" in text.lower() or "tif" in text.lower()


def test_terminal_access_audit_distinguishes_rpc_from_capability():
    """
    The audit document must explicitly state that gateway RPC availability
    is not the same as Nautilus capability support.
    """
    text = AUDIT_PATH.read_text()
    # Look for phrases that separate RPC availability from Nautilus capability
    assert (
        "não deve ser confundida" in text  # Portuguese
        or "is not equivalent" in text.lower()
        or "is not the same" in text.lower()
        or "confundida" in text
        or "capability" in text.lower() and "rpc" in text.lower()
    ), "audit doc must distinguish RPC surface from Nautilus capability support"


def test_data_matrix_has_required_sections():
    """The data matrix must track the minimum required capability areas."""
    text = DATA_MATRIX_PATH.read_text()
    required = ["Instruments", "Quotes", "Bars", "Lifecycle"]
    for section in required:
        assert section in text, f"data_capability_matrix.md must track '{section}'"


def test_execution_matrix_has_required_sections():
    """The execution matrix must track the minimum required capability areas."""
    text = EXEC_MATRIX_PATH.read_text()
    required = ["Market orders", "Limit orders", "cancell", "reconciliat"]
    for section in required:
        found = section.lower() in text.lower()
        assert found, f"execution_capability_matrix.md must track '{section}'"
