"""TC-HOM-D02 homologation scenario guards."""
from __future__ import annotations

import pytest

from homologation.config import HomologationConfig
from homologation.report import HomologationReport
from homologation.scenarios.tick_stream import run_tick_stream


def _cfg(**overrides) -> HomologationConfig:
    base = dict(
        host="127.0.0.1",
        port=18812,
        account_number="12345",
        broker="Tickmill-Demo",
        symbol="BTCUSD",
        enable_execution=False,
        min_quote_ticks=3,
        scenario_timeout_secs=120.0,
        stream_duration_secs=30.0,
        stream_max_gap_secs=30.0,
        stream_min_ticks=3,
        skip_stream=False,
        feed_enabled=False,
        feed_host="0.0.0.0",
        feed_port=8765,
        feed_path="/mt5-feed",
        feed_hello_timeout_secs=30.0,
    )
    base.update(overrides)
    return HomologationConfig(**base)


@pytest.mark.asyncio
async def test_d02_skips_when_feed_disabled() -> None:
    report = HomologationReport()
    await run_tick_stream(_cfg(feed_enabled=False), report)

    assert len(report.results) == 1
    result = report.results[0]
    assert result.case_id == "TC-HOM-D02"
    assert result.status.name == "SKIP"
    assert "MT5_FEED_ENABLED=1" in result.detail


@pytest.mark.asyncio
async def test_d02_skips_when_stream_disabled() -> None:
    report = HomologationReport()
    await run_tick_stream(_cfg(feed_enabled=True, skip_stream=True), report)

    assert report.results[0].status.name == "SKIP"
    assert "HOMOLOG_SKIP_STREAM" in report.results[0].detail
