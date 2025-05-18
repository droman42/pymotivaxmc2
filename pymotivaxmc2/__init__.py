"""
Emotiva XMC-2 Control Library.

This library provides a convenient interface to control Emotiva XMC-2 
and other Emotiva devices using the Emotiva control protocol.
"""

from .controller import EmotivaController
from .enums import Command, Property, Input, Zone
from .exceptions import (
    EmotivaError,
    AckTimeoutError,
    InvalidArgumentError,
)
from .core.logging import setup_logging

__version__ = "0.2.0"
__all__ = [
    "EmotivaController",
    "Command",
    "Property",
    "Input",
    "Zone",
    "EmotivaError",
    "AckTimeoutError",
    "InvalidArgumentError",
    "setup_logging",
]
