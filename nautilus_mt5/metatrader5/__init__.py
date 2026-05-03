import platform
import os
from contextlib import suppress
from nautilus_mt5.metatrader5.config import RpycConnectionConfig, EAConnectionConfig
from nautilus_mt5.metatrader5.ea_client import EAClient
from nautilus_mt5.metatrader5.ea_sockets import EASocketConnection
from nautilus_mt5.metatrader5.errors import EA_ERROR_DICT
from nautilus_mt5.metatrader5.local_python import LocalPythonMT5

current_dir = os.path.dirname(__file__)

# RPyC-based MetaTrader5 wrapper (used by EXTERNAL_RPYC mode)
# Always importable regardless of platform — it is a pure Python RPyC client.
with suppress(ImportError):
    from .MetaTrader5 import MetaTrader5

try:
    from .MetaTrader5 import MetaTrader5
except ImportError:
    pass

__all__ = [
    "MetaTrader5",
    "LocalPythonMT5",
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
