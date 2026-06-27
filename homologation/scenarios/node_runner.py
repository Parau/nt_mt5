"""Shared helpers for TradingNode-based homologation scenarios."""
from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable

from nautilus_trader.live.node import TradingNode

from homologation.support.clients import reset_mt5_client_cache


class NodeStopGate:
    """Ensure ``node.stop()`` is invoked at most once per session."""

    def __init__(self, node: TradingNode) -> None:
        self._node = node
        self._lock = threading.Lock()
        self._stopped = False

    def request_stop(self) -> None:
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            threading.Thread(
                target=self._node.stop,
                daemon=True,
                name="homolog-stop",
            ).start()

    @property
    def stopped(self) -> bool:
        with self._lock:
            return self._stopped


def run_node_session(
    build_node: Callable[[], TradingNode],
    timeout_secs: float,
) -> None:
    """
    Build, run, and dispose a TradingNode in the current thread.

    Mirrors ``examples/exec_smoke_trading_node.py``: the node lifecycle must
    not share an asyncio event loop with other homologation scenarios.
    """
    reset_mt5_client_cache()
    node = build_node()
    try:
        node.run()
    finally:
        node.dispose()
    reset_mt5_client_cache()


async def run_node_until(
    build_node: Callable[[], TradingNode],
    done: threading.Event,
    timeout_secs: float,
    stop_gate_holder: list[NodeStopGate | None] | None = None,
) -> None:
    """
    Run a TradingNode session in a worker thread until ``done`` is set or timeout.
    """
    gate_holder: list[NodeStopGate | None] = stop_gate_holder if stop_gate_holder is not None else [None]
    error_holder: list[BaseException | None] = [None]

    def _worker() -> None:
        reset_mt5_client_cache()
        node = build_node()
        gate_holder[0] = NodeStopGate(node)
        try:
            node.run()
        except BaseException as exc:
            error_holder[0] = exc
            raise
        finally:
            node.dispose()
            reset_mt5_client_cache()

    worker = threading.Thread(target=_worker, daemon=True, name="homolog-node")
    worker.start()

    try:
        await asyncio.wait_for(asyncio.to_thread(done.wait), timeout=timeout_secs)
    except asyncio.TimeoutError as exc:
        gate = gate_holder[0]
        if gate is not None:
            gate.request_stop()
        raise TimeoutError(str(exc)) from exc
    finally:
        gate = gate_holder[0]
        if gate is not None and not gate.stopped:
            gate.request_stop()
        worker.join(timeout=45.0)
        if error_holder[0] is not None:
            raise error_holder[0]


def stop_node_from_strategy(stop_gate: NodeStopGate) -> Callable[[], None]:
    """Return a callback strategies invoke once when their work is complete."""

    def _stop() -> None:
        stop_gate.request_stop()

    return _stop
