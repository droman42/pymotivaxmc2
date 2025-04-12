"""
Custom exceptions for the eMotiva integration.

This module defines custom exceptions used throughout the Motiva integration
to handle specific error cases in a more granular way than standard Python exceptions.
"""

class Error(Exception):
    """Base exception class for all eMotiva-specific exceptions.
    
    This serves as the parent class for all custom exceptions in this module,
    allowing for catching all Motiva-related exceptions with a single except clause.
    """
    pass


class InvalidTransponderResponseError(Error):
    """Raised when the transponder returns an invalid or unexpected response.
    
    This exception is typically raised when:
    - The response format is incorrect
    - Required fields are missing
    - The response contains invalid data
    """
    pass


class InvalidSourceError(Error):
    """Raised when an invalid source is specified for an operation.
    
    This exception is raised when:
    - The source identifier is not recognized
    - The source is not available
    - The source is not compatible with the requested operation
    """
    pass


class InvalidModeError(Error):
    """Raised when an invalid mode is specified for an operation.
    
    This exception is raised when:
    - The mode identifier is not recognized
    - The mode is not available
    - The mode is not compatible with the current configuration
    """
    pass


class DeviceOfflineError(Error):
    """Raised when the device appears to be offline based on missed keepalives."""
    pass
