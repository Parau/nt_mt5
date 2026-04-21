import re

with open("nautilus_mt5/parsing/instruments.py", "r") as f:
    content = f.read()

# I apparently didn't apply the script successfully previously.
new_symbology = """def mt5_symbol_to_instrument_id_simplified_symbology(
    mt5_symbol: MT5Symbol,
) -> InstrumentId:
    if len(mt5_symbol.symbol) > 0:
        symbol = mt5_symbol.symbol
    else:
        symbol = None

    venue = "METATRADER_5"

    if symbol:
        return InstrumentId(Symbol(symbol), Venue(venue))
    raise ValueError(f"Unknown {symbol=}")
"""

content = re.sub(
    r'def mt5_symbol_to_instrument_id_simplified_symbology.*?raise ValueError.*?$',
    new_symbology,
    content,
    flags=re.DOTALL|re.MULTILINE
)

# Wait the previous regex might not match correctly because of the variable substitution or newlines. Let's just find and replace using exact string since it's easy.

content = content.replace(
"""def mt5_symbol_to_instrument_id_simplified_symbology(
    mt5_symbol: MT5Symbol,
) -> InstrumentId:
    if len(mt5_symbol.symbol) > 0:
        symbol = mt5_symbol.symbol
        venue = mt5_symbol.broker
    else:
        symbol = None
        venue = None

    if not venue:
        venue = "METATRADER_5"

    if symbol and venue:
        return InstrumentId(Symbol(symbol), Venue(venue))
    raise ValueError(f"Unknown {symbol=} (broker={mt5_symbol.broker})")""",
new_symbology
)

content = content.replace(
"""def instrument_id_to_mt5_symbol(
    instrument_id: InstrumentId,
    strict_symbology: bool = False,
) -> MT5Symbol:
    PyCondition.type(instrument_id, InstrumentId, "InstrumentId")

    # if strict_symbology:
    #     return instrument_id_to_ib_contract_strict_symbology(instrument_id)
    # else:
    #     return instrument_id_to_ib_contract_simplified_symbology(instrument_id)
    mt_symbol = instrument_id.symbol.value.replace("/", "")
    mt_broker = instrument_id.venue.value.replace("/", ".")
    return MT5Symbol(symbol=mt_symbol, broker=mt_broker)""",
"""def instrument_id_to_mt5_symbol(
    instrument_id: InstrumentId,
    strict_symbology: bool = False,
) -> MT5Symbol:
    PyCondition.type(instrument_id, InstrumentId, "InstrumentId")

    mt_symbol = instrument_id.symbol.value.replace("/", "")
    return MT5Symbol(symbol=mt_symbol, broker="")"""
)

with open("nautilus_mt5/parsing/instruments.py", "w") as f:
    f.write(content)
