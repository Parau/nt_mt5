import pytest
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_mt5.parsing.instruments import mt5_symbol_to_instrument_id_simplified_symbology, instrument_id_to_mt5_symbol
from nautilus_mt5.data_types import MT5Symbol

def test_symbology_mt5_to_instrument_id():
    mt5_sym = MT5Symbol(symbol="EURUSD", broker="TEST")
    inst_id = mt5_symbol_to_instrument_id_simplified_symbology(mt5_sym)
    assert inst_id.symbol.value == "EURUSD"
    assert inst_id.venue.value == "METATRADER_5"

def test_symbology_instrument_id_to_mt5():
    inst_id = InstrumentId(Symbol("EURUSD"), Venue("METATRADER_5"))
    mt5_sym = instrument_id_to_mt5_symbol(inst_id)
    assert mt5_sym.symbol == "EURUSD"
    assert mt5_sym.broker == "METATRADER_5"
