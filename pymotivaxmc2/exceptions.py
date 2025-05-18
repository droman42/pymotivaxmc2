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
