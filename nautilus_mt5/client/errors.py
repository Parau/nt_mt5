"""Adapter-side market-data errors.

Purpose/Single Responsibility:
    Define controlled failures raised by MT5 client-layer market-data operations.

Data Flow & Dependencies:
    Raised by the MT5 client/data adapter and observed by Nautilus live-client
    task error handling.

Premises & Limitations:
    These exceptions report failed supported operations; they are not Nautilus
    DataResponse payloads.
"""


class MT5HistoricalDataError(RuntimeError):
    """Report a failed supported MT5 historical-data operation.

    Boundary Role: Adapter
    Access: EXTERNAL

    The exception distinguishes a failed bounded provider operation from a
    successful request whose result contains no matching data.
    """
