class EmotivaError(Exception):
    """Base error for pymotivaxmc2."""

class AckTimeoutError(EmotivaError):
    """Raised when a command does not receive an <emotivaAck> in time."""


class InvalidArgumentError(EmotivaError):
    """Raised when helper receives an invalid value."""

class InvalidCommandError(EmotivaError):
    """Raised when unsupported Command is requested."""

class DeviceOfflineError(EmotivaError):
    """Raised when keep‑alives lost and device marked offline."""


# Phase 2 Fix: Additional error types for improved error categorization
class ConnectionError(EmotivaError):
    """Raised when connection-related operations fail."""

class NetworkError(EmotivaError):
    """Raised when network-level operations fail."""
    
class ProtocolError(EmotivaError):
    """Raised when protocol-level errors occur."""
    
class ConcurrencyError(EmotivaError):
    """Raised when concurrency limits are exceeded."""
    
class RetryExhaustedError(EmotivaError):
    """Raised when all retry attempts have been exhausted."""
