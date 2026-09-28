"""Official Python client for the Connect Media SMS API (https://connectmedia.co.ke/developers/)."""

from .client import Client, ConnectMediaError, normalize_msisdn

__all__ = ["Client", "ConnectMediaError", "normalize_msisdn"]
__version__ = "1.0.0"
