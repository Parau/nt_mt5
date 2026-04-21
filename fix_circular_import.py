import re

with open("nautilus_mt5/constants.py", "r") as f:
    content = f.read()

# Remove ErrorInfo and MT5 stuff from constants to avoid circular import, since they depend on client/types and metatrader5
# Wait, NO_VALID_ID and TERMINAL_CONNECT_FAIL are what connection.py wants.
# Let's remove `from nautilus_mt5.client.types import ErrorInfo` and `from nautilus_mt5.metatrader5 import MetaTrader5` from constants.py.
# And just hardcode them or use a generic tuple for ErrorInfo.

new_constants = """from decimal import Decimal
from typing import Final, NamedTuple
from nautilus_trader.model.identifiers import Venue

MT5_VENUE: Final[Venue] = Venue("METATRADER_5")
NO_VALID_ID = -1
UNSET_DECIMAL = Decimal(2**127 - 1)

class ErrorInfo(NamedTuple):
    code: int
    msg: str

ALREADY_CONNECTED = ErrorInfo(1, "Already connected.")
RPYC_SERVER_CONNECT_FAIL = ErrorInfo(-1, "Rpyc Server connection failed")
TERMINAL_CONNECT_FAIL = ErrorInfo(0, "Terminal connection failed")
TERMINAL_INIT_FAIL = ErrorInfo(-10000, "MetaTrader5 instance is not initialized")
UPDATE_TERMINAL = ErrorInfo(503, "The TERMINAL is out of date and must be upgraded.")
NOT_CONNECTED = ErrorInfo(504, "Not connected")
UNKNOWN_ID = ErrorInfo(505, "Fatal Error: Unknown message id.")
UNSUPPORTED_VERSION = ErrorInfo(506, "Unsupported version")
BAD_LENGTH = ErrorInfo(507, "Bad message length")
BAD_MESSAGE = ErrorInfo(508, "Bad message")
SOCKET_EXCEPTION = ErrorInfo(509, "Exception caught while reading socket - ")
FAIL_CREATE_SOCK = ErrorInfo(520, "Failed to create socket")
SSL_FAIL = ErrorInfo(530, "SSL specific error: ")
INVALID_SYMBOL = ErrorInfo(579, "Invalid symbol in string - ")
"""

with open("nautilus_mt5/constants.py", "w") as f:
    f.write(new_constants)
