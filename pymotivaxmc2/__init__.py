"""
Python library for controlling Emotiva XMC-2 processors.

This library allows you to discover, connect to, and control Emotiva XMC-2 processors on your network.
"""

from .emotiva_types import EmotivaConfig, EmotivaNotification
from .controller import EmotivaController
from .exceptions import EmotivaError

__version__ = "0.5.0"
__all__ = ["EmotivaController", "EmotivaError", "EmotivaConfig", "EmotivaNotification"]
