"""Post-deploy homologation: E03, D03, D06 (gateway + optional Service restart)."""
from __future__ import annotations

import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from homologation.config import HomologationConfig, probe_symbol_tick
from homologation.report import HomologationReport, ScenarioStatus
from homologation.scenarios.data_tester_suite import run_bar_subscribe
from homologation.scenarios.exec_tester_suite import run_limit_gtc_cancel
from homologation.scenarios.feed_resilience import run_feed_service_restart_dedup
from homologation.scenarios.preflight import run_preflight
from homologation.support.clients import reset_mt5_client_cache
from homologation.support.port_probe import find_listening_pid_windows, port_in_use


def _ensure_feed_port_free(cfg: HomologationConfig) -> str | None:
    """Return error message when the WS feed port is already bound."""
    if port_in_use(cfg.feed_host if cfg.feed_host != "0.0.0.0" else "127.0.0.1", cfg.feed_port):
        pid = find_listening_pid_windows(cfg.feed_port)
        hint = f"taskkill /PID {pid} /F" if pid else "close the other Python/homologation process"
        return (
            f"Port {cfg.feed_port} already in use (InboundFeedGateway bind). "
            f"Only one WS gateway per machine. {hint}"
        )
    return None


async def main() -> int:
    if not os.environ.get("MT5_FEED_ENABLED", "").strip() == "1":
        os.environ["MT5_FEED_ENABLED"] = "1"
    cfg = HomologationConfig.from_env()
    report = HomologationReport()
    require_svc = os.environ.get("HOMOLOG_D06_REQUIRE_SERVICE_RESTART", "").strip() == "1"

    print("=" * 64)
    print("  POST-DEPLOY HOMOLOGATION (E03, D03, D06)")
    print(f"  RPyC   : {cfg.host}:{cfg.port}")
    print(f"  WS     : ws://{cfg.feed_host}:{cfg.feed_port}{cfg.feed_path}")
    print(f"  Symbol : {cfg.symbol}")
    print(f"  Exec   : {'ON' if cfg.enable_execution else 'OFF (set MT5_ENABLE_LIVE_EXECUTION=1)'}")
    if require_svc:
        print("  D06    : gateway restart + manual Service stop/start")
    else:
        print("  D06    : gateway restart only (set HOMOLOG_D06_REQUIRE_SERVICE_RESTART=1 for Service)")
    tick = probe_symbol_tick(cfg.host, cfg.port, cfg.symbol)
    print(f"  Quote  : {tick if tick else 'NO TICK'}")
    port_err = _ensure_feed_port_free(cfg)
    if port_err:
        print(f"  ERROR  : {port_err}")
        print("=" * 64)
        return 1
    print("  Ensure NT5TickFeedService is running (connects to this WS gateway).")
    print("=" * 64)

    reset_mt5_client_cache()
    await run_preflight(cfg, report)
    if report.has_failures:
        report.print_summary()
        return 1

    if cfg.enable_execution:
        reset_mt5_client_cache()
        await run_limit_gtc_cancel(cfg, report)
    else:
        report.add(
            "TC-HOM-E03",
            "Limit GTC + cancel",
            ScenarioStatus.SKIP,
            "Set MT5_ENABLE_LIVE_EXECUTION=1",
        )

    reset_mt5_client_cache()
    await run_bar_subscribe(cfg, report)

    reset_mt5_client_cache(settle_secs=3.0)
    await run_feed_service_restart_dedup(cfg, report)

    report.print_summary()
    path = os.environ.get("HOMOLOG_REPORT_JSON", "homologation/last_deploy_report.json")
    report.write_json(path)
    print(f"  JSON report written to {path}")
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
