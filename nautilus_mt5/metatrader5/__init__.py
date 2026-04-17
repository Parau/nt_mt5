import platform
import os
from contextlib import suppress
from nautilus_mt5.metatrader5.config import RpycConnectionConfig, EAConnectionConfig
from nautilus_mt5.metatrader5.ea_client import EAClient
from nautilus_mt5.metatrader5.ea_sockets import EASocketConnection
from nautilus_mt5.metatrader5.errors import EA_ERROR_DICT

current_dir = os.path.dirname(__file__)

with suppress(ImportError):
    if platform.system() == "Windows":
        import MetaTrader5
    else:
        from .MetaTrader5 import MetaTrader5

try:
    from .MetaTrader5 import MetaTrader5
except ImportError:
    pass

__all__ = [
    "MetaTrader5",
    "RpycConnectionConfig",
    "EAConnectionConfig",
    "EAClient",
    "EASocketConnection",
    "EA_ERROR_DICT",
]

"""
Low-level messaging protocol for financial data streaming.

- Uses sockets.
- Implements a custom protocol (not FIX).
- Uses a custom message format (not JSON).
"""
