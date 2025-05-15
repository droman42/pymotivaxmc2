"""
Exceptions for the Emotiva integration.

This module defines custom exceptions used throughout the Emotiva integration.
"""


class EmotivaError(Exception):
    """Base exception for all Emotiva-related errors."""
    pass


class EmotivaNetworkError(EmotivaError):
    """Exception raised for network-related errors."""
    pass


class CommandTimeoutError(EmotivaNetworkError):
    """Exception raised when a command times out."""
    pass


class DeviceOfflineError(EmotivaNetworkError):
    """Exception raised when trying to communicate with an offline device."""
    pass


class InvalidResponseError(EmotivaError):
    """Exception raised when a response cannot be parsed."""
    pass


class InvalidTransponderResponseError(InvalidResponseError):
    """Exception raised when a transponder response is invalid."""
    pass


class InvalidCommandResponseError(InvalidResponseError):
    """Exception raised when a command response is invalid."""
    pass


class InvalidNotificationError(InvalidResponseError):
    """Exception raised when a notification is invalid."""
    pass


class StateValidationError(EmotivaError):
    """Exception raised when state validation fails."""
    pass


class InvalidSourceError(EmotivaError):
    """Exception raised when an invalid source is specified."""
    pass


class InvalidModeError(EmotivaError):
    """Exception raised when an invalid audio mode is specified."""
    pass
