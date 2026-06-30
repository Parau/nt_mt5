"""One-off helper to write XP symbol fixtures (probe-derived)."""
import json
import pathlib

root = pathlib.Path(__file__).resolve().parent.parent / "tests" / "test_data"
base = json.loads((root / "symbol_info_btcusd.json").read_text())
base.pop("_comment", None)


def write_fixture(filename: str, sym: str, **overrides) -> None:
    data = dict(base)
    data.update(overrides)
    data["symbol"] = {"symbol": sym, "broker": "XPMT5-DEMO", "sec_type": ""}
    payload = {
        "_comment": f"{sym} synthetic fixture from XPMT5-DEMO probe 2026-06-26.",
        **data,
    }
    (root / filename).write_text(json.dumps(payload, indent=2))
    print(f"wrote {filename}")


write_fixture(
    "symbol_info_wdon26.json",
    "WDON26",
    name="WDON26",
    description="DOLAR MINI",
    trade_calc_mode=33,
    trade_mode=4,
    digits=1,
    trade_tick_size=0.5,
    point=0.5,
    trade_tick_value=5.0,
    trade_contract_size=1.0,
    volume_min=1,
    volume_step=1,
    volume_max=50000,
    path=r"BMF\WDON26",
    under_sec_type="FUTURES",
    expiration_time=1782868500,
    filling_mode=3,
    bank="XP Investimentos",
    currency_profit="BRL",
    currency_base="BRL",
    currency_margin="BRL",
)

write_fixture(
    "symbol_info_petr4.json",
    "PETR4",
    name="PETR4",
    description="PETROBRAS PN N2",
    trade_calc_mode=32,
    trade_mode=4,
    digits=2,
    trade_tick_size=0.01,
    point=0.01,
    trade_tick_value=0.01,
    volume_min=100,
    volume_step=100,
    volume_max=1000000,
    path=r"BOVESPA\A VISTA\PETR4",
    under_sec_type="EQUITY",
    filling_mode=3,
    bank="XP Investimentos",
    currency_profit="BRL",
)

write_fixture(
    "symbol_info_win_dollar.json",
    "WIN$",
    name="WIN$",
    description="IBOVESPA MINI continuous",
    trade_calc_mode=33,
    trade_mode=0,
    digits=0,
    trade_tick_size=1.0,
    point=1.0,
    trade_tick_value=0.2,
    volume_min=1,
    volume_step=1,
    volume_max=25000,
    path=r"BMF\SERIES CONTINUAS\WIN$",
    under_sec_type="FUTURES",
    expiration_time=0,
    filling_mode=3,
)

write_fixture(
    "symbol_info_di1f27.json",
    "DI1F27",
    name="DI1F27",
    description="DI DE 1 DIA",
    trade_calc_mode=33,
    trade_mode=4,
    digits=3,
    trade_tick_size=0.005,
    point=0.005,
    trade_tick_value=0.005,
    volume_min=1,
    volume_step=1,
    volume_max=50000,
    path=r"BMF\DI1F27",
    under_sec_type="FUTURES",
    expiration_time=1798675859,
    filling_mode=3,
)

write_fixture(
    "symbol_info_winq26.json",
    "WINQ26",
    name="WINQ26",
    description="IBOVESPA MINI",
    trade_calc_mode=33,
    trade_mode=4,
    digits=0,
    trade_tick_size=5.0,
    point=5.0,
    trade_tick_value=1.0,
    volume_min=1,
    volume_step=1,
    volume_max=25000,
    path=r"BMF\WINQ26",
    under_sec_type="FUTURES",
    expiration_time=1786583700,
    filling_mode=3,
)
