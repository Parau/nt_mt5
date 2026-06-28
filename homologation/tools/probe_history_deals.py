"""Probe history_deals_get call patterns against live MT5 bridge."""
from __future__ import annotations

import datetime as dt
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from nautilus_mt5.metatrader5.MetaTrader5 import MetaTrader5


def _len(result) -> str:
    if result is None:
        return "None"
    return str(len(result))


def main() -> None:
    host = os.environ.get("MT5_HOST", "127.0.0.1")
    port = int(os.environ.get("MT5_PORT", "18812"))
    symbol = os.environ.get("MT5_SYMBOL", "BTCUSD")

    mt5 = MetaTrader5(host=host, port=port)
    now = dt.datetime.now(dt.timezone.utc)
    fr = now - dt.timedelta(hours=2)
    to_future = now + dt.timedelta(minutes=5)
    fr_ts = int(fr.timestamp())
    to_ts = int(now.timestamp())
    to_future_ts = int(to_future.timestamp())

    print(f"account={mt5.account_info()}")
    print(f"now_utc={now.isoformat()}")
    print(f"fr_ts={fr_ts} to_ts={to_ts}")

    d1 = mt5.history_deals_get(fr, to_future, group=f"*{symbol}*")
    print(f"datetime+group+future_end: count={_len(d1)} err={mt5.last_error()}")
    if d1:
        for deal in d1[-3:]:
            d = deal if isinstance(deal, dict) else deal._asdict()
            print(f"  sample: ticket={d.get('ticket')} sym={d.get('symbol')} vol={d.get('volume')}")

    d2 = mt5.history_deals_get(fr_ts, to_ts)
    print(f"unix_int (adapter path): count={_len(d2)} err={mt5.last_error()}")

    d3 = mt5.history_deals_get(fr, now)
    print(f"datetime no group end=now: count={_len(d3)} err={mt5.last_error()}")

    d4 = mt5.history_deals_get(0, to_future_ts)
    print(f"from0 unix: count={_len(d4)} err={mt5.last_error()}")
    if d4:
        deals = [d if isinstance(d, dict) else d._asdict() for d in d4]
        btc = [d for d in deals if d.get("symbol") == symbol]
        print(f"  BTCUSD deals in from0: {len(btc)}")
        if btc:
            latest = max(btc, key=lambda d: int(d.get("time", 0)))
            print(
                f"  latest BTCUSD: time={latest.get('time')} "
                f"({dt.datetime.fromtimestamp(int(latest['time']), tz=dt.timezone.utc).isoformat()}) "
                f"ticket={latest.get('ticket')} vol={latest.get('volume')}"
            )
        times = [int(d.get("time", 0)) for d in deals if d.get("time")]
        if times:
            print(f"  all deals time range: min={min(times)} max={max(times)}")
            print(f"  query window: fr_ts={fr_ts} to_ts={to_ts}")

    d5 = mt5.history_deals_get(fr_ts - 86400, to_future_ts)
    print(f"unix 24h+future: count={_len(d5)} err={mt5.last_error()}")

    d6 = mt5.history_deals_get(fr_ts, to_future_ts)
    print(f"unix 2h+future_end: count={_len(d6)} err={mt5.last_error()}")

    total = mt5.history_deals_total(fr, to_future)
    print(f"history_deals_total datetime: {total} err={mt5.last_error()}")

    total2 = mt5.history_deals_total(fr_ts, to_future_ts)
    print(f"history_deals_total unix: {total2} err={mt5.last_error()}")

    if d4:
        deals = [d if isinstance(d, dict) else d._asdict() for d in d4]
        btc = [d for d in deals if d.get("symbol") == symbol]
        if btc:
            latest = max(btc, key=lambda d: int(d.get("time", 0)))
            order_ticket = int(latest["order"])
            dticket = mt5.history_deals_get(ticket=order_ticket)
            print(
                f"by_order_ticket({order_ticket}): count={_len(dticket)} "
                f"err={mt5.last_error()}"
            )
            deal_ticket = int(latest["ticket"])
            dpos = mt5.history_deals_get(position=deal_ticket)
            print(
                f"by_deal_as_position({deal_ticket}): count={_len(dpos)} "
                f"err={mt5.last_error()}"
            )

    d7 = mt5.history_deals_get(0, to_future_ts, group=f"*{symbol}*")
    print(f"from0+group unix: count={_len(d7)} err={mt5.last_error()}")


if __name__ == "__main__":
    main()
