import msgspec
from typing import Callable, Optional
from rpyc.utils.classic import DEFAULT_SERVER_PORT as RPYC_DEFAULT_SERVER_PORT

class RpycConnectionConfig(msgspec.Struct, frozen=True):
    """
    Configuration for RPYC connection.

    Attributes:
        host (str): Host address for the RPYC connection. Default is "localhost".
        port (int): Port number for the RPYC connection. Default is 18812.
        keep_alive (bool): Whether to keep the RPYC connection alive. Default is False.
    """
    host: str = "localhost"
    port: int = RPYC_DEFAULT_SERVER_PORT
    keep_alive: bool = False



class EAConnectionConfig(msgspec.Struct, frozen=True):
    """
    Configuration for EAClient.

    Attributes:
        host (str): Host address for the EAClient. Default is "127.0.0.1".
        rest_port (int): Port number for REST API. Default is 15556.
        stream_port (int): Port number for streaming data. Default is 15557.
        encoding (str): Encoding type. Default is 'utf-8'.
        use_socket (bool): Whether to use sockets for communication. Default is True.
        enable_stream (bool): Flag to enable or disable streaming. Default is True.
        callback (Optional[Callable]): Callback function to handle streamed data. Default is None.
        debug (bool): Whether to enable debug messages. Default is False.
    """
    host: str = "127.0.0.1"
    rest_port: int = 15556
    stream_port: int = 15557
    encoding: str = 'utf-8'
    use_socket: bool = True
    enable_stream: bool = True
    callback: Optional[Callable] = None
    debug: bool = False

