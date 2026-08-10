"""Safe EXTERNAL_RPYC tick-array wire frame (A05 / x04).

Purpose/Single Responsibility:
    Encode/decode MT5 structured tick arrays as a brine-safe binary frame so
    RPyC can transport them by value without ``allow_pickle``.

Data Flow & Dependencies:
    Bridge ``exposed_copy_ticks_range`` encodes; ``MetaTrader5.copy_ticks_range``
    reconstructs an exact local ``numpy.ndarray`` for the A05 helper.

Premises & Limitations:
    LOCAL_PYTHON does not use this frame. Legacy ``copy_ticks_from`` is unchanged.
    Pickle must remain disabled on the RPyC bridge.
"""
from __future__ import annotations

from typing import Any

import numpy as np

MT5_TICKS_FRAME_TAG = "MT5_TICKS_V1"

MT5_TICK_DTYPE = np.dtype(
    [
        ("time", "<i8"),
        ("bid", "<f8"),
        ("ask", "<f8"),
        ("last", "<f8"),
        ("volume", "<u8"),
        ("time_msc", "<i8"),
        ("flags", "<u4"),
        ("volume_real", "<f8"),
    ],
)

_REQUIRED_NAMES = frozenset(name for name, _ in MT5_TICK_DTYPE.descr if name)


def project_ticks_to_canonical(raw: np.ndarray) -> np.ndarray:
    """Project a structured MT5 tick ndarray onto the canonical A05 dtype."""
    if type(raw) is not np.ndarray:
        raise RuntimeError("MT5 tick projection requires an exact local numpy.ndarray")
    if raw.dtype.names is None:
        raise RuntimeError("MT5 tick projection requires a structured numpy.ndarray")
    names = frozenset(raw.dtype.names)
    missing = _REQUIRED_NAMES - names
    if missing:
        raise RuntimeError(f"MT5 tick array missing required fields: {sorted(missing)}")
    out = np.empty(len(raw), dtype=MT5_TICK_DTYPE)
    for name in _REQUIRED_NAMES:
        out[name] = raw[name]
    return out


def encode_mt5_ticks_frame(raw: np.ndarray | None) -> tuple[str, int, bytes] | None:
    """Encode a local MT5 tick ndarray as ``(tag, row_count, raw_bytes)`` or None."""
    if raw is None:
        return None
    canonical = project_ticks_to_canonical(raw)
    payload = canonical.tobytes(order="C")
    return (MT5_TICKS_FRAME_TAG, int(len(canonical)), payload)


def decode_mt5_ticks_frame(frame: Any) -> np.ndarray | None:
    """
    Reconstruct an exact local ``numpy.ndarray`` from a safe wire frame.

    Accepts ``None`` (provider empty/error sentinel at the MT5 API layer) or a
    ``(tag, row_count, payload_bytes)`` triple produced by ``encode_mt5_ticks_frame``.
    """
    if frame is None:
        return None

    if not isinstance(frame, tuple) or len(frame) != 3:
        raise RuntimeError(
            "copy_ticks_range wire payload must be None or "
            f"({MT5_TICKS_FRAME_TAG!r}, row_count, bytes)",
        )

    tag, row_count, payload = frame
    if tag != MT5_TICKS_FRAME_TAG:
        raise RuntimeError(f"unexpected copy_ticks_range wire tag: {tag!r}")
    if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 0:
        raise RuntimeError(f"invalid copy_ticks_range row_count: {row_count!r}")
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise RuntimeError("copy_ticks_range payload must be bytes-like")

    payload_bytes = bytes(payload)
    expected = row_count * MT5_TICK_DTYPE.itemsize
    if len(payload_bytes) != expected:
        raise RuntimeError(
            "copy_ticks_range payload length mismatch: "
            f"len={len(payload_bytes)} expected={expected} row_count={row_count}",
        )

    array = np.frombuffer(payload_bytes, dtype=MT5_TICK_DTYPE, count=row_count).copy()
    if type(array) is not np.ndarray:
        raise RuntimeError("failed to reconstruct exact local numpy.ndarray")
    return array
