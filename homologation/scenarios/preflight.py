"""TC-HOM-PF: Bridge and symbol pre-flight checks."""
from __future__ import annotations

import rpyc

from homologation.config import HomologationConfig, probe_symbol_tick
from homologation.report import HomologationReport, ScenarioStatus


async def run_preflight(cfg: HomologationConfig, report: HomologationReport) -> None:
    case_id = "TC-HOM-PF"
    name = "Bridge pre-flight (account + symbol tick)"

    try:
        conn = rpyc.connect(cfg.host, cfg.port)
        try:
            info = conn.root.account_info()
            if isinstance(info, dict):
                login = int(info["login"])
                server = info.get("server", "")
            else:
                login = int(info.login)
                server = getattr(info, "server", "")
        finally:
            conn.close()

        if str(login) != cfg.account_number:
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                f"Account mismatch: env={cfg.account_number} bridge={login}",
            )
            return

        prices = probe_symbol_tick(cfg.host, cfg.port, cfg.symbol)
        if prices is None:
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                f"No tick for {cfg.symbol} — market closed or symbol unavailable",
            )
            return

        bid, ask = prices
        report.add(
            case_id,
            name,
            ScenarioStatus.PASS,
            f"login={login} server={server} {cfg.symbol} bid={bid} ask={ask}",
            login=login,
            server=server,
            bid=bid,
            ask=ask,
        )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
